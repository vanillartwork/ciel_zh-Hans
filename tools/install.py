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
import newfiles

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


def range_state(game, st):
    """What is in the byte range one installed plan step describes.

    'original'  the bytes that were there before that step -- nothing to undo
    'patched'   still that build's own output
    'unknown'   neither, or it cannot be read

    Three states, not two.  Treating "not the old output" as "already restored"
    let a range somebody had edited through as though it were pristine: the
    install went ahead, --restore reported success, and the archive kept the
    edited bytes.  When before and after are the same the step wrote what was
    already there, and 'original' is the right answer.
    """
    target = os.path.join(game, "Res_x64", os.path.basename(st["archive"]))
    if not os.path.isfile(target):
        return "unknown"
    try:
        blob = read_range(target, int(st["offset"]), int(st["size"]))
    except OSError:
        return "unknown"
    if len(blob) != int(st["size"]):
        return "unknown"
    cur = hashlib.sha256(blob).hexdigest()
    if cur == st.get("sha256_before"):
        return "original"
    if cur == st.get("sha256_after"):
        return "patched"
    return "unknown"


def stranded_ranges(game, applied, new_plan):
    """(step, state) for each installed range a new plan would abandon.

    Installing writes only its own ranges and then replaces Backup/inplace.json,
    so a build that patches a different offset leaves the previous build's bytes
    in the archive with nothing left pointing at them.  --restore then reverts
    the new range, finds nothing else to do, and reports success -- with the old
    translation still in the archive.

    Migrating between layouts means undoing the old ranges and writing the new
    ones as one transaction, including where they overlap.  Until that exists,
    this is what says so out loud instead of quietly getting it wrong.

    A range that is back to its original bytes -- a plan left in Backup/ after a
    --restore -- abandons nothing and is not reported.  Anything else is,
    including a range in a state neither build can explain.
    """
    keep = {(os.path.basename(st["archive"]), int(st["offset"]), int(st["size"]))
            for st in new_plan}
    out = []
    for st in applied:
        key = (os.path.basename(st["archive"]), int(st["offset"]), int(st["size"]))
        if key in keep:
            continue
        state = range_state(game, st)
        if state != "original":
            out.append((st, state))
    return out


def layout_refusals(game, backup, new_plan):
    """Why this build cannot be installed over the one already there."""
    out = []
    for st, state in stranded_ranges(game, load_applied_plan(backup), new_plan):
        where = "%s at offset %d (%s)" % (os.path.basename(st["archive"]),
                                          int(st["offset"]),
                                          st.get("entry", "?"))
        if state == "patched":
            out.append(
                "the patch already installed writes %s, and this build does not "
                "touch that range.\n"
                "    Installing over it would leave those bytes in the archive "
                "with nothing left to undo them.\n"
                "    Take the installed patch out first:  py -3 tools/install.py "
                "--restore" % where)
        else:
            out.append(
                "the range the installed patch wrote at %s holds neither those "
                "bytes nor the original ones.\n"
                "    Something else has changed it, so there is no way to say "
                "what installing over it would leave behind.\n"
                "    Put the originals back first:  py -3 tools/install.py "
                "--restore\n"
                "    If that is not enough, verify the game files in Steam "
                "(Properties -> Installed Files)." % where)
    return out


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


def read_manifest(build_dir):
    """The build's own account of itself: version, and whether the display layer
    is part of it.

    The installer used to reach for a --version argument that does not exist,
    which made the real entry point fail with an AttributeError while the tests,
    which never called it, passed.  The version belongs to the build, so it is
    read from the build.
    """
    p = os.path.join(build_dir, "manifest.json")
    if not os.path.exists(p):
        raise SystemExit(
            "%s has no manifest.json, so there is no way to tell which build "
            "this is.\n  Build it first:\n    py -3 tools/build.py" % build_dir)
    with io.open(p, encoding="utf-8") as f:
        m = json.load(f)
    if not m.get("patch_version"):
        raise SystemExit("%s does not say which version it is" % p)
    if "loader_enabled" not in m:
        raise SystemExit(
            "%s was made by an older build and does not say whether the display "
            "layer is included.\n  Rebuild with this version of tools/build.py."
            % p)
    return m


def find_built(build_dir):
    """Locate each payload file in a build tree, plus the files we create."""
    found = {}
    for name, _ in list(PAYLOAD) + list(newfiles.CREATED):
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


def refuse_if_running(force=False):
    """0 to go ahead, 1 to stop.  Shared by install and restore.

    "Cannot tell" is not "not running": a query that fails used to be reported
    as stopped, which left the check covering only the cases where it worked.
    """
    state = newfiles.running_state()
    if state == "running":
        print("\nThe game is running. Quit it and try again; nothing was "
              "changed.")
        return 1
    if state == "unknown":
        if not force:
            print("\nCould not tell whether the game is running (tasklist did "
                  "not answer).\n  Quit the game and try again, or pass --force "
                  "if you are sure it is closed.\n  Nothing was changed.")
            return 1
        print("  could not confirm the game is closed; continuing because "
              "--force was given")
    return 0


RUN_RECORDS = ("cielzh-loader.log", "cielzh-status.txt")


def do_restore(game, backup, plan=()):
    if not os.path.isdir(backup):
        print("There is no Backup folder at %s.\n"
              "Nothing to restore from. In Steam, right-click the game ->\n"
              "Properties -> Installed Files -> Verify integrity of game files."
              % backup)
        return 1
    # Recovery data comes first: an install that stopped partway has to be undone
    # before the originals go back, and one that finished without tidying up
    # would otherwise leave its copies in Backup/ for good.
    try:
        tx = newfiles.load_tx(backup)
    except newfiles.Stop as e:
        print("  %s" % e)
        return 1
    if newfiles.committed(tx):
        print("  tidying up after an install that finished but did not clean up")
        newfiles.cleanup(backup)
    elif tx:
        print("  undoing an install that stopped partway, first ...")
        if not newfiles.roll_back(game, backup, tx):
            print("\nCould not undo it; nothing was restored.")
            return 1
        # That rollback may have put an older Backup/inplace.json back, and it is
        # the plan that says which byte ranges to revert.  Restoring against the
        # plan read before the rollback reverted ranges the archives no longer
        # held, and said it had succeeded.
        plan = load_applied_plan(backup) or plan

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

    removed, left = newfiles.remove_all(game, backup)
    if removed or left:
        total += removed + left
        n += removed
    # What the loader entry and the DLL wrote at each start.  Once the DLL is
    # gone they describe a patch that is no longer there, and --verify would
    # go on reporting a failed start for a game that is simply original.
    if not os.path.exists(os.path.join(game, "cielzh.dll")):
        for name in RUN_RECORDS:
            p = os.path.join(game, name)
            if os.path.exists(p):
                os.remove(p)

    print("\nRestored %d of %d." % (n, total))
    if missing:
        print("%d had no backup. Use Steam's \"Verify integrity of game files\"\n"
              "to get clean copies of those." % missing)
        return 1
    return 0


def do_verify(game, built, known, plan=(), payload=PAYLOAD, backup=None):
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
    # The files this patch adds, which have no original to compare against --
    # only what we recorded installing.  Leaving them out meant the one file a
    # reader most wants to check, a freshly built DLL, was the one --verify never
    # mentioned.
    rec = {}
    if backup:
        try:
            rec = newfiles.load_record(backup).get("files", {})
        except newfiles.Stop as e:
            print("  (the ownership record cannot be read: %s)" % e)
    for name, rel in newfiles.CREATED:
        dst = os.path.join(game, rel)
        known_here = rec.get(rel)
        if not os.path.exists(dst):
            print("  %-26s %-10s %s"
                  % (rel, "", "not installed"
                     if known_here is None else "MISSING (we installed it)"))
            continue
        h = sha256(dst)
        if name in built and h == sha256(built[name]):
            state = "matches this build"
        elif known_here and h == known_here.get("installed_sha256"):
            state = "installed by %s" % known_here.get("patch_version")
        elif known_here:
            state = "changed since we installed it (%s...)" % h[:12]
        else:
            state = "not ours -- no record of installing it (%s...)" % h[:12]
        print("  %-26s %-10s %s"
              % (rel, human(os.path.getsize(dst)), state))
    print("\n" + display_status(game))
    return 0


def display_status(game):
    """What the last start of the game made of the display layer, in a line.

    Two records beside the executable: the loader entry's own log (did the DLL
    load at all) and the DLL's status file (did the hooks go in, was the table
    read).  The patched executable shows its own Chinese either way, so without
    these a display layer that never ran looks like a complete patch.
    """
    dll = os.path.join(game, "cielzh.dll")
    log = os.path.join(game, "cielzh-loader.log")
    status = os.path.join(game, "cielzh-status.txt")
    if not os.path.exists(dll):
        # The patched executable still looks for it: a DLL that antivirus
        # quarantined or that was deleted shows up as "missing" in the log the
        # loader entry writes on every start.
        try:
            loader = io.open(log, encoding="utf-8", errors="replace").read().strip()
        except OSError:
            loader = ""
        if "loader=missing" in loader:
            return ("display layer: NOT LOADED at the last start -- cielzh.dll is "
                    "missing (%s); names, the save summary and memos show Japanese. "
                    "Reinstall the patch, and check whether antivirus removed it"
                    % loader)
        return "display layer: not installed"
    if not os.path.exists(log) or os.path.getmtime(log) < os.path.getmtime(dll):
        return ("display layer: not checked yet -- start the game once, then "
                "run --verify again")
    try:
        loader = io.open(log, encoding="utf-8", errors="replace").read().strip()
    except OSError as e:
        return "display layer: cannot read %s (%s)" % (os.path.basename(log), e)
    if "loader=rc=" not in loader:
        return ("display layer: NOT LOADED at the last start (%s); names, the "
                "save summary and memos show Japanese" % loader)
    fields = {}
    if os.path.exists(status) and os.path.getmtime(status) >= os.path.getmtime(dll):
        for line in io.open(status, encoding="utf-8", errors="replace"):
            k, _, v = line.strip().partition("=")
            fields[k] = v
    if not fields:
        return ("display layer: loaded, but it left no status (%s); check "
                "that the game folder is writable" % loader)
    if fields.get("rc") != "0":
        return ("display layer: NOT ACTIVE at the last start (rc=%s: %s); "
                "names, the save summary and memos show Japanese"
                % (fields.get("rc"), fields.get("why")))
    if fields.get("display") != "on" or fields.get("entries", "0") == "0":
        return ("display layer: running, but its text table was not used (%s); "
                "names, the save summary and memos show Japanese"
                % fields.get("why"))
    return "display layer: active at the last start, %s strings" % fields["entries"]


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
    progress.label("正在备份游戏文件并安装补丁")

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
        code = refuse_if_running(a.force)
        if code:
            return code
        return do_restore(game, backup, plan)
    if a.verify:
        return do_verify(game, built, known, plan, payload, backup)

    manifest = read_manifest(a.build)
    version = manifest["patch_version"]
    loader_enabled = bool(manifest["loader_enabled"])
    # Two kinds of problem.  `problems` are about which build of the game this
    # is: a judgement the player is allowed to overrule with --force.
    # `blockers` are about our own files -- an unrecognised cielzh.dll, a
    # transaction that cannot be explained, a build missing the DLL it says it
    # needs.  --force used to skip those too, which installed a loader-enabled
    # executable beside an unknown DLL and recorded nothing.
    blockers = []
    print("build   %s  (%s, display layer %s)\n"
          % (os.path.abspath(a.build), version,
             "included" if loader_enabled else "left out"))
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

    # Files we create rather than replace, planned here -- during the dry run,
    # before a single byte is committed.  Doing this after the executable had
    # been replaced meant an unknown DLL stopped the run halfway, and the
    # rollback put back the ORIGINAL executable rather than the one that was
    # there when the run started: neither "nothing changed" nor "back as it was".
    # An interrupted install is described here and undone later, under --apply
    # and only after the running check.  Recovering during the dry run wrote
    # created.json and deleted the transaction, so "this was a dry run" was not
    # true and the running check had not been reached yet.
    pending_tx = stale_tx = None
    found_tx = None
    try:
        found_tx = newfiles.load_tx(backup)
    except newfiles.Stop as e:
        blockers.append(str(e))
    if newfiles.committed(found_tx):
        # phase=done is the commit point: that install happened, and only its
        # recovery files are left.  Undoing it here deleted the DLL it had just
        # installed -- the copies were already gone, and "there is no copy" was
        # read as "we created this file".
        stale_tx = found_tx
        print("  an install of %s finished but did not get to tidy up; its "
              "recovery files will be removed" % found_tx.get("patch_version"))
        for rel in newfiles.verify_committed(game, found_tx):
            print("      note: %s is no longer what that install left behind"
                  % rel)
    elif found_tx:
        pending_tx = found_tx
        d = newfiles.describe(pending_tx)
        print("  an install of %s stopped partway (%s); it will be undone first"
              % (d["version"], d["started"]))
        for st in d["done"]:
            print("      done:    %s %s" % (st["kind"], st["rel"]))
        for st in d["pending"]:
            print("      not done: %s %s" % (st["kind"], st["rel"]))

    # The ownership plan and the layout check are both worked out against the
    # state as it will be once that rollback has happened, without writing
    # anything now.  A committed transaction changes nothing, so it does not hold
    # either of them up.
    #
    # Deciding the layout before the rollback was wrong in both directions: it
    # let a build through on the strength of a plan the rollback was about to
    # replace, and it refused one that the rollback would have made installable.
    created_rec, created_actions = None, []
    if pending_tx:
        print("  the ranges this build writes are checked against the installed\n"
              "  patch after that is undone, which is when it can be decided")
    else:
        try:
            created_rec, created_actions = newfiles.plan(
                game, backup, built, version, loader_enabled)
        except newfiles.Stop as e:
            blockers.append(str(e))
        blockers.extend(layout_refusals(game, backup, plan))

    for d in STALE:
        if os.path.isdir(os.path.join(game, d)):
            print("  will remove stale loose files: %s" % d)

    if blockers:
        print("\nStopping without changing anything:")
        for p in blockers:
            print("  - %s" % p)
        print("\nThese are about files this patch installs, not about which\n"
              "version of the game you have, so --force does not apply.")
        return 1

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

    # Replacing files the game has mapped cannot work, and a half-replaced
    # install is worse than none.
    code = refuse_if_running(a.force)
    if code:
        return code

    os.makedirs(backup, exist_ok=True)

    # The separate phase journal is gone: the transaction carries both what was
    # planned and what was reached, and a second record of the same thing could
    # only disagree with it.

    # A committed transaction that never got tidied up: finish the tidying, and
    # do it before the new transaction is written, not after.
    if stale_tx:
        print("\nTidying up after the install that already finished ...")
        newfiles.cleanup(backup)

    # Undo an interrupted install first, now that --apply is confirmed and the
    # game is known to be closed.
    if pending_tx:
        print("\nUndoing the install that stopped partway ...")
        if not newfiles.roll_back(game, backup, pending_tx):
            print("\nCould not undo it completely. Nothing further was changed;\n"
                  "the records are still in Backup/ for another attempt.")
            return 1
        # Both checks run again here, against the state the rollback produced --
        # which is a consistent one, so stopping now changes nothing further.
        try:
            created_rec, created_actions = newfiles.plan(
                game, backup, built, version, loader_enabled)
        except newfiles.Stop as e:
            print("\nAfter undoing it: %s" % e)
            return 1
        stops = layout_refusals(game, backup, plan)
        if stops:
            print("\nThat install was undone. This build cannot be installed "
                  "over what is there now:")
            for p in stops:
                print("  - %s" % p)
            return 1

    txn = newfiles.Txn(game, backup, version)

    # Every step's undo information is gathered BEFORE the first change and
    # thrown away only once the whole install has succeeded.  Per-file cleanup
    # meant a later failure found the earlier steps already tidied up, leaving
    # Backup/ -- which holds the original -- as the only thing to restore from.
    # The created files are registered here as well, not inside apply_one.
    # Adding a step on the way past left the DLL replaced while the transaction
    # on disk still said nothing about it, so a process killed there came back as
    # "old executable, new DLL, old record" -- and the transaction was deleted.
    try:
        for step in plan:
            rel = "Res_x64/" + os.path.basename(step["archive"])
            target = os.path.join(game, rel)
            if os.path.isfile(target):
                cur = read_range(target, step["offset"], step["size"])
                if hashlib.sha256(cur).hexdigest() != step["sha256_after"]:
                    txn.add_range_copy("range", rel,
                                       hashlib.sha256(cur).hexdigest(),
                                       step["sha256_after"], cur,
                                       extra={"offset": step["offset"],
                                              "size": step["size"]})
        for name, rel in payload:
            dst = os.path.join(game, rel)
            if os.path.exists(dst):
                txn.add("payload", rel, sha256(dst), sha256(built[name]),
                        save_path=dst)
        # Backup/inplace.json is what --restore reads to find the byte ranges it
        # has to put back.  It was written outside the transaction, so a failed
        # upgrade left the archives at the old version and the restore plan at
        # the new one.  If the two builds patch different offsets, --restore then
        # reverted a range nobody had written and reported success, leaving the
        # old build's bytes in the archive.
        if plan:
            prel = "Backup/" + PLAN
            pfile = os.path.join(backup, PLAN)
            had = sha256(pfile) if os.path.isfile(pfile) else None
            txn.add("backup_file", prel, had, None,
                    save_path=pfile if had else None)
        newfiles.register(txn, created_actions)
    except (newfiles.Stop, OSError) as e:
        # Nothing has been touched yet: add() only reads the game folder and
        # writes copies of its own.
        print("\nStopping without changing anything: %s" % e)
        newfiles.cleanup(backup, report=lambda _m: None)
        return 1
    txn.begin()

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
            # Already this build: the dry run says so, and writing it again
            # anyway made the report and the action disagree -- 50 MB of copying
            # to produce the bytes that were already there.
            if os.path.exists(dst) and sha256(dst) == sha256(built[name]):
                print("%s is already this build" % rel)
            else:
                print("installing %s" % rel)
                copy_verified(built[name], dst)
            done.append(rel)
        for st in txn.data["steps"]:
            if st["kind"] in ("range", "payload"):
                txn.mark(st)

        # Planned before anything was committed; re-checked inside apply_one.
        for act in created_actions:
            newfiles.apply_one(game, backup, created_rec, act, version, txn)

        # Written last, once everything above has succeeded: this is the file
        # the uninstaller reads, and it must describe an install that happened.
        save_plan(backup, plan)
        # Last: the rollback copies go only once everything above is in place.
        txn.finish(report=print)
    except Exception as e:
        print("\nSomething went wrong: %s" % e)
        print("Putting the game back the way it was before this install ...")
        ok = False
        try:
            ok = newfiles.roll_back(game, backup, txn.data,
                                    report=lambda m: print(m))
        except Exception as e2:
            print("  could not undo this install: %s" % e2)
        if ok:
            print("\nThe game is back to what it was before this install.")
        else:
            print("\nCould not undo everything. Backup/%s and %s are still\n"
                  "there; run the installer again and it will finish undoing\n"
                  "this attempt first."
                  % (newfiles.ROLLBACK_DIR, newfiles.TX))
        return 1

    # After the commit point, so tidying only.  These are loose files left over
    # from an older way of installing; the engine ignores them, so failing to
    # remove them is worth saying and is not worth undoing a working install
    # for.  Inside the transaction they would have been an unrecorded change --
    # deleted on the way in and not put back on the way out.
    for d in STALE:
        p = os.path.join(game, d)
        if os.path.isdir(p):
            try:
                shutil.rmtree(p)
                print("removed stale %s" % d)
            except OSError as e:
                print("could not remove the stale %s folder (%s); it is ignored "
                      "by the game and can be deleted by hand" % (d, e))

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
