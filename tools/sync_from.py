# -*- coding: utf-8 -*-
"""Copy finished translations from one export tree into another.

  py -3 sync_from.py <source export> <target export> [--apply]

Only the zh column moves.  Before copying anything it checks that both trees
describe the same data -- same files, same uid order, same jp text -- and
refuses to touch the target if they have drifted apart.
"""
import sys, os, io, csv


def load(p):
    with io.open(p, encoding="utf-8-sig", newline="") as f:
        rd = csv.DictReader(f)
        return rd.fieldnames, list(rd)


def main(argv):
    src, dst = argv[1], argv[2]
    apply = "--apply" in argv
    files = []
    for root, _, fs in os.walk(src):
        for fn in sorted(fs):
            if fn.endswith(".csv") and not fn.startswith("_"):
                files.append(os.path.relpath(os.path.join(root, fn), src).replace(os.sep, "/"))
    problems, plan = [], []
    for rel in sorted(files):
        ps, pd = os.path.join(src, rel.replace("/", os.sep)), os.path.join(dst, rel.replace("/", os.sep))
        if not os.path.exists(pd):
            problems.append((rel, "not present in the target"))
            continue
        cs, rs = load(ps)
        cd, rd_ = load(pd)
        if not cs or not cd or 'uid' not in cs or 'zh' not in cs:
            continue          # reference sheets such as official_glossary.csv
        if [r["uid"] for r in rs] != [r["uid"] for r in rd_]:
            problems.append((rel, "uid order differs"))
            continue
        # CRLF inside a quoted cell may come back as LF from a round trip
        # through another tool; jp is never written back, so ignore that.
        def norm(s):
            return s.replace(chr(13) + chr(10), chr(10))
        jpdiff = sum(1 for a, b in zip(rs, rd_) if norm(a["jp"]) != norm(b["jp"]))
        if jpdiff:
            problems.append((rel, "jp text differs in %d rows" % jpdiff))
            continue
        n = ov = 0
        for a, b in zip(rs, rd_):
            if not a["zh"].strip():
                continue
            if b["zh"].strip() and b["zh"] != a["zh"]:
                ov += 1
            if b["zh"] != a["zh"]:
                b["zh"] = a["zh"]
                n += 1
        plan.append((rel, pd, cd, rd_, n, ov))
    if problems:
        print("REFUSING TO SYNC -- the two trees do not match:")
        for rel, why in problems:
            print("  %-28s %s" % (rel, why))
        return 1
    tot = sum(x[4] for x in plan)
    print("%d files checked, all consistent" % len(plan))
    for rel, pd, cd, rows, n, ov in plan:
        if n:
            print("  %-28s %5d cells%s" % (rel, n, "  (%d overwrote an existing value)" % ov if ov else ""))
    print("%s %d cells" % ("copied" if apply else "would copy (dry run)", tot))
    if apply:
        for rel, pd, cd, rows, n, ov in plan:
            if n:
                with io.open(pd, "w", encoding="utf-8-sig", newline="") as f:
                    cw = csv.DictWriter(f, fieldnames=cd, lineterminator=chr(13) + chr(10))
                    cw.writeheader()
                    cw.writerows(rows)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
