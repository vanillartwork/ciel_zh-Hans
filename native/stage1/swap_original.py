# -*- coding: utf-8 -*-
"""Put the original game back for a debugging session, then put the patch back.

  py -3 swap_original.py status
  py -3 swap_original.py check   # every check `in` makes, changes nothing
  py -3 swap_original.py in      # patched -> original
  py -3 swap_original.py out     # original -> patched, exactly as it was

Stage one sets breakpoints on addresses read out of the ORIGINAL executable,
and wants to watch the original game, not ours.  Uninstalling and reinstalling
would do that too, but rebuilds everything and goes through the installer's
own backup handling; this only moves files aside and back.

Backup/ is read, never written.  What this changes:

  * CielnosurgeDX.exe, CielnosurgeDX_Env.exe, Res_x64/PACK01.PAK
      the patched file is moved into the stash (same volume, so a rename), and
      the original is copied in from Backup/.
  * Res_x64/PACK00_01.PAK
      the patch rewrote one 16,777,260-byte range in place.  That range is
      copied into the stash and the original range from Backup/ written over
      it -- rather than moving a 1.77 GB file around.

Every step is checked against a hash before and after, and the manifest is
rewritten after each one, so a failure halfway leaves a record `out` can finish
from.  `out` refuses to overwrite anything that no longer matches what `in`
left behind: if the game updated itself in between, that is for a person to
look at, not for this to paper over.
"""
import sys, os, io, json, hashlib, shutil, subprocess, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "tools"))
import gamepath  # noqa: E402

STASH_NAME = "_cielzh_stage1_stash"
MANIFEST = "manifest.json"

# Original hashes, from data/game-versions.csv.  Duplicated here on purpose:
# this must not quietly accept a Backup/ that is not the original.
ORIGINAL = {
    "CielnosurgeDX.exe":
        "04b755ab2eb26f26f79df9d2a24d9dcc62f5adca43bdb4871a137866d5d60b90",
    "CielnosurgeDX_Env.exe":
        "0f7ecfa3108a2d86e468d7ab962b2b39160ba576088e2aa50cc0bab897cacdaf",
    "Res_x64/PACK01.PAK":
        "4089c93a99b323b85bd96aa09da822baa1e1ff8778d08c7f5f4256abb2a06086",
    "Res_x64/PACK00_01.PAK":
        "60df678db62674e73cbc80afb7c11e8e125385c2d4f0e1dde44aec91c614c851",
}
WHOLE = ["CielnosurgeDX.exe", "CielnosurgeDX_Env.exe", "Res_x64/PACK01.PAK"]
RANGED = "Res_x64/PACK00_01.PAK"


def sha256_file(path, chunk=1 << 22):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                return h.hexdigest()
            h.update(b)


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def read_range(path, offset, size):
    with open(path, "rb") as f:
        f.seek(offset)
        b = f.read(size)
    if len(b) != size:
        raise SystemExit("%s: short read at %d" % (path, offset))
    return b


def write_range(path, offset, data):
    with open(path, "r+b") as f:
        f.seek(offset)
        f.write(data)
        f.flush()
        os.fsync(f.fileno())


def copy_in(src, dst):
    tmp = dst + ".cielzh-tmp"
    shutil.copyfile(src, tmp)
    os.replace(tmp, dst)


def game_running():
    try:
        out = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq CielnosurgeDX.exe", "/NH"],
            capture_output=True, text=True, timeout=20).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return "CielnosurgeDX.exe" in out


class Stash:
    def __init__(self, game):
        self.game = game
        self.dir = os.path.join(game, STASH_NAME)
        self.path = os.path.join(self.dir, MANIFEST)

    def exists(self):
        return os.path.exists(self.path)

    def load(self):
        with io.open(self.path, encoding="utf-8") as f:
            return json.load(f)

    def save(self, m):
        tmp = self.path + ".tmp"
        with io.open(tmp, "w", encoding="utf-8") as f:
            json.dump(m, f, ensure_ascii=False, indent=1)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.path)


def ranged_plan(backup):
    p = os.path.join(backup, "inplace.json")
    with io.open(p, encoding="utf-8") as f:
        plan = json.load(f)
    steps = [s for s in plan if s["archive"] == "PACK00_01.PAK"]
    if len(steps) != 1:
        raise SystemExit("Backup/inplace.json does not describe exactly one "
                         "PACK00_01.PAK range; not guessing")
    return steps[0]


def cmd_status(game, stash):
    if not stash.exists():
        print("游戏目录当前未处于「临时原版」状态（没有 %s）" % STASH_NAME)
    else:
        m = stash.load()
        print("游戏目录处于「临时原版」状态，开始于 %s" % m["started"])
        for rel, st in m["files"].items():
            print("  %-26s %s" % (rel, st["state"]))
    for rel in WHOLE:
        h = sha256_file(os.path.join(game, rel))
        tag = "原版" if h == ORIGINAL[rel] else "非原版（补丁或其他）"
        print("  当前 %-22s %s" % (rel, tag))


def preflight(game, stash):
    """Every check `in` makes before it touches anything.  Read-only."""
    backup = os.path.join(game, "Backup")
    if stash.exists():
        raise SystemExit("已经处于「临时原版」状态。先运行 `out` 还原，或 `status` 查看。")
    if game_running():
        raise SystemExit("游戏正在运行。请先退出游戏。")

    print("核对 Backup/ 中的原版文件（只读）……")
    for rel in WHOLE:
        src = os.path.join(backup, os.path.basename(rel))
        if sha256_file(src) != ORIGINAL[rel]:
            raise SystemExit("Backup/%s 不是已知的原版，停止。"
                             % os.path.basename(rel))
    step = ranged_plan(backup)
    rng_src = os.path.join(backup, "%s.%d.orig-range"
                           % (step["archive"], step["offset"]))
    rng_orig = open(rng_src, "rb").read()
    if len(rng_orig) != step["size"] or sha256_bytes(rng_orig) != step["sha256_before"]:
        raise SystemExit("Backup/ 中的字库区间备份与 inplace.json 不符，停止。")

    print("核对当前游戏文件是补丁版……")
    live = {}
    for rel in WHOLE:
        h = sha256_file(os.path.join(game, rel))
        if h == ORIGINAL[rel]:
            raise SystemExit("%s 已经是原版——补丁可能没装，或状态不明，停止。" % rel)
        live[rel] = h
    pak = os.path.join(game, RANGED)
    rng_live = read_range(pak, step["offset"], step["size"])
    if sha256_bytes(rng_live) != step["sha256_after"]:
        raise SystemExit("%s 的字库区间不是补丁写入的内容，停止。" % RANGED)
    return backup, step, rng_orig, live, rng_live


def cmd_check(game, stash):
    preflight(game, stash)
    print("\n核对全部通过，可以运行 `in`。本命令未改动任何文件。")


def cmd_in(game, stash):
    backup, step, rng_orig, live, rng_live = preflight(game, stash)
    pak = os.path.join(game, RANGED)

    os.makedirs(stash.dir, exist_ok=True)
    m = {"started": time.strftime("%Y-%m-%d %H:%M:%S"), "files": {}}
    for rel in WHOLE:
        m["files"][rel] = {"patched_sha256": live[rel], "state": "pending"}
    m["files"][RANGED] = {"offset": step["offset"], "size": step["size"],
                          "patched_range_sha256": step["sha256_after"],
                          "original_range_sha256": step["sha256_before"],
                          "state": "pending"}
    stash.save(m)

    for rel in WHOLE:
        dst = os.path.join(game, rel)
        kept = os.path.join(stash.dir, os.path.basename(rel))
        os.replace(dst, kept)                       # patched -> stash
        m["files"][rel]["state"] = "patched moved to stash"
        stash.save(m)
        copy_in(os.path.join(backup, os.path.basename(rel)), dst)
        if sha256_file(dst) != ORIGINAL[rel]:
            raise SystemExit("%s 拷入后哈希不符。运行 `out` 可还原。" % rel)
        m["files"][rel]["state"] = "original in place"
        stash.save(m)
        print("  %-26s 已换为原版" % rel)

    kept = os.path.join(stash.dir, "PACK00_01.range")
    with open(kept, "wb") as f:
        f.write(rng_live)
        f.flush()
        os.fsync(f.fileno())
    m["files"][RANGED]["state"] = "patched range in stash"
    stash.save(m)
    write_range(pak, step["offset"], rng_orig)
    if sha256_bytes(read_range(pak, step["offset"], step["size"])) != step["sha256_before"]:
        raise SystemExit("%s 区间写回后哈希不符。运行 `out` 可还原。" % RANGED)
    m["files"][RANGED]["state"] = "original range in place"
    stash.save(m)
    print("  %-26s 字库区间已换为原版" % RANGED)

    print("核对整个 %s（约 1.7 GB，需要一会儿）……" % RANGED)
    if sha256_file(pak) != ORIGINAL[RANGED]:
        raise SystemExit("%s 整体哈希不是原版：区间之外还有差异。运行 `out` 可还原。"
                         % RANGED)
    print("\n完成。四个文件均与原版哈希一致。Backup/ 未改动。")
    print("调试结束后运行：py -3 swap_original.py out")


def cmd_out(game, stash):
    if not stash.exists():
        raise SystemExit("没有找到 %s，当前不是「临时原版」状态。" % STASH_NAME)
    if game_running():
        raise SystemExit("游戏正在运行。请先退出游戏（以及调试器）。")
    m = stash.load()

    r = m["files"][RANGED]
    pak = os.path.join(game, RANGED)
    kept = os.path.join(stash.dir, "PACK00_01.range")
    if r["state"] != "pending":
        cur = sha256_bytes(read_range(pak, r["offset"], r["size"]))
        if cur == r["patched_range_sha256"]:
            pass                                   # already back
        elif cur == r["original_range_sha256"]:
            data = open(kept, "rb").read()
            if sha256_bytes(data) != r["patched_range_sha256"]:
                raise SystemExit("暂存的字库区间已损坏，停止。")
            write_range(pak, r["offset"], data)
            if sha256_bytes(read_range(pak, r["offset"], r["size"])) != r["patched_range_sha256"]:
                raise SystemExit("%s 区间还原后哈希不符，停止。" % RANGED)
        else:
            raise SystemExit("%s 区间既不是原版也不是补丁版——期间被改过，停止，请人工检查。"
                             % RANGED)
    r["state"] = "restored"
    stash.save(m)
    print("  %-26s 字库区间已还原为补丁版" % RANGED)

    for rel in WHOLE:
        st = m["files"][rel]
        dst = os.path.join(game, rel)
        kept = os.path.join(stash.dir, os.path.basename(rel))
        if st["state"] == "pending":
            st["state"] = "restored"               # never touched
            continue
        if os.path.exists(kept):
            if sha256_file(kept) != st["patched_sha256"]:
                raise SystemExit("暂存的 %s 与移出时不同，停止。" % rel)
            if os.path.exists(dst):
                h = sha256_file(dst)
                if h != ORIGINAL[rel]:
                    raise SystemExit("%s 既不是原版也不是暂存的补丁版——期间被改过，"
                                     "停止，请人工检查。" % rel)
            os.replace(kept, dst)
        if sha256_file(dst) != st["patched_sha256"]:
            raise SystemExit("%s 还原后哈希不符，停止。" % rel)
        st["state"] = "restored"
        stash.save(m)
        print("  %-26s 已还原为补丁版" % rel)

    # Remove only what this script created.
    for name in ("PACK00_01.range", MANIFEST):
        p = os.path.join(stash.dir, name)
        if os.path.exists(p):
            os.remove(p)
    try:
        os.rmdir(stash.dir)
    except OSError:
        print("注意：%s 里还有本脚本以外的文件，未删除该目录。" % stash.dir)
    print("\n完成。补丁已原样恢复。Backup/ 未改动。")


def main(argv):
    cmds = {"status": cmd_status, "check": cmd_check, "in": cmd_in, "out": cmd_out}
    if len(argv) != 2 or argv[1] not in cmds:
        print(__doc__)
        return 2
    game = gamepath.resolve()
    stash = Stash(game)
    cmds[argv[1]](game, stash)
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv))
