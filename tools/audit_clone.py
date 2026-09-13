# -*- coding: utf-8 -*-
"""Audit a translated copy of the export against the pristine one.

  py -3 audit_clone.py <pristine export> <clone export>

Checks, in order of how badly each would hurt:
  1. encoding: does the file decode as UTF-8, any replacement chars, any
     tell-tale mojibake from a wrong-codec round trip
  2. structure: same columns, same uid set, same order
  3. source integrity: the jp column must be identical -- if the source text
     moved at all, the file went through something lossy
  4. fill rate: how much zh is actually there
"""
import sys, os, io, csv, re, collections, unicodedata

MOJI = re.compile(r'[\ufffd]|[\u00c0-\u00ff]{2,}|[\ue000-\uf8ff]')
CTRL = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f]')


def load(path):
    raw = open(path, "rb").read()
    bom = raw.startswith(b"\xef\xbb\xbf")
    err = None
    try:
        txt = (raw[3:] if bom else raw).decode("utf-8")
    except UnicodeDecodeError as e:
        return None, None, bom, "UTF-8 decode failed at byte %d: %s" % (e.start, e.reason)
    rows = list(csv.DictReader(io.StringIO(txt, newline="")))
    return rows, txt, bom, err


def main(a, b):
    files = []
    for root, _, fs in os.walk(b):
        for fn in sorted(fs):
            if fn.endswith(".csv"):
                files.append(os.path.relpath(os.path.join(root, fn), b).replace(os.sep, "/"))
    print("clone files: %d" % len(files))
    tot = collections.Counter()
    problems = []
    for rel in sorted(files):
        pa, pb = os.path.join(a, rel.replace("/", os.sep)), os.path.join(b, rel.replace("/", os.sep))
        if not os.path.exists(pa):
            problems.append((rel, "no such file in the pristine export"))
            continue
        ra, _, boma, ea = load(pa)
        rb, tb, bomb, eb = load(pb)
        if eb:
            problems.append((rel, eb)); continue
        if rel == "_manifest.csv" or rel == "official_glossary.csv":
            continue
        if not bomb:
            problems.append((rel, "BOM missing (Excel will mis-read it)"))
        bad = MOJI.findall(tb)
        if bad:
            problems.append((rel, "mojibake/replacement chars: %d (%s)"
                             % (len(bad), " ".join(sorted(set(bad))[:6]))))
        if CTRL.search(tb):
            problems.append((rel, "stray control characters"))
        if ra is None:
            continue
        if [r["uid"] for r in ra] != [r["uid"] for r in rb]:
            sa, sb = set(r["uid"] for r in ra), set(r["uid"] for r in rb)
            problems.append((rel, "uid mismatch: missing %d, extra %d, reordered=%s"
                             % (len(sa - sb), len(sb - sa), len(sa) == len(sb))))
        d = {r["uid"]: r for r in ra}
        jpdiff = [r["uid"] for r in rb if r["uid"] in d and r["jp"] != d[r["uid"]]["jp"]]
        if jpdiff:
            problems.append((rel, "SOURCE TEXT CHANGED in %d rows (uid %s ...)"
                             % (len(jpdiff), " ".join(jpdiff[:5]))))
        n = len(rb)
        filled = sum(1 for r in rb if r["zh"].strip())
        tot["rows"] += n
        tot["filled"] += filled
        if filled:
            tot["files_touched"] += 1
    print("\n--- problems ---")
    if problems:
        for rel, msg in problems:
            print("  %-28s %s" % (rel, msg))
    else:
        print("  none")
    print("\n--- totals ---")
    print("  rows %s   translated %s (%.1f%%)   files with any translation %d"
          % (format(tot["rows"], ","), format(tot["filled"], ","),
             100.0 * tot["filled"] / max(1, tot["rows"]), tot["files_touched"]))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
