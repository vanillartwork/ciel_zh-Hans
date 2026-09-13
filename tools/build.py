# -*- coding: utf-8 -*-
"""Build the patch from the repository and your own copy of the game.

  py -3 tools/build.py [--game <folder>] [--out build] [--version 0.9.0]
                       [--skip-font] [--skip-validate] [--no-repack]

The repository holds translations, not game data, so a build starts from the
copy of the game you own:

  1. validate   the translation data, on its own
  2. extract    the Japanese out of your installation
  3. merge      the repository's translations onto it, by id and source hash
  4. font       rebuild the atlas and glyph table so Chinese can be drawn
  5. inject     splice the translations back into the data files, and
                translate the strings compiled into the executable
  6. repack     fold the result into copies of the archives
  7. manifest   record what was built, and the checksums for it

Each step stops at the first thing it cannot do rather than carrying on and
producing something half-patched.  Nothing here writes into the game folder;
that is install.py, which takes a backup first.
"""
import sys, os, io, csv, json, time, shutil, argparse, hashlib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import gamepath

TOTAL = 7


def step(n, title):
    print("\n[%d/%d] %s" % (n, TOTAL, title))
    sys.stdout.flush()


def stop(what, detail=""):
    raise SystemExit("\n%s failed.%s\nThe build stopped here; your game folder "
                     "has not been touched." % (what, ("\n" + detail) if detail else ""))


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--game", help="the game folder (found automatically if omitted)")
    ap.add_argument("--out", default="build")
    ap.add_argument("--data", default="data")
    ap.add_argument("--version", default="dev")
    ap.add_argument("--skip-font", action="store_true",
                    help="reuse the atlas already under --out")
    ap.add_argument("--skip-validate", action="store_true")
    ap.add_argument("--no-repack", action="store_true",
                    help="stop after staging; leaves the loose files only")
    a = ap.parse_args(argv)

    os.chdir(ROOT)
    try:
        game = gamepath.resolve(a.game)
    except gamepath.NotFound as e:
        raise SystemExit(str(e))
    res = os.path.join(game, "Res_x64")

    out = os.path.abspath(a.out)
    work = os.path.join(out, "work")
    fontdir = os.path.join(out, "font")
    stage = os.path.join(out, "stage")
    dist = os.path.join(out, "dist")
    for d in (out, work, fontdir, dist):
        os.makedirs(d, exist_ok=True)

    print("game      %s" % game)
    print("output    %s" % out)
    print("version   %s" % a.version)
    started = time.time()

    step(1, "checking the translation data")
    if a.skip_validate:
        print("  skipped at your request")
    else:
        import validate
        if validate.main(["--data", a.data]):
            stop("Validation", "Fix the errors above, then build again.")

    step(2, "reading the Japanese out of your copy of the game")
    import export_text, export_exe_text
    try:
        export_text.main(res, work)
        export_exe_text.main(work)
    except Exception as e:
        stop("Extraction", str(e))

    step(3, "merging in the repository's translations")
    import merge_repo
    if merge_repo.main([a.data, work]):
        stop("Merge")

    step(4, "building the font")
    if a.skip_font and os.path.exists(os.path.join(fontdir, "FOT-SKIPSTD-B_0.g1t")):
        print("  reusing the atlas already in %s" % fontdir)
    else:
        import build_font
        try:
            build_font.main(work, fontdir)
        except Exception as e:
            stop("Font build", str(e))

    step(5, "injecting the text and translating the executable")
    import build_patch
    if os.path.isdir(stage):
        shutil.rmtree(stage)
    try:
        build_patch.main(work, fontdir, stage)
    except SystemExit as e:
        stop("Injection", str(e.code))
    except Exception as e:
        stop("Injection", str(e))

    if a.no_repack:
        print("\nStopped before repacking, as asked.")
        return 0

    step(6, "repacking the archives")
    import repack_pak
    try:
        repack_pak.main(stage, dist)
    except Exception as e:
        stop("Repacking", str(e))

    step(7, "writing the manifest")
    files = []
    for root, _, names in os.walk(dist):
        for fn in sorted(names):
            p = os.path.join(root, fn)
            files.append({
                "path": os.path.relpath(p, dist).replace(os.sep, "/"),
                "bytes": os.path.getsize(p),
                "sha256": sha256(p),
            })
    exe = os.path.join(stage, "CielnosurgeDX.exe")
    if os.path.exists(exe):
        files.append({"path": "CielnosurgeDX.exe",
                      "bytes": os.path.getsize(exe), "sha256": sha256(exe)})
    # Record the *unpatched* executable this build was made from. Hashing the
    # one sitting in the game folder would record a previous patch's output
    # whenever the game is already patched, which is exactly when the manifest
    # would be consulted.
    from build_charset import pristine_exe
    manifest = {
        "patch_version": a.version,
        "built": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "built_from_game_exe_sha256": sha256(pristine_exe()),
        "files": files,
    }
    mp = os.path.join(out, "manifest.json")
    io.open(mp, "w", encoding="utf-8").write(
        json.dumps(manifest, ensure_ascii=False, indent=2))

    print("\nBuilt in %d seconds." % (time.time() - started))
    print("  archives   %s" % dist)
    print("  executable %s" % exe)
    print("  manifest   %s" % mp)
    print("\nInstall it with:\n  py -3 tools/install.py --apply --from %s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
