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
import nameplates
from export_text import (JP, MAX_LINES, MAX_CHARS, ATTR_RE, COMMENT_RE,
                         bin_fields, schema_for, TAG_RE, TERM_RE,
                         SPEAKER_COL, DIALOG_COL)
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
    speakers = {}
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
    # The name plate above each line of dialogue is column 11 of the script,
    # and it is not exported per row -- one name shows up tens of thousands of
    # times, so it is translated once in the speaker glossary and applied from
    # there. Without this the text is Chinese but the name above it stays
    # Japanese, which is easy to miss for names that happen to be written the
    # same in both languages (神官, 少年).
    p = os.path.join(exportdir, "glossary_speakers.csv")
    if os.path.exists(p):
        for r in load_csv(p):
            if r["zh"].strip() and r["zh"] != r["jp"]:
                speakers[r["jp"]] = r["zh"]
    return script, ui, binmap, speakers


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


# Files that must come out of a build byte for byte identical.  The injector
# matches .bin fields by their Japanese text alone, so a word that is display
# text in one table and a functional value in another gets rewritten in both.
# ngword_data.bin is the blocked-word list the game filters player input with:
# translating エッチ to 下流 in it does not localise anything, it silently
# changes what the filter catches.
KEEP_VERBATIM = (
    "inc/globaldata/ngword_data.bin",
)


def build(pak, script, ui, binmap, speakers=None):
    """Return {archive path lower: new bytes}.

    `speakers` is accepted and ignored.  It used to drive nameplate injection;
    see the note further down for why that had to go.
    """
    out = {}
    by_file = collections.defaultdict(list)
    for k, r in script.items():
        by_file[r["file"]].append(r)
    paths = set(by_file)
    if speakers:
        # every shipped event script, not only the ones with translated
        # dialogue: a script may need nothing but its nameplate defaults
        paths |= {e.path.lower() for e in pak if nameplates.enabled(e.path.lower())}
    known_keys = nameplates.known_actors(pak) if speakers else set()
    plated = plated_files = 0
    for path in sorted(paths):
        rows = by_file.get(path, [])
        e = pak.get(path)
        if e is None:
            continue
        d = pak.read(e)
        bom = d.startswith(BOM)
        try:
            t = (d[3:] if bom else d).decode("utf-8")
        except UnicodeDecodeError:
            continue
        spans = {}
        for row, col, s, en in csvspan.scan(t):
            spans[(row, col)] = (s, en)
        edits = []
        for r in rows:
            sp = spans.get((int(r["row"]), int(r["col"])))
            if sp is None:
                continue
            edits.append((sp[0], sp[1], csvspan.quote(r["zh"])))
        # Column 11 is NOT a nameplate to translate.  It is the character
        # key: the row that places a character on stage carries it, and every
        # later row -- dialogue included -- uses it to say which of the placed
        # characters this line and this expression belong to.  charanamemap.inc
        # keys models by exactly this string, down to a trailing fullwidth
        # space ("イオン" is the normal model, "イオン　" the chibi one), and
        # charafacestancemap.inc resolves the generic FS_CRY in column 8 to a
        # per-character PC00_FS_CRY through it.
        #
        # It is also what the game prints on the nameplate, which is what made
        # translating it look right and safe.  It is not: a translated key
        # matches nothing, so the character is never placed, expressions and
        # lip sync never change, the camera has no target, and an interaction
        # that has to find her softlocks.  There is no separate display-name
        # table to patch instead -- so nameplates stay Japanese until that is
        # solved some other way.  Do not reintroduce this without a way to
        # separate the key from the label.
        # Chinese nameplates, where they have been confirmed safe: the key in
        # column 11 stays Japanese and the label is set with the game's own
        # rename command, inserted after the header row.  See nameplates.py.
        if speakers and nameplates.enabled(path):
            ins, who = nameplates.plan(t, speakers, known_keys)
            edits += ins
            plated += len(who)
            if ins: plated_files += 1
        if not edits:
            continue
        edits.sort()
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

    if plated_files:
        print("nameplates: %d 条改名指令插入 %d 个脚本" % (plated, plated_files))

    if binmap:
        for e in pak:
            p = e.path.lower()
            if not p.endswith(".bin"):
                continue
            if any(p.endswith(x) for x in KEEP_VERBATIM):
                continue
            data = bytearray(pak.read(e))
            touched = False
            for off, cap, s in list(bin_fields(bytes(data), schema_for(p))):
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
    script, ui, binmap, speakers = collect(exportdir)
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
    files = build(pak, script, ui, binmap, speakers)
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
