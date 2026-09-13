# -*- coding: utf-8 -*-
"""Merge the repository's translations onto text freshly read from the game.

  py -3 merge_repo.py <repo data dir> <export dir> [--strict]

export_text.py produces a tree with the Japanese in it and `zh` empty; this
fills `zh` in from `data/`, matching on the stable id.  Only the translation
travels: the ids, the Japanese and every technical column stay as the game
produced them, so nothing the repository says can talk the build into
believing a row is something it is not.

A row whose source hash no longer matches is left untranslated rather than
guessed at.  That is the whole point of carrying the hash: if the game is a
version this patch was not made for, the build says so instead of splicing a
translation into the wrong line.
"""
import sys, os, io, csv, argparse, glob

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from repo_export import src_hash

PAIRS = [
    ("ui.csv", "ui_text.csv"),
    ("items.csv", "item_text.csv"),
    ("global.csv", "global_text.csv"),
    ("executable.csv", "exe_text.csv"),
    ("terms-in-text.csv", "glossary_terms.csv"),
    ("speakers.csv", "glossary_speakers.csv"),
]


def read(path):
    with io.open(path, encoding="utf-8-sig", newline="") as f:
        rd = csv.DictReader(f)
        return list(rd), rd.fieldnames


def merge_one(repo_path, exp_path, report):
    repo, _ = read(repo_path)
    exp, cols = read(exp_path)
    trans = {r["id"]: r for r in repo if r.get("zh", "").strip()}
    # Rows left untranslated on purpose carry the reason in `note`. That reason
    # is project data, not something the extractor can regenerate, and
    # patch_exe_strings.py refuses to run without it -- so it has to travel too.
    skipped = {r["id"]: r.get("note", "") for r in repo
               if not r.get("zh", "").strip() and r.get("note", "").strip()}

    filled = drift = 0
    for r in exp:
        rid = r.get("key") or r.get("uid")
        if rid in skipped and "note" in r:
            r["note"] = skipped[rid]
        t = trans.get(rid)
        if t is None:
            continue
        if t.get("src") and src_hash(r.get("jp", "")) != t["src"]:
            drift += 1
            report.append("%s: %s -- source text differs from what the "
                          "translation was written against" %
                          (os.path.basename(exp_path), rid))
            continue
        r["zh"] = t["zh"]
        filled += 1

    with io.open(exp_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, lineterminator="\r\n")
        w.writeheader()
        w.writerows(exp)
    return filled, drift, len(trans)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("data")
    ap.add_argument("export")
    ap.add_argument("--strict", action="store_true",
                    help="stop if any row has drifted")
    a = ap.parse_args(argv)

    zh = os.path.join(a.data, "zh-Hans")
    report = []
    filled = drift = available = 0

    jobs = []
    sd = os.path.join(zh, "script")
    if os.path.isdir(sd):
        for fn in sorted(os.listdir(sd)):
            if fn.endswith(".csv"):
                jobs.append((os.path.join(sd, fn),
                             os.path.join(a.export, "script", fn)))
    for repo_name, exp_name in PAIRS:
        rp = os.path.join(zh, repo_name)
        ep = os.path.join(a.export, exp_name)
        if os.path.exists(rp) and os.path.exists(ep):
            jobs.append((rp, ep))

    for rp, ep in jobs:
        if not os.path.exists(ep):
            report.append("%s: your game produced no matching file"
                          % os.path.basename(rp))
            continue
        f, d, n = merge_one(rp, ep, report)
        filled += f
        drift += d
        available += n

    print("merged %s of %s translations into %d files"
          % (format(filled, ","), format(available, ","), len(jobs)))
    if drift:
        share = drift / float(available or 1)
        print("%d rows (%.1f%%) did not match the text in your game and were "
              "left untranslated:" % (drift, share * 100))
        for line in report[:15]:
            print("  %s" % line)
        if len(report) > 15:
            print("  ... %d more" % (len(report) - 15))
        # A handful of mismatches means a few lines moved.  A large share means
        # the text being read is not the original Japanese at all -- nearly
        # always an installation the patch has already been applied to, where
        # the extractor is reading back this project's own Chinese.
        if share > 0.02:
            print("\nThat is far too many for ordinary drift. The usual cause is "
                  "that\nthe game folder is already patched, so the Japanese is no "
                  "longer\nthere to read. Restore it first:\n"
                  "    py -3 tools/install.py --restore\n"
                  "or let Steam verify the game files, then build again.\n"
                  "If the game really is a different version, see "
                  "docs/supported-versions.md.")
            return 1
        if a.strict:
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
