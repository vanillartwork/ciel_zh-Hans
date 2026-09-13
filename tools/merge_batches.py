"""Read the replies from the translating AI back into the export CSVs.

  py -3 merge_batches.py <export dir> <replies dir> [--dry]

A reply file is whatever the other AI sent back: blocks that start with
@<uid> followed by the Chinese lines.  Anything before the first @ is
ignored, so a chatty preamble does no harm.  Unknown uids, duplicate uids
and rows that already carry a translation are reported, never applied
silently.
"""
import sys, os, io, csv, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_batches import dedupable

NL = chr(10)
UID_RE = re.compile(r"^@\s*(\d+)\b")


def parse(text):
    out, uid, buf = {}, None, []
    for raw in text.replace(chr(13) + NL, NL).split(NL):
        m = UID_RE.match(raw.strip())
        if m:
            if uid is not None:
                out[uid] = NL.join(buf).strip(NL)
            uid, buf = m.group(1), []
            continue
        if uid is not None:
            buf.append(raw.rstrip())
    if uid is not None:
        out[uid] = NL.join(buf).strip(NL)
    return {k: v for k, v in out.items() if v.strip()}


def main(argv):
    exportdir, repliesdir = argv[1], argv[2]
    dry = "--dry" in argv
    trans, dupes = {}, set()
    for root, _, files in os.walk(repliesdir):
        for fn in sorted(files):
            if not fn.lower().endswith((".txt", ".md")):
                continue
            got = parse(io.open(os.path.join(root, fn), encoding="utf-8",
                                errors="replace").read())
            for k, v in got.items():
                if k in trans and trans[k] != v:
                    dupes.add(k)
                trans[k] = v
    print("parsed %s translated blocks from %s"
          % (format(len(trans), ","), repliesdir))
    if dupes:
        print("  WARNING: %d uids appeared twice with different text (last wins)"
              % len(dupes))

    applied = overwritten = 0
    used = set()
    for root, _, files in os.walk(exportdir):
        for fn in sorted(files):
            if not fn.endswith(".csv") or fn.startswith("_"):
                continue
            p = os.path.join(root, fn)
            with io.open(p, encoding="utf-8-sig", newline="") as f:
                rd = csv.DictReader(f)
                cols = rd.fieldnames
                rows = list(rd)
            hit = False
            for r in rows:
                v = trans.get(r["uid"])
                if v is None:
                    continue
                used.add(r["uid"])
                if r["zh"].strip() and r["zh"] != v:
                    overwritten += 1
                if r["zh"] != v:
                    r["zh"] = v
                    applied += 1
                    hit = True
            if hit and not dry:
                with io.open(p, "w", encoding="utf-8-sig", newline="") as f:
                    cw = csv.DictWriter(f, fieldnames=cols, lineterminator="\r\n")
                    cw.writeheader()
                    cw.writerows(rows)
    # A deduplicated batch carries one row per distinct source string; copy its
    # translation onto every other row with the same source (dialogue excluded).
    canon = {}
    for root, _, files in os.walk(exportdir):
        for fn in sorted(files):
            if not fn.endswith(".csv") or fn.startswith("_"):
                continue
            rel = os.path.relpath(os.path.join(root, fn), exportdir).replace(os.sep, "/")
            with io.open(os.path.join(root, fn), encoding="utf-8-sig", newline="") as f:
                for r in csv.DictReader(f):
                    if not dedupable(rel, r):
                        continue
                    if r["uid"] in trans:
                        canon[r["jp"]] = trans[r["uid"]]
    copied = 0
    for root, _, files in os.walk(exportdir):
        for fn in sorted(files):
            if not fn.endswith(".csv") or fn.startswith("_"):
                continue
            p2 = os.path.join(root, fn)
            rel = os.path.relpath(p2, exportdir).replace(os.sep, "/")
            with io.open(p2, encoding="utf-8-sig", newline="") as f:
                rd = csv.DictReader(f)
                cols = rd.fieldnames
                rows = list(rd)
            hit = False
            for r in rows:
                if not dedupable(rel, r):
                    continue
                v = canon.get(r["jp"])
                if v and not r["zh"].strip():
                    cap = int(r.get("max_bytes") or 10 ** 9)
                    if len(v.encode("utf-8")) <= cap - 1:
                        r["zh"] = v
                        copied += 1
                        hit = True
            if hit and not dry:
                with io.open(p2, "w", encoding="utf-8-sig", newline="") as f:
                    cw = csv.DictWriter(f, fieldnames=cols,
                                        lineterminator=chr(13) + chr(10))
                    cw.writeheader()
                    cw.writerows(rows)
    if copied:
        print("  copied %s translations onto identical source rows" % format(copied, ","))

    unknown = set(trans) - used
    print("  applied %s cells%s"
          % (format(applied, ","), "  (dry run)" if dry else ""))
    if overwritten:
        print("  %d already had a translation and were replaced" % overwritten)
    if unknown:
        print("  %d uids not found in the export: %s"
              % (len(unknown), " ".join(sorted(unknown)[:12])))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
