# -*- coding: utf-8 -*-
"""Rebuild the game font so it can draw Simplified Chinese.

  py -3 build_font.py <export dir> <out dir>

Produces
  <out>/FOT-SKIPSTD-B_0.g1t   8192x4096 BC1 atlas, same size as shipped
  <out>/CielnosurgeDX.exe     patched: bigger glyph table in a new section

How it works
  Existing glyphs are lifted out of the shipped atlas pixel for pixel, so the
  79% of the game that is still Japanese keeps its original typeface.  The
  missing GB2312 hanzi are rendered from Microsoft YaHei Bold, whose ink
  weight matches FOT-Skip Std B to within 1%, calibrated so the ink boxes
  land within about a pixel of the originals.

  The table outgrows its place in .rdata, so it moves to a new section and
  the single lea that addresses it is repointed.  The engine reads the glyph
  count as a u16 out of the font descriptor and binary-searches the array, so
  the new table is written sorted by codepoint.

  The atlas keeps its shipped 8192x4096.  Growing it to 8192x8192 and widening
  the descriptor UV field to 4096x4096 renders garbage: the engine gets its UV
  divisor from somewhere else, so every glyph samples at twice the intended
  height.  Room is made instead by dropping the 4,475 kanji this game never
  draws.
"""
import sys, os, struct, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gamepath
import numpy as np
from PIL import Image, ImageFont, ImageDraw
import bc1
import font_atlas as fa
from gustpak import Pak
from build_charset import main as build_charset

from build_charset import pristine_exe


def game_dir():
    return gamepath.resolve(os.environ.get("CIEL_NOSURGE_DX"))


def pak00():
    return gamepath.source_pak(game_dir() + "/Res_x64", "PACK00_01.PAK")


# The Chinese glyphs are drawn from a font on the building machine; it is not
# redistributed, and the built atlas is what the release carries.
FONT_TTF = os.environ.get("CIEL_NOSURGE_FONT", "C:/Windows/Fonts/msyhbd.ttc")

SRC_W, SRC_H = 8192, 4096
DST_W, DST_H = 8192, 4096          # unchanged: the engine does not take its
                                   # UV divisor from the descriptor, so the
                                   # atlas must keep the shipped dimensions
S = 2
UV_W, UV_H = DST_W // S, DST_H // S
PAD = 4          # keep glyphs in separate BC1 blocks
BLK = 4          # every glyph starts and ends on a block boundary, so that
                 # re-encoding cannot mix two glyphs into one 4x4 block and
                 # so that physical/2 lands exactly on the UV grid


def block(v):
    return (v + BLK - 1) // BLK * BLK
CANVAS = 192
NEW_TABLE_SLOTS = 12000

FONT_SIZE = 55
ANCHOR_X, ANCHOR_Y = 67, 58

LEA_OFF = 0x59656F
TEXT_VA, TEXT_RAW = 0x3EF000, 0x600
DESC_DIMS = 0x8D08A0
DESC_COUNT = 0x8D08B0


def log(*a):
    print(*a, flush=True)


def render_glyph(font, ch):
    im = Image.new("L", (CANVAS, CANVAS), 0)
    ImageDraw.Draw(im).text((CANVAS // 2, CANVAS // 2), ch, font=font, fill=255, anchor="mm")
    a = np.asarray(im)
    ys, xs = np.nonzero(a > 12)
    if len(xs) == 0:
        return None
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    return a[y0:y1, x0:x1], int(x0), int(y0)


def patch_exe(entries, out_path):
    d = bytearray(open(pristine_exe(), "rb").read())
    lf = struct.unpack_from("<I", d, 0x3C)[0]
    coff = lf + 4
    nsec = struct.unpack_from("<H", d, coff + 2)[0]
    optsz = struct.unpack_from("<H", d, coff + 16)[0]
    opt = coff + 20
    sect = opt + optsz
    salign = struct.unpack_from("<I", d, opt + 32)[0]
    falign = struct.unpack_from("<I", d, opt + 36)[0]
    sizeofimage = struct.unpack_from("<I", d, opt + 56)[0]

    body = b"".join(g.pack() for g in entries)
    raw_size = (len(body) + falign - 1) // falign * falign
    new_va = (sizeofimage + salign - 1) // salign * salign
    new_raw = (len(d) + falign - 1) // falign * falign
    d += bytes(new_raw - len(d))
    d += body + bytes(raw_size - len(body))

    hdr = struct.pack("<8s6I2HI", b".fontex", len(body), new_va, raw_size, new_raw,
                      0, 0, 0, 0, 0x40000040)
    off = sect + nsec * 40
    if any(d[off:off + 40]):
        raise SystemExit("no room in the section table")
    d[off:off + 40] = hdr
    struct.pack_into("<H", d, coff + 2, nsec + 1)
    struct.pack_into("<I", d, opt + 56,
                     new_va + (len(body) + salign - 1) // salign * salign)

    if bytes(d[LEA_OFF:LEA_OFF + 3]) != bytes([0x4C, 0x8D, 0x0D]):
        raise SystemExit("the lea that loads the glyph array is not where expected")
    rip_rva = TEXT_VA + (LEA_OFF + 7 - TEXT_RAW)
    struct.pack_into("<i", d, LEA_OFF + 3, new_va - rip_rva)
    struct.pack_into("<H", d, DESC_COUNT, len(entries))
    struct.pack_into("<I", d, opt + 64, 0)

    open(out_path, "wb").write(bytes(d))
    log("exe   -> %s  (+%d bytes; table at RVA 0x%X, %d entries, UV %dx%d)"
        % (out_path, raw_size, new_va, len(entries), UV_W, UV_H))


def main(exportdir, outdir):
    os.makedirs(outdir, exist_ok=True)
    t0 = time.time()

    keep, add = build_charset(exportdir, os.path.join(outdir, "charset.txt"))
    log("")

    log("reading the shipped atlas ...")
    pak = Pak(pak00())
    raw = pak.read("res_x64/font/fot-skipstd-b_0.g1t")
    header = bytearray(raw[:0x2C])
    src = bc1.decode(raw[0x2C:], SRC_W, SRC_H)

    have = {}
    for g in fa.read_table(pristine_exe()):
        if g.ch is not None and g.ch not in have:
            have[g.ch] = g

    # Any hanzi that Chinese uses is drawn from one typeface, so a Chinese
    # sentence never mixes two.  Kana, latin, punctuation and the kanji that
    # only Japanese needs keep the original FOT-Skip shapes.
    from build_charset import gb2312_chars
    redraw = gb2312_chars()

    glyphs = []
    kept = 0
    for ch in keep:
        if ch in redraw:
            add.append(ch)
            continue
        g = have[ch]
        bm = src[g.y * S:(g.y + g.h) * S, g.x * S:(g.x + g.w) * S]
        glyphs.append([ch, bm, g.w, g.h, g.ox, g.oy, g.adv])
        kept += 1
    add = sorted(set(add))
    log("kept %d original glyphs (kana, latin, punctuation, Japanese-only kanji)"
        % kept)

    font = ImageFont.truetype(FONT_TTF, FONT_SIZE)
    missing = []
    for ch in add:
        r = render_glyph(font, ch)
        if r is None:
            # blanks (the ideographic space) and anything the TTF lacks:
            # fall back to whatever the shipped font had
            g = have.get(ch)
            if g is not None:
                bm = src[g.y * S:(g.y + g.h) * S, g.x * S:(g.x + g.w) * S]
                glyphs.append([ch, bm, g.w, g.h, g.ox, g.oy, g.adv])
            else:
                missing.append(ch)
            continue
        bm, x0, y0 = r
        glyphs.append([ch, bm,
                       max(1, -(-bm.shape[1] // S)), max(1, -(-bm.shape[0] // S)),
                       int(round((x0 - ANCHOR_X) / S)),
                       int(round((y0 - ANCHOR_Y) / S)), 28])
    log("drew %d glyphs from %s at %dpx%s"
        % (len(add) - len(missing), os.path.basename(FONT_TTF), FONT_SIZE,
           ("   %d had no outline: %s" % (len(missing), "".join(missing))) if missing else ""))

    order = sorted(range(len(glyphs)), key=lambda i: -glyphs[i][1].shape[0])
    atlas = np.zeros((DST_H, DST_W), np.uint8)
    x = y = shelf = 0
    for i in order:
        h, w = glyphs[i][1].shape
        cw, chh = block(w), block(h)          # footprint, so no two glyphs
        if x + cw > DST_W:                    # ever share a BC1 block
            x = 0
            y += shelf + PAD
            shelf = 0
        if y + chh > DST_H:
            raise SystemExit("atlas overflow")
        atlas[y:y + h, x:x + w] = glyphs[i][1]
        assert x % S == 0 and y % S == 0, "glyph would land off the UV grid"
        glyphs[i].append((x // S, y // S))
        x += cw + PAD
        shelf = max(shelf, chh)
    used = y + shelf
    log("packed %d glyphs into %dx%d, %d rows used (%.1f%% of the texture)"
        % (len(glyphs), DST_W, DST_H, used, 100.0 * used / DST_H))

    entries = [fa.Glyph(fa.pack_code(ch), pos[0], pos[1], w_uv, h_uv, ox, oy, adv)
               for ch, bm, w_uv, h_uv, ox, oy, adv, pos in glyphs]
    entries.sort(key=lambda g: g.code)
    if len(entries) > NEW_TABLE_SLOTS:
        raise SystemExit("table needs %d slots" % len(entries))
    log("glyph table: %d entries, %d bytes, sorted by codepoint"
        % (len(entries), len(entries) * fa.ENTRY))

    log("encoding BC1 ...")
    payload = bc1.encode(atlas)
    struct.pack_into("<I", header, 8, len(payload) + 0x2C)
    out_g1t = os.path.join(outdir, "FOT-SKIPSTD-B_0.g1t")
    open(out_g1t, "wb").write(bytes(header) + payload)
    log("atlas -> %s (%d bytes)" % (out_g1t, len(payload) + 0x2C))

    patch_exe(entries, os.path.join(outdir, "CielnosurgeDX.exe"))
    log("done in %.1fs" % (time.time() - t0))
    return entries


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
