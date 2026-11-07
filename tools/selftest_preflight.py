# -*- coding: utf-8 -*-
"""Self-test for preflight.py: version checks on a synthetic game folder.

  py -3 tools/selftest_preflight.py

No game needed.  The "archive" is a few hundred kilobytes with one range
patched in place, the way the font range is in PACK00_01.PAK.
"""
import builtins, contextlib, hashlib, io, json, os, shutil, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import preflight as P                   # noqa: E402

failures = []


def check(name, cond):
    print("  %-52s %s" % (name, "ok" if cond else "失败"))
    if not cond:
        failures.append(name)


def sha(b):
    return hashlib.sha256(b).hexdigest()


@contextlib.contextmanager
def counting_reads(path):
    """Bytes read from `path` while inside the block."""
    real_open = builtins.open
    total = [0]

    class Counted:
        def __init__(self, f):
            self.f = f

        def read(self, n=-1):
            b = self.f.read(n)
            total[0] += len(b)
            return b

        def __enter__(self):
            return self

        def __exit__(self, *a):
            self.f.close()

    def fake_open(p, *a, **k):
        f = real_open(p, *a, **k)
        if os.path.abspath(str(p)) == os.path.abspath(path):
            return Counted(f)
        return f
    builtins.open = fake_open
    try:
        yield total
    finally:
        builtins.open = real_open


root = tempfile.mkdtemp(prefix="cielzh-preflight-")
try:
    game = os.path.join(root, "game")
    backup = os.path.join(game, "Backup")
    os.makedirs(os.path.join(game, "Res_x64"))
    os.makedirs(backup)
    original = bytes((i * 7 + 3) % 251 for i in range(300000))
    OFF, SIZE = 100000, 5000
    patched = original[:OFF] + b"\x5a" * SIZE + original[OFF + SIZE:]
    rel = "Res_x64/PACK00_01.PAK"
    pak = os.path.join(game, rel)
    table = {sha(original): ("v", "supported")}

    def write_pak(data):
        open(pak, "wb").write(data)

    def write_backup(rng=original[OFF:OFF + SIZE], plan=True, off=OFF):
        for fn in os.listdir(backup):
            os.remove(os.path.join(backup, fn))
        open(os.path.join(backup, "PACK00_01.PAK.%d.orig-range" % off), "wb").write(rng)
        if plan:
            json.dump([{"archive": "PACK00_01.PAK", "offset": off, "size": SIZE,
                        "sha256_before": sha(original[OFF:OFF + SIZE])}],
                      io.open(os.path.join(backup, P.PLAN), "w", encoding="utf-8"))

    write_pak(original)
    now, virt = P.hash_both(pak, [])
    check("原版：当前摘要就是原版摘要", now == sha(original))
    check("  ……没有备份区间时不算虚拟还原摘要", virt is None)

    write_pak(patched)
    write_backup()
    ranges = P.in_place_ranges(backup, "PACK00_01.PAK")
    with counting_reads(pak) as n:
        now, virt = P.hash_both(pak, ranges)
    check("原地修改：当前摘要不是原版", now == sha(patched) and now not in table)
    check("  ……代回备份区间后是原版", virt == sha(original))
    check("  ……两个摘要只读了一遍文件", n[0] == len(patched))
    check("  ……restorable_in_place 判为可还原", P.restorable_in_place(game, backup, rel, table))

    write_backup(plan=False)
    check("0.9.6 之前没有计划文件：按区间文件名还原",
          P.restorable_in_place(game, backup, rel, table))

    write_backup(rng=b"\x00" * SIZE)
    check("备份区间与计划记录的摘要不符：不认", P.in_place_ranges(backup, "PACK00_01.PAK") == []
          and not P.restorable_in_place(game, backup, rel, table))

    write_backup()
    write_pak(patched[:200] + b"\xff" + patched[201:])
    check("区间以外还有别的改动：虚拟还原后不是原版，不认",
          not P.restorable_in_place(game, backup, rel, table))

    write_pak(patched[:OFF + 10])
    now, virt = P.hash_both(pak, P.in_place_ranges(backup, "PACK00_01.PAK"))
    check("文件在区间中间就结束了：不算虚拟摘要", virt is None)
    write_pak(patched[:OFF - 10])
    now, virt = P.hash_both(pak, P.in_place_ranges(backup, "PACK00_01.PAK"))
    check("文件在区间之前就结束了：不算虚拟摘要", virt is None)

    write_pak(patched)
    now, virt = P.hash_both(pak, [(OFF, original[OFF:OFF + SIZE]),
                                  (OFF + 10, original[OFF + 10:OFF + SIZE])])
    check("区间重叠：不猜", virt is None and now == sha(patched))

    # the whole check, through main(), on a folder with the four files it wants
    data = os.path.join(root, "data")
    os.makedirs(data)
    others = {"CielnosurgeDX.exe": b"exe", "CielnosurgeDX_Env.exe": b"env",
              "Res_x64/PACK01.PAK": b"pak01"}
    for r, b in others.items():
        open(os.path.join(game, r), "wb").write(b)
    with io.open(os.path.join(data, "game-versions.csv"), "w", encoding="utf-8") as f:
        f.write("version_id,label,platform,file,bytes,sha256,status,note\n")
        for r, b in list(others.items()) + [(rel, original)]:
            f.write("v,x,x,%s,%d,%s,supported,\n" % (r, len(b), sha(b)))
    write_backup()
    write_pak(patched)
    out = io.StringIO()
    with counting_reads(pak) as n, contextlib.redirect_stdout(out):
        rc = P.main(["--game", game, "--data", data, "--need-mb", "0"])
    check("预检：原地修改过的封包判为已安装过、可以重装",
          rc == 0 and "原地修改" in out.getvalue())
    check("  ……整个预检只读了一遍封包", n[0] == len(patched))
    full = os.path.join(backup, "PACK00_01.PAK")
    open(full, "wb").write(original)       # what 0.9.4/0.9.5 left behind
    out = io.StringIO()
    with counting_reads(full) as nb, contextlib.redirect_stdout(out):
        rc = P.main(["--game", game, "--data", data, "--need-mb", "0"])
    check("还留着早期的整份备份：区间能还原时不再读整份备份",
          rc == 0 and nb[0] == 0 and "原地修改" in out.getvalue())
    write_backup()                          # ranges gone bad, full copy still there
    os.remove(os.path.join(backup, "PACK00_01.PAK.%d.orig-range" % OFF))
    open(full, "wb").write(original)
    out = io.StringIO()
    with counting_reads(full) as nb, contextlib.redirect_stdout(out):
        rc = P.main(["--game", game, "--data", data, "--need-mb", "0"])
    check("  ……区间备份缺失时退回检查整份备份",
          rc == 0 and nb[0] == len(original) and "原版已备份" in out.getvalue())
    os.remove(full)
    write_backup()
    write_pak(patched[:200] + b"\xff" + patched[201:])
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = P.main(["--game", game, "--data", data, "--need-mb", "0"])
    check("预检：封包被别的东西改过：拒绝并给出摘要", rc == 5 and "无法识别" in out.getvalue())
finally:
    shutil.rmtree(root, ignore_errors=True)

print()
print("%d 项未通过" % len(failures) if failures else "全部自检通过")
sys.exit(1 if failures else 0)
