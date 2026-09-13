# -*- coding: utf-8 -*-
"""Decide whether this game folder can be patched, before anything is written.

  py -3 tools/preflight.py --game "<folder>" [--data data] [--need-mb 6000]

The installer runs this first.  It answers one question -- is it safe to go
ahead -- and says why not in words a player can act on.  Nothing here writes
anything.

Exit status 0 means go ahead.  Anything else means stop, and the reason has
already been printed.
"""
import sys, os, io, csv, shutil, hashlib, argparse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import gamepath

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

REQUIRED = ["CielnosurgeDX.exe", "Res_x64/PACK01.PAK", "Res_x64/PACK00_01.PAK"]


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


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--game")
    ap.add_argument("--data", default=os.path.join(ROOT, "data"))
    ap.add_argument("--need-mb", type=int, default=6000)
    a = ap.parse_args(argv)

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


if __name__ == "__main__":
    sys.exit(main())
