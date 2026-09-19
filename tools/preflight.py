# -*- coding: utf-8 -*-
"""Decide whether this game folder can be patched, before anything is written.

  py -3 tools/preflight.py --game "<folder>" [--data data] [--need-mb 6000]

The installer runs this first.  It answers one question -- is it safe to go
ahead -- and says why not in words a player can act on.  Nothing here writes
anything.

Exit status 0 means go ahead.  Anything else means stop, and the reason has
already been printed.
"""
import sys, os, io, csv, json, shutil, hashlib, argparse

PLAN = "inplace.json"
RANGE_SUFFIX = ".orig-range"

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import gamepath
import runlog
import progress

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

REQUIRED = ["CielnosurgeDX.exe", "CielnosurgeDX_Env.exe",
            "Res_x64/PACK01.PAK", "Res_x64/PACK00_01.PAK"]


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def expected(data):
    """file -> {sha256: (version_id, status)} for the versions we support."""
    out = {}
    p = os.path.join(data, "game-versions.csv")
    if not os.path.exists(p):
        return out
    for r in csv.DictReader(io.open(p, encoding="utf-8-sig", newline="")):
        if r["status"].strip() != "supported":
            continue
        out.setdefault(r["file"].strip(), {})[r["sha256"].strip().lower()] = \
            (r["version_id"], r["status"])
    return out


def restorable_in_place(game, backup, rel, table):
    """True when this archive is a supported original with our range written over it.

    An archive patched in place has no full backup by design -- only the bytes
    that were overwritten, plus the plan saying where they go.  Checking the
    plan and the range alone is not enough: it says our own edit can be undone,
    not that the rest of the file is still a version this patch was built for.
    A game update, another mod or corruption anywhere outside the font range
    would sail straight through.

    So the whole file is hashed with the backed-up bytes substituted back in as
    it is read -- the archive restored virtually, without writing 1.8 GB or
    holding it in memory -- and that hash has to be one we know.
    """
    plan = os.path.join(backup, PLAN)
    if not os.path.isfile(plan):
        return False
    try:
        steps = json.load(io.open(plan, encoding="utf-8"))
    except (ValueError, OSError):
        return False
    name = os.path.basename(rel)
    steps = [st for st in steps if os.path.basename(st.get("archive", "")) == name]
    if not steps:
        return False

    ranges = []
    for st in steps:
        b = os.path.join(backup, "%s.%d%s" % (name, st["offset"], RANGE_SUFFIX))
        if not os.path.isfile(b) or os.path.getsize(b) != st["size"]:
            return False
        orig = io.open(b, "rb").read()
        if hashlib.sha256(orig).hexdigest() != st["sha256_before"]:
            return False
        ranges.append((st["offset"], orig))
    ranges.sort()

    target = os.path.join(game, rel)
    if not os.path.isfile(target):
        return False
    h = hashlib.sha256()
    pos = 0
    try:
        with open(target, "rb") as f:
            for off, orig in ranges:
                if off < pos:
                    return False              # overlapping ranges: do not guess
                while pos < off:
                    chunk = f.read(min(1 << 20, off - pos))
                    if not chunk:
                        return False
                    h.update(chunk)
                    pos += len(chunk)
                if len(f.read(len(orig))) != len(orig):
                    return False
                h.update(orig)                # the bytes that were displaced
                pos += len(orig)
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
    except OSError:
        return False
    return h.hexdigest() in table


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--game")
    ap.add_argument("--data", default=os.path.join(ROOT, "data"))
    ap.add_argument("--need-mb", type=int, default=1200)
    runlog.add_argument(ap)
    progress.add_arguments(ap)
    ap.add_argument("--done", help="write the exit code here when finished")
    a = ap.parse_args(argv)
    runlog.start(a.log, "preflight.py")
    progress.from_args(a)
    progress.label("正在核对游戏版本")

    try:
        game = gamepath.resolve(a.game)
    except gamepath.NotFound as e:
        print(e)
        return 2
    print("游戏目录：%s" % game)

    for rel in REQUIRED:
        if not os.path.isfile(os.path.join(game, rel)):
            print("\n缺少文件：%s\n"
                  "游戏安装似乎不完整。请先在 Steam 里对游戏执行\n"
                  "“验证游戏文件完整性”，然后重试。" % rel)
            return 3

    free_mb = shutil.disk_usage(game).free // (1024 * 1024)
    if free_mb < a.need_mb:
        print("\n磁盘空间不足：%s 所在磁盘只剩 %d MB，重新打包约需 %d MB。\n"
              "请先清理磁盘空间再重试。" % (game, free_mb, a.need_mb))
        return 4

    known = expected(a.data)
    backup = os.path.join(game, "Backup")
    unknown, already = [], []
    for rel in REQUIRED:
        table = known.get(rel, {})
        if not table:
            continue
        h = sha256(os.path.join(game, rel))
        if h in table:
            print("  %-26s 原版（%s）" % (rel, table[h][0]))
            continue
        b = os.path.join(backup, os.path.basename(rel))
        if os.path.isfile(b) and sha256(b) in table:
            already.append(rel)
            print("  %-26s 已被补丁修改，原版已备份在 Backup" % rel)
        elif restorable_in_place(game, backup, rel, table):
            # An archive patched in place has no full backup by design -- only
            # the range that was overwritten, plus the plan describing it.
            # Without this branch a second install of a patched game is refused
            # as an unsupported version, which is exactly when someone is
            # upgrading.
            already.append(rel)
            print("  %-26s 已被补丁原地修改，原始区间已备份在 Backup" % rel)
        else:
            unknown.append((rel, h))
            print("  %-26s 无法识别（%s…）" % (rel, h[:12]))

    if unknown:
        print("\n以下文件不是本补丁所针对的游戏版本：")
        for rel, h in unknown:
            print("  %s  sha256=%s" % (rel, h))
        print("\n可能的原因：\n"
              "  · 游戏更新到了新版本，本补丁尚未跟进\n"
              "  · 安装过其他补丁或修改，且原始文件没有备份\n"
              "  · 文件损坏\n\n"
              "为避免把游戏改坏，安装已经中止，什么都没有被修改。\n"
              "建议先在 Steam 里执行“验证游戏文件完整性”；如果游戏确实已经\n"
              "更新，请到项目页面反馈，并附上上面这些 sha256。")
        return 5

    if already:
        print("\n检测到已经安装过本补丁，将在原版备份的基础上重新安装。")

    print("\n检查通过，可以安装。")
    return 0


def _run(argv=None):
    """Entry point that always records its exit status for a waiting caller."""
    import argparse as _ap
    done = None
    args = argv if argv is not None else sys.argv[1:]
    if "--done" in args:
        try:
            done = args[args.index("--done") + 1]
        except IndexError:
            done = None
    try:
        code = main(argv)
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
        if e.code and not isinstance(e.code, int):
            print(e.code)
    except Exception:
        import traceback
        traceback.print_exc()
        code = 1
    if done:
        progress.finish(done, code or 0)
    return code or 0

if __name__ == "__main__":
    sys.exit(_run())
