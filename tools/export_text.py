"""Export every player-facing string of Ciel nosurge DX into translation CSVs.

Usage:  py -3 export_text.py "<path to Res_x64>" "<output dir>"

Only the `zh` column is meant to be edited.  `key` is the join key used by
import_text.py -- never change it, never reorder or delete rows.
"""
import sys, os, re, csv, io, collections, itertools
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gamepath
from gustpak import Pak
import csvspan

JP = re.compile(r'[\u3040-\u30ff\u4e00-\u9fff\u3005\u30fc]')
MAX_LINES, MAX_CHARS = 3, 24

DIALOG_COL = 12
SPEAKER_COL = 11
CMD_COL = 13
CMD_TEXT = {
    "EVENT_PROCESS_WRITE_MEMO": ([1], "memo"),
    "EVENT_PROCESS_INFO": ([1], "info"),
    "EVENT_PROCESS_CHANGE_DISPLAY_NAME": ([1, 2], "name"),
}

_UID = itertools.count(1)


TAG_RE = re.compile(r'<[A-Za-z0-9_]{1,12}>')
TERM_RE = re.compile(r'\{[^}]{1,24}\}')


def notes_for(text):
    n = []
    tags = TAG_RE.findall(text)
    terms = TERM_RE.findall(text)
    if tags:
        n.append("keep-tags " + " ".join(sorted(set(tags))))
    if terms:
        n.append("keep-terms " + " ".join(sorted(set(terms))))
    lines = text.split("\n")
    if len(lines) > MAX_LINES:
        n.append("src-lines=%d" % len(lines))
    over = [len(l) for l in lines if len(l) > MAX_CHARS]
    if over:
        n.append("src-longest-line=%d" % max(over))
    return "; ".join(n)


def w(path, header, rows):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with io.open(path, "w", encoding="utf-8-sig", newline="") as f:
        cw = csv.writer(f, lineterminator="\r\n")
        cw.writerow(header)
        cw.writerows(rows)


def export_scripts(pak, outdir):
    groups = collections.defaultdict(list)
    speakers = collections.Counter()
    for e in pak:
        p = e.path.lower()
        if not (p.startswith("inc/event/res/") and p.endswith(".txt")):
            continue
        d = pak.read(e)
        bom = d.startswith(b"\xef\xbb\xbf")
        try:
            t = (d[3:] if bom else d).decode("utf-8")
        except UnicodeDecodeError:
            continue
        rel = p[len("inc/event/res/"):]
        grp = rel.split("/")[0] if "/" in rel else "_root"
        cells = collections.defaultdict(dict)
        for row, col, s, en in csvspan.scan(t):
            cells[row][col] = (s, en)
        for row in sorted(cells):
            c = cells[row]

            def val(i):
                sp = c.get(i)
                return csvspan.unquote(t[sp[0]:sp[1]]) if sp else ""

            speaker = val(SPEAKER_COL)
            if speaker:
                speakers[speaker] += 1
            items = []
            dv = val(DIALOG_COL)
            if dv.strip() and JP.search(dv):
                items.append((DIALOG_COL, "dialog", dv))
            cmd = val(CMD_COL)
            if cmd in CMD_TEXT:
                args, kind = CMD_TEXT[cmd]
                for a in args:
                    av = val(CMD_COL + a)
                    if av.strip() and JP.search(av):
                        items.append((CMD_COL + a, kind, av))
            for col, kind, text in items:
                groups[grp].append([
                    next(_UID),
                    "%s#%d#%d" % (p, row, col), p, row, col, kind, speaker,
                    len(text.split("\n")), text, "", notes_for(text)])
    hdr = ["uid", "key", "file", "row", "col", "kind", "speaker", "lines", "jp", "zh", "note"]
    stats = []
    for grp, rows in sorted(groups.items()):
        w(os.path.join(outdir, "script", grp + ".csv"), hdr, rows)
        stats.append(["script/" + grp + ".csv", len(rows), sum(len(r[8]) for r in rows)])
    return stats, speakers


ATTR_RE = re.compile(r'\b(text|title|prompt)="([^"]*)"')
COMMENT_RE = re.compile(r'<!--.*?-->', re.S)


def export_ui(pak, outdir):
    rows = []
    for e in pak:
        p = e.path.lower()
        if not (p.startswith("ui/") and p.endswith(".xml")):
            continue
        d = pak.read(e)
        bom = d.startswith(b"\xef\xbb\xbf")
        try:
            t = (d[3:] if bom else d).decode("utf-8")
        except UnicodeDecodeError:
            continue
        blanked = COMMENT_RE.sub(lambda m: " " * len(m.group()), t)
        for m in ATTR_RE.finditer(blanked):
            v = m.group(2)
            if not JP.search(v):
                continue
            rows.append([next(_UID), "%s#%d" % (p, m.start(2)), p, m.group(1), v, "",
                         notes_for(v)])
    w(os.path.join(outdir, "ui_text.csv"),
      ["uid", "key", "file", "attr", "jp", "zh", "note"], rows)
    return [["ui_text.csv", len(rows), sum(len(r[4]) for r in rows)]]


STR_RE = re.compile(rb'[^\x00]{1,4000}')


def bin_fields(data):
    for m in STR_RE.finditer(data):
        chunk = m.group()
        try:
            s = chunk.decode("utf-8")
        except UnicodeDecodeError:
            continue
        if not JP.search(s):
            continue
        end, cap = m.end(), len(chunk)
        while end < len(data) and data[end] == 0:
            cap += 1
            end += 1
        yield m.start(), cap, s


def inc_literals(pak, prefixes):
    """Human-readable source strings from the .inc files that generated the .bin."""
    out = set()
    for e in pak:
        q = e.path.lower()
        if q.endswith(".inc") and any(q.startswith(x) for x in prefixes):
            try:
                t = pak.read(e).decode("utf-8-sig")
            except UnicodeDecodeError:
                continue
            for m in re.finditer('"([^"]*)"', t):
                s = m.group(1)
                if JP.search(s):
                    out.add(s)
    return sorted(out, key=len)


def export_bins(pak, outdir, prefixes, name, ns=None):
    """Packed .bin fields.

    `ns` namespaces the keys. Without it, items and global text both number
    their rows from bin:0 and the two sets collide -- which matters because
    ids are meant to be unique across the whole project, and things like
    data/allow.csv address a row by id alone.
    """
    lits = inc_literals(pak, prefixes)
    uniq = {}
    for e in pak:
        p = e.path.lower()
        if not p.endswith(".bin") or not any(p.startswith(x) for x in prefixes):
            continue
        data = pak.read(e)
        for off, cap, s in bin_fields(data):
            rec = uniq.get(s)
            if rec is None:
                uniq[s] = [cap, 1, p]
            else:
                rec[0] = min(rec[0], cap)
                rec[1] += 1
    rows = []
    for i, (s, (cap, cnt, src)) in enumerate(sorted(uniq.items())):
        context, note = "", notes_for(s)
        if len(s) >= 10 and s not in lits:
            parent = next((x for x in lits if s in x), "")
            if parent:
                context = parent
                where = "head" if parent.startswith(s) else "continuation"
                note = ("field is a %s chunk of a longer source string; "
                        "translate it as that part only" % where
                        + ("; " + note if note else ""))
        rows.append([next(_UID), "%s:%d" % (ns or "bin", i), src, cnt, cap,
                     len(s.encode("utf-8")), s, "", context, note])
    w(os.path.join(outdir, name),
      ["uid", "key", "sample_file", "occurrences", "max_bytes", "jp_bytes", "jp",
       "zh", "full_source_context", "note"], rows)
    return [[name, len(rows), sum(len(r[6]) for r in rows)]]


KANA_RE = re.compile(r'[ァ-ヺー・]{3,}')


def export_terms(outdir, min_freq=12):
    """Proper nouns and in-game glossary markers, harvested from what we exported.

    Translate this file FIRST: make_batches.py injects the finished entries
    into every batch so each translation session uses the same wording.
    """
    braced = collections.Counter()
    kana = collections.Counter()
    for root, _, files in os.walk(outdir):
        for fn in files:
            if not fn.endswith(".csv") or fn.startswith("_"):
                continue
            with io.open(os.path.join(root, fn), encoding="utf-8-sig", newline="") as f:
                for r in csv.DictReader(f):
                    s = r.get("jp", "")
                    for m in TERM_RE.findall(s):
                        braced[m[1:-1]] += 1
                    for m in KANA_RE.findall(s):
                        kana[m] += 1
    rows = []
    seen = set()
    for term, c in braced.most_common():
        seen.add(term)
        rows.append([next(_UID), term, "glossary-marker", c, "", ""])
    for term, c in kana.most_common():
        if c >= min_freq and term not in seen:
            rows.append([next(_UID), term, "proper-noun", c, "", ""])
    w(os.path.join(outdir, "glossary_terms.csv"),
      ["uid", "jp", "kind", "occurrences", "zh", "note"], rows)
    return ["glossary_terms.csv", len(rows), sum(len(r[1]) for r in rows)]


def main(res_dir, outdir):
    pak = Pak(gamepath.source_pak(res_dir, "PACK01.PAK"))
    stats = []
    s, speakers = export_scripts(pak, outdir)
    stats += s
    stats += export_ui(pak, outdir)
    stats += export_bins(pak, outdir, ("inc/item/",), "item_text.csv", "item")
    stats += export_bins(pak, outdir,
                         ("inc/globaldata/", "inc/sharl/", "inc/iontweet/"),
                         "global_text.csv", "global")
    namemap = {}
    e = pak.get("inc/event/charanamemap.inc")
    if e:
        for ln in pak.read(e).decode("utf-8-sig", "replace").splitlines():
            m = re.match(r'"([^"]*)"\s+(\S+)\s+(\S+)', ln)
            if m:
                namemap[m.group(1)] = m.group(2)
    rows = [[next(_UID), "spk:%d" % i, n, c, namemap.get(n, ""), "", ""]
            for i, (n, c) in enumerate(speakers.most_common())]
    w(os.path.join(outdir, "glossary_speakers.csv"),
      ["uid", "key", "jp", "occurrences", "chara_id", "zh", "note"], rows)
    stats.append(["glossary_speakers.csv", len(rows), sum(len(r[2]) for r in rows)])
    stats.append(export_terms(outdir))
    w(os.path.join(outdir, "_manifest.csv"), ["file", "rows", "jp_chars"], stats)
    print("%d files, %s rows, %s JP characters -> %s"
          % (len(stats), format(sum(x[1] for x in stats), ","),
             format(sum(x[2] for x in stats), ","), outdir))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
