"""Pre-fill the glossary CSVs with the publisher official Chinese names.

  py -3 apply_official.py <export dir> [--tw] [--dry]

Default writes Simplified Chinese; --tw writes the Traditional wording exactly
as Koei Tecmo Taiwan published it.  Rows that already have a different zh are
reported and left alone unless --force.
"""
import sys, os, io, csv
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from official_glossary import OFFICIAL, TITLES


def main(argv):
    exportdir = argv[1]
    tw = "--tw" in argv
    dry = "--dry" in argv
    force = "--force" in argv
    col = 1 if tw else 2          # 1 = Traditional as published, 2 = Simplified
    table = {o[0]: o[col] for o in OFFICIAL}

    # reference sheet
    rows = [[o[0], o[2], o[3], o[1]] for o in OFFICIAL]
    with io.open(os.path.join(exportdir, "official_glossary.csv"), "w",
                 encoding="utf-8-sig", newline="") as f:
        cw = csv.writer(f, lineterminator="\r\n")
        cw.writerow(["jp", "zh_cn", "kind", "zh_tw_as_published"])
        cw.writerows(rows)
        cw.writerow([])
        cw.writerow(["-- titles --"])
        cw.writerows([list(t) for t in TITLES])

    filled = skipped = conflict = 0
    hit = set()
    for name in ("glossary_terms.csv", "glossary_speakers.csv"):
        p = os.path.join(exportdir, name)
        if not os.path.exists(p):
            continue
        with io.open(p, encoding="utf-8-sig", newline="") as f:
            rd = csv.DictReader(f)
            cols = rd.fieldnames
            data = list(rd)
        changed = False
        for r in data:
            v = table.get(r["jp"])
            if not v:
                continue
            hit.add(r["jp"])
            if r["zh"].strip() and r["zh"].strip() != v:
                conflict += 1
                print("  conflict %-20s existing %-12s official %s"
                      % (r["jp"], r["zh"], v))
                if not force:
                    skipped += 1
                    continue
            if r["zh"] != v:
                r["zh"] = v
                r["note"] = (r.get("note") or "") + "官方译名(光荣特库摩台湾)"
                filled += 1
                changed = True
        if changed and not dry:
            with io.open(p, "w", encoding="utf-8-sig", newline="") as f:
                cw = csv.DictWriter(f, fieldnames=cols, lineterminator="\r\n")
                cw.writeheader()
                cw.writerows(data)
    missing = [o[0] for o in OFFICIAL if o[0] not in hit]
    print("filled %d glossary rows%s" % (filled, "  (dry run)" if dry else ""))
    if skipped:
        print("  %d left alone because they already had a different translation" % skipped)
    print("  %d official entries have no matching row in the export:" % len(missing))
    print("    " + "  ".join(missing))
    print("  reference sheet -> export/official_glossary.csv")


if __name__ == "__main__":
    main(sys.argv)
