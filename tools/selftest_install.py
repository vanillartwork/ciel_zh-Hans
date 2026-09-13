# -*- coding: utf-8 -*-
"""Prove that an in-place patch can be applied, re-applied and undone.

  py -3 tools/selftest_install.py

One archive is patched by overwriting a byte range rather than being replaced
wholesale, and its backup is that range alone. That is a lot less copying, but
it puts the burden on this code to put the bytes back exactly -- so the undo
path has to be tested, not assumed. It was in fact broken once: the revert
function existed and nothing ever called it.

Runs on synthetic files; needs neither the game nor a patched build.
"""
import sys, os, io, json, hashlib, shutil, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import install

for _s in (sys.stdout,):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

OFFSET, SIZE = 4096, 2048


def sha(b):
    return hashlib.sha256(b).hexdigest()


def build_case(root):
    """A fake game folder with one archive, plus a plan that rewrites a slice."""
    game = os.path.join(root, "game")
    os.makedirs(os.path.join(game, "Res_x64"))
    os.makedirs(os.path.join(game, "Backup"))
    original = bytes(range(256)) * 64                      # 16 KB, recognisable
    archive = os.path.join(game, "Res_x64", "PACK00_01.PAK")
    io.open(archive, "wb").write(original)

    new_slice = b"\xA5" * SIZE
    staged = os.path.join(root, "dist")
    os.makedirs(staged)
    io.open(os.path.join(staged, "slice.bin"), "wb").write(new_slice)
    plan = [{
        "archive": "PACK00_01.PAK", "entry": "test/slice", "file": "slice.bin",
        "offset": OFFSET, "size": SIZE,
        "sha256_before": sha(original[OFFSET:OFFSET + SIZE]),
        "sha256_after": sha(new_slice),
    }]
    io.open(os.path.join(staged, install.PLAN), "w", encoding="utf-8").write(
        json.dumps(plan, ensure_ascii=False))
    return game, staged, original, new_slice


def main():
    failures = []
    root = tempfile.mkdtemp(prefix="cninst-")
    try:
        game, staged, original, new_slice = build_case(root)
        backup = os.path.join(game, "Backup")
        archive = os.path.join(game, "Res_x64", "PACK00_01.PAK")
        plan = install.load_plan(root)
        if not plan:
            print("FAILED: the plan was not found next to the staged files")
            return 1
        step = plan[0]

        def check(name, cond):
            print("  %-46s %s" % (name, "ok" if cond else "FAILED"))
            if not cond:
                failures.append(name)

        # apply
        changed = install.apply_step(game, backup, step, report=lambda *a: None)
        cur = open(archive, "rb").read()
        check("写入后该段等于新内容", cur[OFFSET:OFFSET + SIZE] == new_slice)
        check("写入报告发生了改动", changed is True)
        check("该段以外一个字节都没动",
              cur[:OFFSET] == original[:OFFSET]
              and cur[OFFSET + SIZE:] == original[OFFSET + SIZE:])
        check("文件大小不变", len(cur) == len(original))
        b = install.backup_name(backup, step)
        check("备份的是被覆盖的原始字节",
              os.path.isfile(b)
              and open(b, "rb").read() == original[OFFSET:OFFSET + SIZE])

        # apply again: should be a no-op, and must not overwrite the backup
        again = install.apply_step(game, backup, step, report=lambda *a: None)
        check("重复安装被识别为已是该版本", again is False)
        check("重复安装没有把备份覆盖成补丁内容",
              open(b, "rb").read() == original[OFFSET:OFFSET + SIZE])

        # undo
        ok = install.revert_step(game, backup, step)
        check("还原报告成功", ok is True)
        check("还原后整个文件与原始逐字节相同",
              open(archive, "rb").read() == original)

        # a truncated backup must be refused rather than written
        io.open(b, "wb").write(b"\x00" * (SIZE - 1))
        check("备份长度不对时拒绝还原",
              install.revert_step(game, backup, step) is False)

        # and with the original bytes gone and no usable backup, applying to
        # something unrecognised must raise instead of guessing
        with open(archive, "r+b") as f:
            f.seek(OFFSET)
            f.write(b"\x11" * SIZE)
        os.remove(b)
        try:
            install.apply_step(game, backup, step, report=lambda *a: None)
            check("内容无法识别且无备份时拒绝写入", False)
        except IOError:
            check("内容无法识别且无备份时拒绝写入", True)
    finally:
        shutil.rmtree(root, ignore_errors=True)

    print()
    if failures:
        print("%d 项未通过" % len(failures))
        return 1
    print("全部 10 项自检通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
