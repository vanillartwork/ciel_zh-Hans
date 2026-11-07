# -*- coding: utf-8 -*-
"""Re-break the 嬉しかったことメモ texts so they fit the memo box.

  py -3 tools/dev/rewrap_memos.py [--apply]

The memo screen shows each memo in a slot three lines high, and the Japanese
is broken by hand at ten full-width characters a line (eleven at most, in 51
lines).  A Chinese line longer than that runs past the box.  This re-breaks
every memo with an over-wide line: at most eleven full-width characters a line
(the Japanese's own widest), at most three lines, breaking after
punctuation where it can, never starting a line with closing punctuation and
never splitting "……", a run of ASCII or a run of full-width digits/letters.
Memos already within the limits are left exactly as they are.  A memo that
cannot fit three lines is listed, not cut: it needs shorter wording.

Which rows are memos comes from the build's own export (build/work/script.zip, the
`kind` column), so run a build first.  Translations are changed in
data/zh-Hans/script/*.csv, matched by id.
"""
import csv, glob, io, os, re, sys, unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import workscript      # noqa: E402
SOFT, HARD, LINES = 22, 22, 3          # widths in half-width units
NO_START = set("，。、！？：；…）」』】〉》”’♪～ー・")
BREAK_AFTER = set("，。、！？：；♪")


def width(s):
    return sum(2 if unicodedata.east_asian_width(ch) in "WFA" else 1 for ch in s)


def fits(text):
    lines = text.split("\n")
    return len(lines) <= LINES and all(width(l) <= SOFT for l in lines)


def units(text):
    """Pieces that must stay on one line."""
    return re.findall(r"…+|[A-Za-z0-9.%]+|[０-９Ａ-Ｚａ-ｚ]+|.", text)


def rewrap(text):
    """Best re-breaking of `text`, or None if it needs more than LINES lines."""
    u = units(text.replace("\r\n", "").replace("\n", ""))
    n = len(u)
    w = [width(x) for x in u]
    INF = float("inf")
    # best[i] = (cost, lines, breaks) for u[:i]
    best = [(INF, 0, None)] * (n + 1)
    best[0] = (0, 0, [])
    for i in range(n):
        cost0, lines0, br0 = best[i]
        if cost0 == INF:
            continue
        lw = 0
        for j in range(i + 1, n + 1):
            lw += w[j - 1]
            if lw > HARD:
                break
            if j < n and u[j][0] in NO_START:
                continue
            c = cost0 + 10                                  # every line costs
            if j < n:
                # a break inside a phrase reads badly in Chinese, which has no
                # spaces to break at; a short line is the lesser evil
                c += 0 if u[j - 1][-1] in BREAK_AFTER else 60
                c += (SOFT - lw) * 0.2
            if lines0 + 1 > LINES:
                continue
            if c < best[j][0]:
                best[j] = (c, lines0 + 1, br0 + [j])
    if best[n][0] == INF:
        return None
    out, prev = [], 0
    for j in best[n][2]:
        out.append("".join(u[prev:j]))
        prev = j
    return "\n".join(out)


def memo_ids():
    ids = set()
    for _name, data in workscript.read_all(os.path.join(ROOT, "build", "work")):
        for r in workscript.rows(data):
            if r.get("kind") == "memo":
                ids.add(r["key"])
    return ids


def main(argv):
    apply = "--apply" in argv
    ids = memo_ids()
    if not ids:
        print("no memo rows in build/work; run a build first")
        return 1
    changed, stuck, total = [], [], 0
    for p in sorted(glob.glob(os.path.join(ROOT, "data", "zh-Hans", "script", "*.csv"))):
        with io.open(p, encoding="utf-8", newline="") as f:
            s = f.read()
        rows = list(csv.DictReader(io.StringIO(s, newline="")))
        cols = list(rows[0].keys()) if rows else []
        touched = False
        for r in rows:
            if r["id"] not in ids or not r["zh"]:
                continue
            total += 1
            if fits(r["zh"]):
                continue
            new = rewrap(r["zh"])
            if new is None:
                stuck.append((os.path.basename(p), r["id"], r["zh"]))
                continue
            changed.append((r["zh"], new))
            r["zh"] = new
            touched = True
        if apply and touched:
            out = io.StringIO(newline="")
            w = csv.DictWriter(out, fieldnames=cols, lineterminator="\n")
            w.writeheader()
            w.writerows(rows)
            with io.open(p, "w", encoding="utf-8", newline="") as f:
                f.write(out.getvalue())
    for a, b in changed[:12]:
        print("%s\n  -> %s" % (a.replace("\n", "|"), b.replace("\n", "|")))
    print("%d memo rows, %d re-broken, %d need shorter wording" % (total, len(changed), len(stuck)))
    for fn, rid, zh in stuck:
        print("STUCK  %s  %s  %s" % (fn, rid, zh.replace("\n", "|")))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
