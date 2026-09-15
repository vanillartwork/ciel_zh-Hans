"""Pre-fill the glossary CSVs with the publisher official Chinese names.

  py -3 apply_official.py <export dir> [--tw] [--dry]

Default writes Simplified Chinese; --tw writes the Traditional wording exactly
as Koei Tecmo Taiwan published it.  Rows that already have a different zh are
reported and left alone unless --force.

A few entries in the table were never printed in Chinese by the publisher and
carry an authority of their own; the note written into the glossary says which,
so that nothing here claims official backing it does not have.
"""
import sys, os, io, csv, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from official_glossary import OFFICIAL, TITLES

KOEI = "光荣特库摩台湾"
# provenance this tool has written before, in any of its forms -- matched so a
# second run replaces the note instead of stamping the row a second time
NOTE = re.compile(r"(?:官方译名|译名来源)\([^)]*\)")


def authority(entry):
    """Who settled this wording -- the publisher, unless the entry says otherwise."""
    return entry[4] if len(entry) > 4 else KOEI


def note_for(entry):
    a = authority(entry)
    return ("官方译名(%s)" % a) if a == KOEI else ("译名来源(%s)" % a)


def main(argv):
    exportdir = argv[1]
    tw = "--tw" in argv
    dry = "--dry" in argv
    force = "--force" in argv
    col = 1 if tw else 2          # 1 = Traditional as published, 2 = Simplified
    table = {o[0]: (o[col], note_for(o)) for o in OFFICIAL}

    # Reference sheet.  Titles go in as ordinary rows of kind "title" rather
    # than as a loose block at the bottom: a reader walking the columns used to
    # take the Traditional title for the Simplified one, and so handed a
    # fan-made title to translators as though the publisher had blessed it.
    rows = [[o[0], o[2], o[3], o[1], authority(o)] for o in OFFICIAL]
    rows += [[t[0], t[2], "title", t[1], t[3]] for t in TITLES]
    with io.open(os.path.join(exportdir, "official_glossary.csv"), "w",
                 encoding="utf-8-sig", newline="") as f:
        cw = csv.writer(f, lineterminator="\r\n")
        cw.writerow(["jp", "zh_cn", "kind", "zh_tw_as_published", "authority"])
        cw.writerows(rows)

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
            got = table.get(r["jp"])
            if not got:
                continue
            v, note = got
            hit.add(r["jp"])
            if r["zh"].strip() and r["zh"].strip() != v:
                conflict += 1
                print("  conflict %-20s existing %-12s official %s"
                      % (r["jp"], r["zh"], v))
                if not force:
                    skipped += 1
                    continue
            # Rewrite the provenance rather than appending to it: running this
            # twice used to leave the same note stamped on the row twice over.
            was = NOTE.sub("", r.get("note") or "").strip()
            if r["zh"] != v or r.get("note") != was + note:
                filled += r["zh"] != v
                r["zh"] = v
                r["note"] = was + note
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
