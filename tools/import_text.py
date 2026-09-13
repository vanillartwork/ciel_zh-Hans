"""Inject translated CSVs back into the game data.

  py -3 import_text.py <Res_x64> <export dir> --loose <out dir>
  py -3 import_text.py <Res_x64> <export dir> --pak   <out PACK01.PAK>

--loose writes only the changed files, laid out the way the archive stores
them (Inc/..., UI/...), for drop-in testing next to the exe.
--pak rebuilds the whole archive.

Rows whose `zh` is empty are left in Japanese, so partial translations work.
Everything is checked before a single byte is written; problems are reported
and the run aborts unless --force is given.
"""
import sys, os, re, csv, io, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gustpak import Pak, rebuild
import csvspan
from export_text import (JP, MAX_LINES, MAX_CHARS, ATTR_RE, COMMENT_RE,
                         bin_fields, TAG_RE, TERM_RE)
try:
    from normalize_cn import normalize, residual, SUSPECT
except Exception:
    # zhconv is a maintainer dependency. Without it the normalisation pass is
    # skipped, which is correct for a build: what is in data/ has already been
    # normalised, and this step would only re-do that work.
    normalize = residual = SUSPECT = None

BOM = b"\xef\xbb\xbf"


def load_csv(path):
    with io.open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def collect(exportdir):
    script, ui, binmap = {}, {}, {}
    for root, _, files in os.walk(os.path.join(exportdir, "script")):
        for fn in sorted(files):
            if fn.endswith(".csv"):
                for r in load_csv(os.path.join(root, fn)):
                    if r["zh"].strip():
                        script[r["key"]] = r
    p = os.path.join(exportdir, "ui_text.csv")
    if os.path.exists(p):
        for r in load_csv(p):
            if r["zh"].strip():
                ui[r["key"]] = r
    for n in ("item_text.csv", "global_text.csv"):
        p = os.path.join(exportdir, n)
        if os.path.exists(p):
            for r in load_csv(p):
                if r["zh"].strip():
                    binmap[r["jp"]] = r
    return script, ui, binmap


def check(script, ui, binmap, charset):
    errs, warns = [], []
    missing = collections.Counter()
    notcn = collections.Counter()

    def cn_check(k, zh):
        """Flag Traditional / Japanese shinjitai left in a Simplified patch."""
        if normalize is None:
            return
        fixed = normalize(zh)
        if fixed != zh:
            bad = "".join(sorted({x for x, y in zip(zh, fixed) if x != y}))
            warns.append("%s: not Simplified (%s) -- run normalize_cn.py" % (k, bad))
        for c in zh:
            if SUSPECT and c in SUSPECT:
                notcn[c] += 1
    for k, r in list(script.items()) + list(ui.items()):
        zh, jp = r["zh"], r["jp"]
        # <TAG> markers are literal and must survive unchanged; {term} markers
        # get their contents translated, so only the braces can be compared.
        tj, tz = sorted(TAG_RE.findall(jp)), sorted(TAG_RE.findall(zh))
        if tj != tz:
            warns.append("%s: control tags changed %s -> %s" % (k, tj, tz))
        if (jp.count("{"), jp.count("}")) != (zh.count("{"), zh.count("}")):
            warns.append("%s: %d glossary markers in source, %d in translation"
                         % (k, jp.count("{"), zh.count("{")))
        lines = zh.split("\n")
        if len(lines) > max(MAX_LINES, len(jp.split("\n"))):
            warns.append("%s: %d lines (source %d)" % (k, len(lines), len(jp.split("\n"))))
        for l in lines:
            if len(l) > MAX_CHARS and len(l) > max(len(x) for x in jp.split("\n")):
                warns.append("%s: line of %d chars" % (k, len(l)))
        for ch in zh:
            if ch not in charset and ch not in "\n":
                missing[ch] += 1
        cn_check(k, zh)
    for jp, r in binmap.items():
        need = len(r["zh"].encode("utf-8"))
        cap = int(r["max_bytes"])
        if need > cap - 1:            # every field keeps one byte for the NUL
            errs.append("bin field over capacity: %d > %d usable bytes  %r"
                        % (need, cap - 1, r["zh"][:30]))
        for ch in r["zh"]:
            if ch not in charset:
                missing[ch] += 1
        cn_check(jp[:12], r["zh"])
    for c, n in notcn.most_common():
        warns.append("possible Japanese leftover %s x%d -- %s" % (c, n, SUSPECT[c]))
    return errs, warns, missing


def font_charset(pak):
    e = pak.get("inc/font/font_fotelemarraydata.inc")
    if not e:
        return None
    txt = pak.read(e).decode("utf-8", "replace")
    out = set()
    for m in re.finditer(r"\{\s*(\d+),", txt):
        c = int(m.group(1))
        b, v = [], c
        while v:
            b.append(v & 0xFF)
            v >>= 8
        try:
            out.add(bytes(reversed(b)).decode("utf-8"))
        except Exception:
            pass
    return out


def build(pak, script, ui, binmap):
    """Return {archive path lower: new bytes}."""
    out = {}
    by_file = collections.defaultdict(list)
    for k, r in script.items():
        by_file[r["file"]].append(r)
    for path, rows in by_file.items():
        e = pak.get(path)
        if e is None:
            continue
        d = pak.read(e)
        bom = d.startswith(BOM)
        t = (d[3:] if bom else d).decode("utf-8")
        spans = {}
        for row, col, s, en in csvspan.scan(t):
            spans[(row, col)] = (s, en)
        edits = []
        for r in rows:
            sp = spans.get((int(r["row"]), int(r["col"])))
            if sp is None:
                continue
            edits.append((sp[0], sp[1], csvspan.quote(r["zh"])))
        out[path] = (BOM if bom else b"") + csvspan.splice(t, edits).encode("utf-8")

    by_file = collections.defaultdict(list)
    for k, r in ui.items():
        by_file[r["file"]].append((int(k.rsplit("#", 1)[1]), r))
    for path, rows in by_file.items():
        e = pak.get(path)
        if e is None:
            continue
        d = pak.read(e)
        bom = d.startswith(BOM)
        t = (d[3:] if bom else d).decode("utf-8")
        blanked = COMMENT_RE.sub(lambda m: " " * len(m.group()), t)
        spans = {m.start(2): (m.start(2), m.end(2)) for m in ATTR_RE.finditer(blanked)}
        edits = [(spans[o][0], spans[o][1], r["zh"].replace('"', "&quot;"))
                 for o, r in rows if o in spans]
        out[path] = (BOM if bom else b"") + csvspan.splice(t, edits).encode("utf-8")

    if binmap:
        for e in pak:
            p = e.path.lower()
            if not p.endswith(".bin"):
                continue
            data = bytearray(pak.read(e))
            touched = False
            for off, cap, s in list(bin_fields(bytes(data))):
                r = binmap.get(s)
                if not r:
                    continue
                nb = r["zh"].encode("utf-8")
                if len(nb) > cap - 1:
                    continue
                data[off:off + cap] = nb + b"\0" * (cap - len(nb))
                touched = True
            if touched:
                out[p] = bytes(data)
    return out


def main(argv):
    res, exportdir, mode, target = argv[1], argv[2], argv[3], argv[4]
    force = "--force" in argv
    pak = Pak(os.path.join(res, "PACK01.PAK"))
    script, ui, binmap = collect(exportdir)
    print("translated rows: script=%d ui=%d bin=%d" % (len(script), len(ui), len(binmap)))
    cs = font_charset(pak)
    errs, warns, missing = check(script, ui, binmap, cs)
    for e in errs[:25]:
        print("  ERROR  " + e)
    for x in warns[:25]:
        print("  warn   " + x)
    if warns:
        print("  ... %d warnings total" % len(warns))
    if missing:
        p = os.path.join(exportdir, "missing_glyphs.txt")
        io.open(p, "w", encoding="utf-8").write("".join(sorted(missing)))
        print("  %d characters are not in the game font -> %s"
              % (len(missing), p))
    if errs and not force:
        print("aborted (%d errors); pass --force to write anyway" % len(errs))
        return 1
    files = build(pak, script, ui, binmap)
    print("rewriting %d archive members" % len(files))
    if mode == "--loose":
        for p, data in files.items():
            real = pak.get(p).name.strip("\\")
            dst = os.path.join(target, real.replace("\\", os.sep))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            open(dst, "wb").write(data)
        print("loose files -> " + target)
    else:
        rebuild(pak, files, target)
        print("archive -> %s (%d bytes)" % (target, os.path.getsize(target)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
