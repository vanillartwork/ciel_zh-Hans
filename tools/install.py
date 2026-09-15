# -*- coding: utf-8 -*-
"""Install the built patch into the game folder, or take it back out.

  py -3 tools/install.py                 say what would happen, change nothing
  py -3 tools/install.py --apply         install
  py -3 tools/install.py --restore       put the originals back
  py -3 tools/install.py --verify        check what is currently installed

The engine reads only the archives -- loose files in the game folder are
ignored -- so installing means replacing two archives and the executable.
That is a lot of bytes to get wrong, so:

  * the game folder is identified before anything is read or written
  * every file that will be replaced is checked against the versions this
    patch was built for, and an unknown one stops the install
  * originals are copied to Backup/ before anything is overwritten, and an
    existing backup is never overwritten by an already-patched file
  * each file is copied to a temporary name, checked, and only then moved
    into place, so an interrupted copy cannot leave a half-written archive
  * if any step fails, what was already replaced is put back

--restore exists so that nobody has to know how to undo this by hand.  If the
backups are gone too, Steam's "verify integrity of game files" will fetch
clean copies.
"""
import sys, os, io, csv, json, shutil, hashlib, argparse, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import gamepath
import runlog
import progress

PLAN = "inplace.json"
# One archive is patched by overwriting a byte range rather than being
# replaced wholesale; see repack_pak.py. Its backup is that range alone.
BACKUP_SUFFIX = ".orig-range"

# what the patch replaces wholesale: (built file, path inside the game folder)
PAYLOAD = [
    ("CielnosurgeDX.exe", "CielnosurgeDX.exe"),
    ("PACK01.PAK", "Res_x64/PACK01.PAK"),
    ("PACK00_01.PAK", "Res_x64/PACK00_01.PAK"),
    ("CielnosurgeDX_Env.exe", "CielnosurgeDX_Env.exe"),
]
# left over from when the patch was tried as loose files; the engine ignores
# them, and leaving them around only confuses the next person to look
STALE = ["inc", "ui", "Res_x64/font"]


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_range(path, offset, size):
    with open(path, "rb") as f:
        f.seek(offset)
        return f.read(size)


def load_plan(build_dir):
    """The in-place steps a build produced, if any."""
    for sub in ("dist", "stage", ""):
        p = os.path.join(build_dir, sub, PLAN) if sub else os.path.join(build_dir, PLAN)
        if os.path.isfile(p):
            steps = json.load(io.open(p, encoding="utf-8"))
            for st in steps:
                st["_src"] = os.path.join(os.path.dirname(p), st["file"])
            return steps
    return []


def save_plan(backup, plan):
    """Keep the restore plan beside the bytes it describes.

    The range backup in Backup/ is 16 MB of the archive's original bytes, and
    nothing else says where in the archive they belong.  The plan used to live
    only in the build folder, which the installer deletes once it has finished
    -- so an uninstall later found the backup but no way to use it, and left
    the game patched.  Writing the plan here makes Backup/ self-sufficient.
    """
    if not plan:
        return
    keep = [{k: v for k, v in st.items() if not k.startswith("_")} for st in plan]
    p = os.path.join(backup, PLAN)
    tmp = p + ".tmp"
    io.open(tmp, "w", encoding="utf-8").write(json.dumps(keep, ensure_ascii=False,
                                                         indent=2))
    os.replace(tmp, p)


def load_applied_plan(backup):
    """What a previous install actually did to this game folder."""
    p = os.path.join(backup, PLAN)
    if not os.path.isfile(p):
        return []
    try:
        return json.load(io.open(p, encoding="utf-8"))
    except (ValueError, OSError):
        return []


def backup_name(backup, step):
    return os.path.join(backup, "%s.%d%s" % (os.path.basename(step["archive"]),
                                             step["offset"], BACKUP_SUFFIX))


def apply_step(game, backup, step, report=print):
    """Overwrite one byte range, keeping the bytes it replaced."""
    target = os.path.join(game, "Res_x64", os.path.basename(step["archive"]))
    if not os.path.isfile(target):
        raise IOError("%s is not there" % target)
    cur = read_range(target, step["offset"], step["size"])
    if hashlib.sha256(cur).hexdigest() == step["sha256_after"]:
        report("  %s is already this build" % step["entry"])
        return False
    b = backup_name(backup, step)
    if hashlib.sha256(cur).hexdigest() == step["sha256_before"]:
        if not os.path.exists(b):
            io.open(b, "wb").write(cur)      # the original bytes, 16 MB not 1.8 GB
    elif not os.path.exists(b):
        raise IOError("%s does not hold the bytes this patch expects, and no "
                      "backup of them exists" % step["entry"])
    new = open(step["_src"], "rb").read()
    if len(new) != step["size"]:
        raise IOError("%s: staged file is %d bytes, the slot is %d"
                      % (step["file"], len(new), step["size"]))
    with open(target, "r+b") as f:
        f.seek(step["offset"])
        f.write(new)
        f.flush()
        os.fsync(f.fileno())
    after = read_range(target, step["offset"], step["size"])
    if hashlib.sha256(after).hexdigest() != step["sha256_after"]:
        raise IOError("%s did not read back as expected after writing" % step["entry"])
    return True


def revert_step(game, backup, step, report=print):
    target = os.path.join(game, "Res_x64", os.path.basename(step["archive"]))
    b = backup_name(backup, step)
    if not (os.path.isfile(target) and os.path.isfile(b)):
        return False
    data = open(b, "rb").read()
    if len(data) != step["size"]:
        return False
    with open(target, "r+b") as f:
        f.seek(step["offset"])
        f.write(data)
    return True


def known_versions(data):
    """sha256 -> (version_id, file) for every original this patch supports."""
    out = {}
    p = os.path.join(data, "game-versions.csv")
    if not os.path.exists(p):
        return out
    for r in csv.DictReader(io.open(p, encoding="utf-8-sig", newline="")):
        out[r["sha256"].strip().lower()] = (r["version_id"], r["file"], r["status"])
    return out


def find_built(build_dir):
    """Locate each payload file in a build tree."""
    found = {}
    for name, _ in PAYLOAD:
        for sub in ("dist", "stage", ""):
            p = os.path.join(build_dir, sub, name) if sub else os.path.join(build_dir, name)
            if os.path.isfile(p):
                found[name] = p
                break
    return found


def human(n):
    return "%.1f MB" % (n / 1e6)


def copy_verified(src, dst):
    """Copy through a temporary file so a failure never leaves a partial one."""
    d = os.path.dirname(dst) or "."
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".cnl10n-", suffix=".part")
    os.close(fd)
    try:
        shutil.copyfile(src, tmp)
        if sha256(tmp) != sha256(src):
            raise IOError("the copy of %s did not match the original; "
                          "the disk may be full" % os.path.basename(src))
        os.replace(tmp, dst)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def do_restore(game, backup, plan=()):
    if not os.path.isdir(backup):
        print("There is no Backup folder at %s.\n"
              "Nothing to restore from. In Steam, right-click the game ->\n"
              "Properties -> Installed Files -> Verify integrity of game files."
              % backup)
        return 1
    inplace_rel = {"Res_x64/" + os.path.basename(st["archive"]) for st in plan}
    n = missing = total = 0

    for name, rel in PAYLOAD:
        dst = os.path.join(game, rel)
        if not os.path.isfile(dst) or rel in inplace_rel:
            continue
        total += 1
        b = os.path.join(backup, os.path.basename(rel))
        if not os.path.isfile(b):
            print("  no backup of %s" % rel)
            missing += 1
            continue
        print("  restoring %s" % rel)
        copy_verified(b, dst)
        n += 1

    # Ranges that were written over in place come back from the bytes they
    # displaced -- 16 MB kept in Backup rather than a copy of a 1.8 GB archive.
    for step in plan:
        rel = "Res_x64/" + os.path.basename(step["archive"])
        total += 1
        if revert_step(game, backup, step):
            print("  restoring %s  [%s]" % (rel, step["entry"]))
            n += 1
            continue
        # an older build replaced that archive wholesale; its backup still works
        b = os.path.join(backup, os.path.basename(step["archive"]))
        if os.path.isfile(b) and os.path.isfile(os.path.join(game, rel)):
            print("  restoring %s (from a full backup)" % rel)
            copy_verified(b, os.path.join(game, rel))
            n += 1
        else:
            print("  no backup of %s" % rel)
            missing += 1

    print("\nRestored %d of %d." % (n, total))
    if missing:
        print("%d had no backup. Use Steam's \"Verify integrity of game files\"\n"
              "to get clean copies of those." % missing)
        return 1
    return 0


def do_verify(game, built, known, plan=(), payload=PAYLOAD):
    print("What is in the game folder now:\n")
    for name, rel in payload:
        dst = os.path.join(game, rel)
        if not os.path.exists(dst):
            print("  %-26s missing" % rel)
            continue
        h = sha256(dst)
        if name in built and h == sha256(built[name]):
            state = "patched (matches this build)"
        elif h in known:
            state = "original, %s" % known[h][0]
        else:
            state = "unrecognised (%s...)" % h[:12]
        print("  %-26s %-10s %s" % (rel, human(os.path.getsize(dst)), state))
    for step in plan:
        rel = "Res_x64/" + os.path.basename(step["archive"])
        target = os.path.join(game, rel)
        if not os.path.isfile(target):
            print("  %-26s missing" % rel)
            continue
        h = hashlib.sha256(read_range(target, step["offset"], step["size"])).hexdigest()
        if h == step["sha256_after"]:
            state = "patched (matches this build)"
        elif h == step["sha256_before"]:
            state = "original"
        else:
            state = "unrecognised (%s...)" % h[:12]
        print("  %-26s %-10s %s  [%s]"
              % (rel, human(step["size"]), state, step["entry"]))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--game", help="the game folder (found automatically if omitted)")
    ap.add_argument("--from", dest="build", default=os.path.join(ROOT, "build"),
                    help="the build to install (default: build/)")
    ap.add_argument("--data", default=os.path.join(ROOT, "data"))
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--restore", action="store_true")
    ap.add_argument("--verify", action="store_true")
    runlog.add_argument(ap)
    progress.add_arguments(ap)
    ap.add_argument("--done", help="write the exit code here when finished")
    ap.add_argument("--force", action="store_true",
                    help="install even though a file is not a version this "
                         "patch was built for")
    a = ap.parse_args(argv)
    runlog.start(a.log, "install.py")
    progress.from_args(a)
    progress.label("正在备份并安装")

    try:
        game = gamepath.resolve(a.game)
    except gamepath.NotFound as e:
        raise SystemExit(str(e))
    backup = os.path.join(game, "Backup")
    known = known_versions(a.data)
    built = find_built(a.build)
    plan = load_plan(a.build)
    # For undoing an install, what Backup/ records beats what a build tree
    # happens to contain -- and after a real install the build tree is gone.
    if a.restore or a.verify:
        plan = load_applied_plan(backup) or plan
    # An archive covered by the in-place plan is not replaced wholesale.
    inplace_rel = {"Res_x64/" + os.path.basename(st["archive"]) for st in plan}
    payload = [(n, r) for n, r in PAYLOAD if r not in inplace_rel]

    print("game    %s" % game)
    print("backup  %s" % backup)

    if a.restore:
        return do_restore(game, backup, plan)
    if a.verify:
        return do_verify(game, built, known, plan, payload)

    print("build   %s\n" % os.path.abspath(a.build))
    missing = [rel for name, rel in payload if name not in built]
    if missing:
        print("The build is incomplete -- these are missing:")
        for rel in missing:
            print("  %s" % rel)
        print("\nBuild it first:\n  py -3 tools/build.py")
        return 1

    # Refuse to work on files this patch was not built for.  Getting this
    # wrong means replacing an archive from a different version of the game,
    # which the player would then have to reinstall.
    problems = []
    for name, rel in payload:
        dst = os.path.join(game, rel)
        if not os.path.exists(dst):
            problems.append("%s is not there at all" % rel)
            continue
        h = sha256(dst)
        b = os.path.join(backup, os.path.basename(rel))
        if h == sha256(built[name]):
            print("  %-26s already this build" % rel)
            continue
        if h in known:
            print("  %-26s %-10s -> %s" % (rel, human(os.path.getsize(built[name])),
                                           "original, will back up first"
                                           if not os.path.exists(b) else
                                           "original, backup already kept"))
        elif os.path.exists(b) and sha256(b) in known:
            print("  %-26s %-10s -> patched by an earlier version; the original "
                  "is safe in Backup" % (rel, human(os.path.getsize(built[name]))))
        else:
            problems.append("%s is not a version this patch knows (%s...)"
                            % (rel, h[:12]))

    for step in plan:
        rel = "Res_x64/" + os.path.basename(step["archive"])
        target = os.path.join(game, rel)
        if not os.path.isfile(target):
            problems.append("%s is not there at all" % rel)
            continue
        h = hashlib.sha256(read_range(target, step["offset"], step["size"])).hexdigest()
        if h == step["sha256_after"]:
            print("  %-26s already this build  [%s]" % (rel, step["entry"]))
        elif h == step["sha256_before"]:
            print("  %-26s %-10s -> written in place, not rebuilt "
                  "(backs up %s, not the whole %s)"
                  % (rel, human(step["size"]), human(step["size"]),
                     human(os.path.getsize(target))))
        elif os.path.isfile(backup_name(backup, step)):
            print("  %-26s %-10s -> patched by an earlier version; the original "
                  "bytes are safe in Backup" % (rel, human(step["size"])))
        else:
            problems.append("%s: the bytes at offset %d are not what this patch "
                            "expects (%s...)" % (rel, step["offset"], h[:12]))

    for d in STALE:
        if os.path.isdir(os.path.join(game, d)):
            print("  will remove stale loose files: %s" % d)

    if problems:
        print("\nStopping without changing anything:")
        for p in problems:
            print("  - %s" % p)
        print("\nThis patch is built for the game versions listed in\n"
              "data/game-versions.csv. If yours is newer, please open an issue\n"
              "rather than forcing it: an archive from a different build will\n"
              "not load. If you are certain, --force overrides this.")
        if not a.force:
            return 1

    if not a.apply:
        print("\nThis was a dry run. Add --apply to install.")
        return 0

    os.makedirs(backup, exist_ok=True)
    done, done_steps = [], []
    try:
        for step in plan:
            if apply_step(game, backup, step):
                print("patched %s in place" % step["entry"])
                done_steps.append(step)
        for name, rel in payload:
            dst = os.path.join(game, rel)
            b = os.path.join(backup, os.path.basename(rel))
            # only ever back up something that is actually an original
            if not os.path.exists(b) and os.path.exists(dst) and sha256(dst) in known:
                print("backing up %s" % rel)
                copy_verified(dst, b)
            print("installing %s" % rel)
            copy_verified(built[name], dst)
            done.append(rel)
        for d in STALE:
            p = os.path.join(game, d)
            if os.path.isdir(p):
                shutil.rmtree(p)
                print("removed stale %s" % d)
        # Written last, once everything above has succeeded: this is the file
        # the uninstaller reads, and it must describe an install that happened.
        save_plan(backup, plan)
    except Exception as e:
        print("\nSomething went wrong: %s" % e)
        print("Putting back what had already been replaced ...")
        for step in done_steps:
            try:
                if revert_step(game, backup, step):
                    print("  restored %s" % step["entry"])
            except Exception as e2:
                print("  could not restore %s: %s" % (step["entry"], e2))
        for rel in done:
            b = os.path.join(backup, os.path.basename(rel))
            if os.path.isfile(b):
                try:
                    copy_verified(b, os.path.join(game, rel))
                    print("  restored %s" % rel)
                except Exception as e2:
                    print("  could not restore %s: %s" % (rel, e2))
        print("\nThe game has been left as it was. If it still misbehaves, run\n"
              "  py -3 tools/install.py --restore")
        return 1

    print("\nInstalled. Start the game from the usual launcher.")
    print("To undo this at any time:\n  py -3 tools/install.py --restore")
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
