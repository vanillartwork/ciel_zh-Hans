# -*- coding: utf-8 -*-
"""Fold edits made in the working copy back into the repository data.

  py -3 dehydrate.py [--data data] [--work work] [--dry]

Only `zh`, `status` and `note` travel back.  Ids, source hashes and the
technical columns come from `data/` and are never taken from `work/`, so a
working copy built against a different version of the game cannot quietly
rewrite the repository's idea of what each row is.

The diff this produces is the whole point of the format: one line per changed
translation, so a pull request reads as a list of sentences that changed.
"""
import sys, os, io, csv, argparse

CARRY = ("zh", "status", "note")


def read(path):
    with io.open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f)), csv.DictReader(
            io.open(path, encoding="utf-8-sig", newline="")).fieldnames


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default="data")
    ap.add_argument("--work", default="work")
    ap.add_argument("--dry", action="store_true", help="report, do not write")
    a = ap.parse_args(argv)

    zh = os.path.join(a.data, "zh-Hans")
    wk = os.path.join(a.work, "zh-Hans")
    if not os.path.isdir(wk):
        print("no working copy at %s -- run hydrate.py first" % wk)
        return 1

    changed_files = changed_rows = unknown = 0
    for root, _, names in os.walk(wk):
        for fn in sorted(names):
            if not fn.endswith(".csv") or fn.startswith("_"):
                continue
            wpath = os.path.join(root, fn)
            rel = os.path.relpath(wpath, wk)
            dpath = os.path.join(zh, rel)
            if not os.path.exists(dpath):
                print("  %s has no counterpart in data/ -- ignored" % rel)
                continue
            work_rows, _ = read(wpath)
            data_rows, cols = read(dpath)
            edits = {r["id"]: r for r in work_rows}
            n = 0
            for r in data_rows:
                e = edits.get(r["id"])
                if e is None:
                    continue
                for c in CARRY:
                    if c in e and e[c] != r.get(c, ""):
                        r[c] = e[c]
                        n += 1
            unknown += len(edits) - sum(1 for r in data_rows if r["id"] in edits)
            if n:
                changed_files += 1
                changed_rows += n
                if not a.dry:
                    with io.open(dpath, "w", encoding="utf-8", newline="") as f:
                        w = csv.DictWriter(f, fieldnames=cols, lineterminator="\n")
                        w.writeheader()
                        w.writerows(data_rows)
                print("  %-40s %d cells" % (rel, n))

    print("%d files, %d cells updated%s" % (changed_files, changed_rows,
                                            "  (dry run)" if a.dry else ""))
    if unknown:
        print("%d rows in the working copy have ids that data/ does not know; "
              "they were ignored" % unknown)
    return 0


if __name__ == "__main__":
    sys.exit(main())
