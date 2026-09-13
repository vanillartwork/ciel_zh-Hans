# -*- coding: utf-8 -*-
"""One source string, one translation -- for everything except dialogue.

  py -3 unify_dupes.py <export dir> [--apply]

Menu labels, item data, help text and glossary entries repeat verbatim across
files (49% of the non-dialogue rows are duplicates).  When those get split
across translation batches they come back worded differently, and the player
sees the same entry under two names.

Dialogue is deliberately left alone: the same line can and should read
differently in different scenes.

Pick order for the canonical wording:
  1. the official Koei Tecmo Taiwan glossary, if it covers the source string
  2. the variant used in the most rows
  3. the shorter variant (menu labels are usually tighter)
"""
import sys, os, io, csv, collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from official_glossary import OFFICIAL
    OFF = {o[0]: o[2] for o in OFFICIAL}
except Exception:
    OFF = {}


def is_dialog(rel, row):
    return rel.startswith("script/") and row.get("kind") == "dialog"


def main(argv):
    exportdir = argv[1]
    apply = "--apply" in argv
    files = {}
    groups = collections.defaultdict(list)
    for root, _, fs in os.walk(exportdir):
        for fn in sorted(fs):
            if not fn.endswith(".csv") or fn.startswith("_"):
                continue
            p = os.path.join(root, fn)
            rel = os.path.relpath(p, exportdir).replace(os.sep, "/")
            with io.open(p, encoding="utf-8-sig", newline="") as f:
                rd = csv.DictReader(f)
                files[rel] = (p, rd.fieldnames, list(rd))
            for r in files[rel][2]:
                if r.get("zh", "").strip() and not is_dialog(rel, r):
                    groups[r["jp"]].append((rel, r))
    bad = {k: v for k, v in groups.items()
           if len({r["zh"] for _, r in v}) > 1}
    print("non-dialogue source strings with more than one translation: %d" % len(bad))
    changes = 0
    for jp, rows in sorted(bad.items()):
        counts = collections.Counter(r["zh"] for _, r in rows)
        official = OFF.get(jp)
        if official and official in counts:
            best, why = official, "official"
        elif official:
            best, why = official, "official (was not used anywhere)"
        else:
            top = counts.most_common()
            most = top[0][1]
            tied = sorted([z for z, n in top if n == most], key=len)
            best, why = tied[0], "majority" if len(tied) == 1 else "shortest of tied"
        print("\n  %r  (%d rows)" % (jp[:44], len(rows)))
        for z, n in counts.most_common():
            print("     %-46r x%d%s" % (z[:44], n, "   <= keep [%s]" % why if z == best else ""))
        for rel, r in rows:
            if r["zh"] != best:
                r["zh"] = best
                changes += 1
    print("\n%d cells %s" % (changes, "rewritten" if apply else "would change (dry run)"))
    if apply:
        for rel, (p, cols, rows) in files.items():
            with io.open(p, "w", encoding="utf-8-sig", newline="") as f:
                cw = csv.DictWriter(f, fieldnames=cols, lineterminator="\r\n")
                cw.writeheader()
                cw.writerows(rows)


if __name__ == "__main__":
    main(sys.argv)
