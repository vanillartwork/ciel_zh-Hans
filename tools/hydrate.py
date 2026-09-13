# -*- coding: utf-8 -*-
"""Make a working copy of the translation data outside git.

  py -3 hydrate.py [--game "<game folder>"] [--data data] [--out work]

The repository already holds the Japanese beside every translation, so you do
not need this to start translating -- you can edit `data/zh-Hans/**.csv`
directly. What this gives you is a copy under `work/`, which git ignores, so
you can reorganise, sort and bulk-edit without any of that showing up as a
change. `dehydrate.py` folds the edits back.

Pass `--game` and it will also read the Japanese out of your own installation
and compare: a row whose text differs from what the repository recorded is
reported rather than quietly accepted, which is how a game version the patch
was not built for gets noticed early.
"""
import sys, os, io, csv, argparse, tempfile, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from repo_export import src_hash

REPO_TO_EXPORT = {
    "ui.csv": "ui_text.csv",
    "items.csv": "item_text.csv",
    "global.csv": "global_text.csv",
    "executable.csv": "exe_text.csv",
    "terms-in-text.csv": "glossary_terms.csv",
    "speakers.csv": "glossary_speakers.csv",
}


def read(path):
    with io.open(path, encoding="utf-8-sig", newline="") as f:
        rd = csv.DictReader(f)
        return list(rd), rd.fieldnames


def game_text(game):
    """The Japanese this installation actually contains, keyed by id."""
    import export_text, export_exe_text
    tmp = tempfile.mkdtemp(prefix="cnl10n-")
    try:
        export_text.main(os.path.join(game, "Res_x64"), tmp)
        try:
            export_exe_text.main(tmp)
        except Exception as e:
            print("  (skipping executable strings: %s)" % e)
        out = {}
        for root, _, names in os.walk(tmp):
            for fn in names:
                if not fn.endswith(".csv") or fn.startswith("_"):
                    continue
                rows, _ = read(os.path.join(root, fn))
                for r in rows:
                    k = r.get("key") or r.get("uid")
                    if k:
                        out[k] = r.get("jp", "")
        return out
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--game", nargs="?", const="", default=None,
                    help="also check the data against your own copy of the game")
    ap.add_argument("--data", default="data")
    ap.add_argument("--out", default="work")
    a = ap.parse_args(argv)

    zh = os.path.join(a.data, "zh-Hans")
    if not os.path.isdir(zh):
        print("no data at %s" % zh)
        return 1

    theirs = None
    if a.game is not None:
        import gamepath
        try:
            game = gamepath.resolve(a.game or None)
        except gamepath.NotFound as e:
            print(e)
            return 1
        print("checking against %s ..." % game)
        theirs = game_text(game)

    files = rows = drift = missing = 0
    report = []
    for root, _, names in os.walk(zh):
        for fn in sorted(names):
            if not fn.endswith(".csv") or fn.startswith("_"):
                continue
            src = os.path.join(root, fn)
            rel = os.path.relpath(src, zh)
            data, cols = read(src)
            if theirs is not None:
                for r in data:
                    g = theirs.get(r["id"])
                    if g is None:
                        missing += 1
                        report.append("%s: %s is not in your game" % (rel, r["id"]))
                    elif r.get("src") and src_hash(g) != r["src"]:
                        drift += 1
                        report.append("%s: %s reads differently in your game"
                                      % (rel, r["id"]))
            dst = os.path.join(a.out, "zh-Hans", rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with io.open(dst, "w", encoding="utf-8-sig", newline="") as f:
                w = csv.DictWriter(f, fieldnames=cols, lineterminator="\n")
                w.writeheader()
                w.writerows(data)
            files += 1
            rows += len(data)

    print("%d files, %s rows -> %s" % (files, format(rows, ","),
                                       os.path.join(a.out, "zh-Hans")))
    print("Edit the `zh` column there, then: py -3 tools/dehydrate.py")
    if theirs is not None:
        if drift or missing:
            print("\n%d rows differ from your game, %d are not in it:" % (drift, missing))
            for line in report[:15]:
                print("  %s" % line)
            if len(report) > 15:
                print("  ... %d more" % (len(report) - 15))
            print("A few is normal drift. Many means your game is a different\n"
                  "version than this patch targets -- see docs/supported-versions.md.")
        else:
            print("Your copy of the game matches the repository exactly.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
