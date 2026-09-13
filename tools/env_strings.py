# -*- coding: utf-8 -*-
"""The settings program's UI text: read it out, and write a translation back.

  py -3 env_strings.py export <out dir>            -> env_text.csv
  py -3 env_strings.py patch  <in exe> <out exe> [--csv <env_text.csv>] [--dry]

`CielnosurgeDX_Env.exe` is the little program that opens before the game and
holds 起動環境設定 -- resolution, language, gamepad and key bindings. It is a
separate executable from the game, with its own Win32 resources, so nothing
the data patch or the game executable patch does touches it.

Its text lives in two kinds of resource:

  STRINGTABLE   blocks of 16 length-prefixed UTF-16 strings
  DIALOG        NUL-terminated UTF-16 inside the dialog template

Both are rewritten in place, which means a translation must fit in the same
number of UTF-16 units as the original and the rest is padded with spaces.
Changing a length would move everything after it within the resource and the
resource directory's sizes would no longer match -- far more surgery than a
settings dialog is worth. Chinese is shorter than Japanese here in every case.
"""
import sys, os, io, csv, re, struct, argparse, unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gamepath

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

EXE = "CielnosurgeDX_Env.exe"
JP = re.compile(r"[぀-ヿ一-鿿]")
KANA = re.compile(r"[぀-ヿ]")
# A dialog template is mostly numbers, and some of those decode as printable
# UTF-16. Real UI text uses only these: ASCII, kana, CJK, CJK and fullwidth
# punctuation, and the four arrows the key-binding prompts draw. Anything with
# a character from outside that -- Cyrillic, Arabic, Latin Extended -- is
# template data that happened to decode, not a label.
UI_CHAR = re.compile(r"^[\x20-\x7e←-↓　-〿぀-ヿ"
                     r"一-鿿！-｠]+$")
# the dialog font name, which is text but must never be translated
NOT_TEXT = re.compile(r"(Gothic|MS UI|Segoe|Arial|Tahoma|MS Shell Dlg)")


def looks_like_ui(s):
    if not UI_CHAR.match(s) or NOT_TEXT.search(s):
        return False
    return bool(KANA.search(s)) or len(re.findall(r"[一-鿿]", s)) >= 2
COLS = ["uid", "kind", "max_chars", "jp", "zh", "note"]


def sections(d):
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    nsec = struct.unpack_from("<H", d, pe + 6)[0]
    optsz = struct.unpack_from("<H", d, pe + 20)[0]
    opt = pe + 24
    magic = struct.unpack_from("<H", d, opt)[0]
    ddir = opt + (112 if magic == 0x20B else 96)
    rsrc_va = struct.unpack_from("<I", d, ddir + 16)[0]
    tbl = pe + 24 + optsz
    secs = []
    for i in range(nsec):
        s = d[tbl + i * 40:tbl + (i + 1) * 40]
        vsize, vaddr, rsize, raddr = struct.unpack("<4I", s[8:24])
        secs.append((vaddr, vsize, raddr, rsize))
    return secs, rsrc_va


def va2off(secs, v):
    for va, vs, ra, rs in secs:
        if va <= v < va + max(vs, rs):
            return ra + (v - va)


def resources(d):
    """(type, file offset, size) for every resource data entry."""
    secs, rsrc_va = sections(d)
    base = va2off(secs, rsrc_va)
    out = []

    def walk(off, path):
        n_named, n_id = struct.unpack_from("<HH", d, off + 12)
        for i in range(n_named + n_id):
            e = off + 16 + i * 8
            name, entry = struct.unpack_from("<II", d, e)
            nm = name & 0x7FFFFFFF if not (name & 0x80000000) else None
            if entry & 0x80000000:
                walk(base + (entry & 0x7FFFFFFF), path + [nm])
            else:
                va, size = struct.unpack_from("<2I", d, base + entry)
                out.append((path[0] if path else None, va2off(secs, va), size))

    walk(base, [])
    return out


def find_strings(d):
    """Every translatable UI string, as (uid, kind, offset, chars, text)."""
    found = []
    for rtype, off, size in resources(d):
        blob = d[off:off + size]
        if rtype == 6:                                   # STRINGTABLE
            i = 0
            while i + 2 <= len(blob):
                ln = struct.unpack_from("<H", blob, i)[0]
                i += 2
                if ln:
                    try:
                        s = blob[i:i + ln * 2].decode("utf-16-le")
                    except UnicodeDecodeError:
                        s = None
                    if s and looks_like_ui(s):
                        found.append(("str", off + i, ln, s))
                i += ln * 2
        elif rtype == 5:                                 # DIALOG
            # Walk 16-bit units and take each maximal printable run that ends
            # at a NUL. Matching with a regex instead picks up runs that start
            # partway into a string -- which produced a four-character
            # "効にする" out of the middle of "マウス操作を有効にする", and
            # translating that would have left half a Japanese word behind.
            run, start = [], None
            for i in range(0, len(blob) - 1, 2):
                u = blob[i] | (blob[i + 1] << 8)
                if u == 0:
                    if run and len(run) >= 2:
                        s = "".join(run)
                        if looks_like_ui(s):
                            found.append(("dlg", start, len(s), s))
                    run, start = [], None
                    continue
                c = chr(u)
                # not str.isprintable(): that call rejects U+3000, the
                # ideographic space, which the dialog titles use between the
                # game's name and the screen's name. Splitting there produced
                # two half-titles instead of one string.
                if u >= 0x20 and unicodedata.category(c)[0] != "C":
                    if start is None:
                        start = off + i
                    run.append(c)
                else:
                    run, start = [], None
    # one row per distinct text; the same label can appear in several dialogs
    by_text = {}
    for kind, off, n, s in found:
        by_text.setdefault(s, []).append((kind, off, n))
    rows = []
    for i, s in enumerate(sorted(by_text), 1):
        places = by_text[s]
        cap = min(n for _, _, n in places)
        kinds = "+".join(sorted({k for k, _, _ in places}))
        note = "出现%d处" % len(places) if len(places) > 1 else ""
        rows.append(("env:%d" % i, kinds, cap, s, note, places))
    return rows


def do_export(outdir, exe_path=None):
    path = exe_path or gamepath.source_file(gamepath.resolve(), EXE)
    d = open(path, "rb").read()
    rows = find_strings(d)
    os.makedirs(outdir, exist_ok=True)
    p = os.path.join(outdir, "env_text.csv")
    with io.open(p, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, lineterminator="\r\n")
        w.writerow(COLS)
        for uid, kinds, cap, s, note, _ in rows:
            w.writerow([uid, kinds, cap, s, "", note])
    print("%d strings -> %s" % (len(rows), p))
    return rows


def load(csv_path):
    rows = list(csv.DictReader(io.open(csv_path, encoding="utf-8-sig", newline="")))
    return {r["jp"]: r["zh"] for r in rows if r["zh"].strip()}


FACES = ("MS UI Gothic", "MS Shell Dlg")


def retypeface(d, new="SimSun", report=print, faces=FACES):
    """Point the dialogs at a font that has the target language's characters.

    The dialogs ask for MS UI Gothic, which is a Japanese face: it has no
    glyph for 设 语 键 镜 请 and a dozen others, so Chinese labels would come
    out as boxes wherever the system did not quietly substitute something.

    The typeface name sits inside the dialog template as a NUL-terminated
    string, and everything after it is parsed sequentially and DWORD-aligned,
    so its length cannot simply change. Two things make the swap safe:
    shifting the remainder of the template back and zero-padding the tail
    keeps the resource the size the directory says it is, and
    "MS UI Gothic\\0" and "SimSun\\0" happen to be the same length modulo 4,
    so every item after it stays on its alignment.
    """
    nb = (new + "\0").encode("utf-16-le")
    total = 0
    for old in faces:
        ob = (old + "\0").encode("utf-16-le")
        if len(ob) % 4 != len(nb) % 4:
            raise SystemExit("%r cannot replace %r: it would change the "
                             "alignment of everything after it in the dialog "
                             "template" % (new, old))
        n = 0
        for rtype, off, size in resources(bytes(d)):
            if rtype != 5:
                continue
            blob = bytes(d[off:off + size])
            i = blob.find(ob)
            if i < 0:
                continue
            rebuilt = (blob[:i] + nb + blob[i + len(ob):]
                       + b"\0" * (len(ob) - len(nb)))
            assert len(rebuilt) == size
            d[off:off + size] = rebuilt
            n += 1
        if n:
            report("  dialog font: %s -> %s  (%d dialogs)" % (old, new, n))
        total += n
    return total


def do_patch(src, dst, csv_path, dry=False, font="SimSun"):
    d = bytearray(open(src, "rb").read())
    trans = load(csv_path)
    rows = find_strings(bytes(d))
    done = over = miss = spots = 0
    for uid, kinds, cap, s, note, places in rows:
        zh = trans.get(s)
        if not zh:
            miss += 1
            continue
        if len(zh) > cap:
            print("TOO LONG %s  %d > %d 字  %r" % (uid, len(zh), cap, zh))
            over += 1
            continue
        for kind, off, n in places:
            # same number of UTF-16 units, padded with spaces
            text = (zh + " " * (n - len(zh))).encode("utf-16-le")
            d[off:off + n * 2] = text
            spots += 1
        done += 1
    if font:
        retypeface(d, new=font)
    print("%d of %d strings translated in %d places; %d left in Japanese%s"
          % (done, len(rows), spots, miss, "  (dry run)" if dry else ""))
    if over:
        return 1
    if not dry:
        open(dst, "wb").write(bytes(d))
        print("settings exe -> %s" % dst)
    return 0


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export")
    e.add_argument("outdir")
    e.add_argument("--exe")
    p = sub.add_parser("patch")
    p.add_argument("src")
    p.add_argument("dst")
    p.add_argument("--csv", required=True)
    p.add_argument("--dry", action="store_true")
    p.add_argument("--font", default="SimSun",
                   help="typeface for the dialogs; \"\" leaves it alone")
    a = ap.parse_args(argv[1:])
    if a.cmd == "export":
        do_export(a.outdir, a.exe)
        return 0
    return do_patch(a.src, a.dst, a.csv, a.dry, a.font)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
