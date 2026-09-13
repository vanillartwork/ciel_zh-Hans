# -*- coding: utf-8 -*-
"""Write data/charset.txt from the glyph table the patch actually ships.

  py -3 tools/export_charset.py [--exe <CielnosurgeDX.exe>] [--out data/charset.txt]

validate.py uses this list to answer one question: can the font draw this
character? So it has to come from the shipped glyph table itself, not from the
wish-list that went into the font build -- those two differ, because a glyph
the packer could not place, or that the source typeface had no outline for,
never makes it into the table.

With no --exe, it reads the patched executable in the game folder; failing
that, build/font/CielnosurgeDX.exe from a local build. Re-run this whenever
the font is rebuilt.
"""
import sys, os, io, struct, argparse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import font_atlas
import gamepath

# where the glyph count lives, and the one instruction that points at the table
DESC_COUNT = 0x8D08B0
LEA_OFF = 0x59656F


def sections(d):
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    nsec = struct.unpack_from("<H", d, pe + 6)[0]
    optsz = struct.unpack_from("<H", d, pe + 20)[0]
    tbl = pe + 24 + optsz
    out = []
    for i in range(nsec):
        s = d[tbl + i * 40:tbl + (i + 1) * 40]
        vsize, vaddr, rsize, raddr = struct.unpack("<4I", s[8:24])
        out.append((vaddr, vsize, raddr, rsize))
    return out


def shipped_glyphs(path):
    """Every character the executable's glyph table can draw."""
    d = open(path, "rb").read()
    secs = sections(d)

    def off_to_va(o):
        for va, vs, ra, rs in secs:
            if ra <= o < ra + rs:
                return va + (o - ra)

    def va_to_off(v):
        for va, vs, ra, rs in secs:
            if va <= v < va + max(vs, rs):
                return ra + (v - va)

    if bytes(d[LEA_OFF:LEA_OFF + 3]) != bytes([0x4C, 0x8D, 0x0D]):
        raise SystemExit(
            "%s does not look like a patched executable: the instruction that\n"
            "loads the glyph table is not where this build expects it.\n"
            "Point --exe at one produced by tools/build.py." % path)
    disp = struct.unpack_from("<i", d, LEA_OFF + 3)[0]
    table = va_to_off(off_to_va(LEA_OFF + 7) + disp)
    count = struct.unpack_from("<H", d, DESC_COUNT)[0]

    out = set()
    for i in range(count):
        raw = d[table + i * font_atlas.ENTRY:table + (i + 1) * font_atlas.ENTRY]
        g = font_atlas.Glyph(struct.unpack("<I", raw[:4])[0],
                             *struct.unpack("<4h", raw[4:12]),
                             *struct.unpack("<4i", raw[12:28]))
        # A slot whose packed code does not decode to exactly one character is
        # not a glyph anyone can ask for. Whitespace has no ink, and a control
        # character is not something a translation should ever contain, so
        # none of the three belongs in the list.
        ch = g.ch
        if ch and len(ch) == 1 and not ch.isspace() and ord(ch) >= 0x20:
            out.add(ch)
    return count, out


def candidates(explicit):
    if explicit:
        return [explicit]
    found = []
    try:
        found.append(os.path.join(gamepath.resolve(), "CielnosurgeDX.exe"))
    except gamepath.NotFound:
        pass
    found.append(os.path.join(ROOT, "build", "font", "CielnosurgeDX.exe"))
    return found


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--exe")
    ap.add_argument("--out", default=os.path.join(ROOT, "data", "charset.txt"))
    a = ap.parse_args(argv)

    last = None
    for p in candidates(a.exe):
        if not os.path.isfile(p):
            continue
        try:
            count, chars = shipped_glyphs(p)
        except SystemExit as e:
            last = str(e)
            continue
        io.open(a.out, "w", encoding="utf-8", newline="\n").write(
            "".join(sorted(chars)) + "\n")
        print("%d glyphs in %s\n%d drawable characters -> %s"
              % (count, p, len(chars), a.out))
        return 0

    print(last or "no patched executable found; build one first:\n"
                  "    py -3 tools/build.py --no-repack")
    return 1


if __name__ == "__main__":
    sys.exit(main())
