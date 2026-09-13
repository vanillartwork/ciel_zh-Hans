# -*- coding: utf-8 -*-
"""Read and write the game font: an 8192x4096 BC1 atlas plus a glyph table
compiled into the exe.

Atlas   Res_x64/font/FOT-SKIPSTD-B_0.g1t, container GT1G0600, texture type
        0x59 = BC1/DXT1, 8192x4096.  The glyph table addresses it in
        4096x2048 space, so every rect is doubled when sampling.

Table   8344 entries of 28 bytes at file offset 0x8D08D0 in CielnosurgeDX.exe:
            u32 code      UTF-8 bytes of the character packed big-endian
            i16 x, y      position in the 4096x2048 UV space
            i16 w, h      size in that space
            i32 ox        left bearing
            i32 oy        top offset from the line box
            i32 adv       advance width
            i32 pad
"""
import struct

EXE_TABLE_OFF = 0x8D08D0
ENTRY = 28
ENTRY_COUNT = 8344
COUNT_CONST = 8342          # appears once in the exe as a u32
ATLAS_W, ATLAS_H = 8192, 4096
UV_W, UV_H = 4096, 2048
SCALE = ATLAS_W // UV_W     # 2


def pack_code(ch):
    v = 0
    for b in ch.encode("utf-8"):
        v = (v << 8) | b
    return v


def unpack_code(v):
    b = []
    while v:
        b.append(v & 0xFF)
        v >>= 8
    if not b:
        return "\0"
    try:
        return bytes(reversed(b)).decode("utf-8")
    except UnicodeDecodeError:
        return None


class Glyph:
    __slots__ = ("code", "ch", "x", "y", "w", "h", "ox", "oy", "adv", "pad")

    def __init__(self, code, x, y, w, h, ox, oy, adv, pad=0):
        self.code, self.x, self.y, self.w, self.h = code, x, y, w, h
        self.ox, self.oy, self.adv, self.pad = ox, oy, adv, pad
        self.ch = unpack_code(code)

    def pack(self):
        return (struct.pack("<I", self.code)
                + struct.pack("<4h", self.x, self.y, self.w, self.h)
                + struct.pack("<4i", self.ox, self.oy, self.adv, self.pad))

    def __repr__(self):
        return "<Glyph %r %dx%d @%d,%d ox=%d oy=%d adv=%d>" % (
            self.ch, self.w, self.h, self.x, self.y, self.ox, self.oy, self.adv)


def read_table(exe_path):
    with open(exe_path, "rb") as f:
        f.seek(EXE_TABLE_OFF)
        blob = f.read(ENTRY_COUNT * ENTRY)
    out = []
    for i in range(ENTRY_COUNT):
        raw = blob[i * ENTRY:(i + 1) * ENTRY]
        code = struct.unpack("<I", raw[:4])[0]
        x, y, w, h = struct.unpack("<4h", raw[4:12])
        ox, oy, adv, pad = struct.unpack("<4i", raw[12:28])
        out.append(Glyph(code, x, y, w, h, ox, oy, adv, pad))
    return out


def write_table(glyphs):
    """Serialise back to the 28-byte layout, keeping the untouched fields."""
    if len(glyphs) > ENTRY_COUNT:
        raise ValueError("table holds %d entries, got %d" % (ENTRY_COUNT, len(glyphs)))
    out = bytearray()
    for g in glyphs:
        out += g.pack()
    # pad with the last entry repeated so the array keeps its declared length
    last = glyphs[-1].pack()
    while len(out) < ENTRY_COUNT * ENTRY:
        out += last
    return bytes(out)


# ---------------------------------------------------------------- BC1
def bc1_decode_block(b):
    c0, c1 = struct.unpack("<HH", b[:4])
    bits = int.from_bytes(b[4:8], "little")

    def rgb(c):
        return (((c >> 11) & 31) * 255 // 31, ((c >> 5) & 63) * 255 // 63, (c & 31) * 255 // 31)

    a, bb = rgb(c0), rgb(c1)
    if c0 > c1:
        pal = [a, bb,
               tuple((2 * a[i] + bb[i]) // 3 for i in range(3)),
               tuple((a[i] + 2 * bb[i]) // 3 for i in range(3))]
    else:
        pal = [a, bb, tuple((a[i] + bb[i]) // 2 for i in range(3)), (0, 0, 0)]
    return [pal[(bits >> (2 * i)) & 3] for i in range(16)]


def bc1_encode_block(px):
    """px: 16 greyscale values, row-major 4x4.  The atlas is a coverage mask,
    so encode along the black->white axis, which BC1 reproduces exactly."""
    lo, hi = min(px), max(px)
    if hi == lo:
        c = (hi >> 3 << 11) | (hi >> 2 << 5) | (hi >> 3)
        return struct.pack("<HHI", c, c, 0)

    def to565(v):
        return (v >> 3 << 11) | (v >> 2 << 5) | (v >> 3)

    c0, c1 = to565(hi), to565(lo)
    if c0 <= c1:                      # keep the 4-colour mode
        c0, c1 = c1, c0 if c1 != c0 else max(0, c1 - 1)
        if c0 <= c1:
            c1 = max(0, c0 - 1)
    bits = 0
    span = hi - lo
    for i, v in enumerate(px):
        t = (v - lo) * 3.0 / span
        idx = [0, 2, 3, 1][min(3, max(0, int(round(t))))]
        bits |= idx << (2 * i)
    return struct.pack("<HHI", c0, c1, bits)


class Atlas:
    """Greyscale coverage bitmap of the whole 8192x4096 texture."""

    def __init__(self, w=ATLAS_W, h=ATLAS_H, data=None):
        self.w, self.h = w, h
        self.data = data if data is not None else bytearray(w * h)

    @classmethod
    def from_g1t(cls, path):
        raw = open(path, "rb").read()
        hdr = raw[:0x2C]
        px = raw[0x2C:]
        a = cls()
        bw = ATLAS_W // 4
        for by in range(ATLAS_H // 4):
            for bx in range(bw):
                blk = px[(by * bw + bx) * 8:(by * bw + bx) * 8 + 8]
                cols = bc1_decode_block(blk)
                for i, c in enumerate(cols):
                    x, y = bx * 4 + (i & 3), by * 4 + (i >> 2)
                    a.data[y * ATLAS_W + x] = (c[0] + c[1] + c[2]) // 3
        a.header = hdr
        return a

    def to_g1t(self, header):
        out = bytearray(header)
        bw = ATLAS_W // 4
        for by in range(ATLAS_H // 4):
            row = by * 4
            for bx in range(bw):
                col = bx * 4
                px = [self.data[(row + dy) * ATLAS_W + col + dx]
                      for dy in range(4) for dx in range(4)]
                out += bc1_encode_block(px)
        return bytes(out)
