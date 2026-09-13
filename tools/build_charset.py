# -*- coding: utf-8 -*-
"""Decide which characters the rebuilt font has to contain.

  py -3 build_charset.py <export dir> [out file]

The shipped font carries 6,718 kanji because it is a general-purpose
typeface, but this game only ever draws 2,243 of them.  Dropping the ones
that never appear frees enough room to add the whole of GB2312 without
touching the atlas dimensions -- which matters, because the engine does not
take its UV divisor from the font descriptor, so resizing the texture
silently breaks every lookup.

Kept:
  every non-CJK glyph            kana, latin, punctuation, symbols
  kanji the game actually draws  from all Japanese source text, plus the
                                 hardcoded Japanese strings in the exe
  all of GB2312                  so any Simplified Chinese renders
  anything the translations use  covers the few chars outside both
"""
import sys, os, io, csv, re, struct

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gamepath
import font_atlas as fa

# Resolved on demand: importing this module must not fail on a machine that
# has no copy of the game, so that CI can import the tools around it.
def game_dir():
    return gamepath.resolve(os.environ.get("CIEL_NOSURGE_DX"))

CJK = re.compile(r"[\u3400-\u9fff\uf900-\ufaff]")


def pristine_exe():
    """Path to an unpatched CielnosurgeDX.exe.

    Building from an already-patched exe would stack a second .fontex on top
    of the first, so this refuses to guess: it wants the original 12-section
    image, and looks in Backup/ before the game folder.
    """
    game = game_dir()
    for p in (game + "/Backup/CielnosurgeDX.exe", game + "/CielnosurgeDX.exe"):
        if not os.path.exists(p):
            continue
        head = open(p, "rb").read(0x400)
        lf = struct.unpack_from("<I", head, 0x3C)[0]
        if struct.unpack_from("<H", head, lf + 6)[0] == 12:
            return p
    raise SystemExit("no unpatched CielnosurgeDX.exe found -- restore one from "
                     "Backup, or let Steam verify the game files, then retry")




def gb2312_chars():
    out = set()
    for hi in range(0xA1, 0xFF):
        for lo in range(0xA1, 0xFF):
            try:
                out.add(bytes([hi, lo]).decode("gb2312"))
            except Exception:
                pass
    return out


def exe_japanese():
    """Hardcoded Japanese in the executable, which no data patch can reach."""
    d = open(pristine_exe(), "rb").read()
    out = set()
    for m in re.finditer(rb"(?:[\xe3-\xe9][\x80-\xbf]{2}){2,}", d):
        try:
            out.update(m.group().decode("utf-8"))
        except UnicodeDecodeError:
            pass
    return out


def main(exportdir, out_path=None):
    have = {}
    for g in fa.read_table(pristine_exe()):
        if g.ch is not None and g.ch not in have:
            have[g.ch] = g

    jp_text, zh_text = set(), set()
    for root, _, files in os.walk(exportdir):
        for fn in sorted(files):
            if not fn.endswith(".csv") or fn.startswith("_"):
                continue
            with io.open(os.path.join(root, fn), encoding="utf-8-sig", newline="") as f:
                for r in csv.DictReader(f):
                    if "zh" not in (r or {}):
                        continue
                    jp_text.update(r["jp"])
                    if r["zh"].strip():
                        zh_text.update(r["zh"])

    non_cjk = {c for c in have if not CJK.match(c)}
    kanji_used = {c for c in (jp_text | exe_japanese()) if CJK.match(c) and c in have}
    gb = gb2312_chars()

    need = non_cjk | kanji_used | gb | zh_text
    need = {c for c in need if c and c not in "\r\n"}
    keep = sorted(c for c in need if c in have)
    add = sorted(c for c in need if c not in have)

    dropped = len(have) - len(keep)
    print("shipped font %d glyphs; the game draws %d of its kanji"
          % (len(have), len(kanji_used)))
    print("keep %d (dropping %d kanji this game never shows) + add %d = %d"
          % (len(keep), dropped, len(add), len(keep) + len(add)))

    if out_path:
        with io.open(out_path, "w", encoding="utf-8") as f:
            f.write("".join(keep) + "\n")
            f.write("".join(add) + "\n")
    return keep, add


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
