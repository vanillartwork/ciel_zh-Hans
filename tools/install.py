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
import sys, os, io, csv, shutil, hashlib, argparse, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import gamepath

# what the patch replaces: (built file, path inside the game folder)
PAYLOAD = [
    ("CielnosurgeDX.exe", "CielnosurgeDX.exe"),
    ("PACK01.PAK", "Res_x64/PACK01.PAK"),
    ("PACK00_01.PAK", "Res_x64/PACK00_01.PAK"),
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


def do_restore(game, backup):
    if not os.path.isdir(backup):
        print("There is no Backup folder at %s.\n"
              "Nothing to restore from. In Steam, right-click the game ->\n"
              "Properties -> Installed Files -> Verify integrity of game files."
              % backup)
        return 1
    n = missing = 0
    for name, rel in PAYLOAD:
        b = os.path.join(backup, os.path.basename(rel))
        dst = os.path.join(game, rel)
        if not os.path.isfile(b):
            print("  no backup of %s" % rel)
            missing += 1
            continue
        print("  restoring %s" % rel)
        copy_verified(b, dst)
        n += 1
    print("\nRestored %d of %d files." % (n, len(PAYLOAD)))
    if missing:
        print("%d had no backup. Use Steam's \"Verify integrity of game files\"\n"
              "to get clean copies of those." % missing)
        return 1
    return 0


def do_verify(game, built, known):
    print("What is in the game folder now:\n")
    for name, rel in PAYLOAD:
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
    ap.add_argument("--force", action="store_true",
                    help="install even though a file is not a version this "
                         "patch was built for")
    a = ap.parse_args(argv)

    try:
        game = gamepath.resolve(a.game)
    except gamepath.NotFound as e:
        raise SystemExit(str(e))
    backup = os.path.join(game, "Backup")
    known = known_versions(a.data)
    built = find_built(a.build)

    print("game    %s" % game)
    print("backup  %s" % backup)

    if a.restore:
        return do_restore(game, backup)
    if a.verify:
        return do_verify(game, built, known)

    print("build   %s\n" % os.path.abspath(a.build))
    missing = [rel for name, rel in PAYLOAD if name not in built]
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
    for name, rel in PAYLOAD:
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
    done = []
    try:
        for name, rel in PAYLOAD:
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
    except Exception as e:
        print("\nSomething went wrong: %s" % e)
        print("Putting back what had already been replaced ...")
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


if __name__ == "__main__":
    sys.exit(main())
