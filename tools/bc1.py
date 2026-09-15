# -*- coding: utf-8 -*-
"""Vectorised BC1/DXT1 for the font atlas.

The atlas is a coverage mask, not a picture: red is pinned at 255 and the
glyph shape lives in green/blue.  Encoding therefore only has to place two
endpoints along the coverage axis with red saturated, which BC1 reproduces
almost exactly (green keeps 6 bits, blue 5).

Both directions work a band of block rows at a time rather than the whole
atlas at once.  The arithmetic is unchanged -- every value is computed from
its own 4x4 block, so a block does not care which band it was in -- but the
temporaries stop scaling with the atlas.  At 8192x4096 the whole-atlas form
needed about 1.2 GB resident, most of it in two places: the index array that
`take_along_axis` promotes to intp (268 MB), and `t`/`rint(t)` in the encoder,
which are float64 because the 3.0 in the expression is a Python float
(268 MB each).  A band divides all of those by the number of bands.

Blocks are laid out row of blocks by row of blocks, so banding by block rows
keeps them in exactly the order the format expects.
"""
import numpy as np

R_BITS = 31 << 11          # red pinned to full

# 32 block rows = 128 pixel rows.  Large enough that the per-call NumPy
# overhead stays irrelevant, small enough to keep the temporaries modest.
BLOCK_ROWS = 32


def _bands(rows, step=BLOCK_ROWS):
    """(first block row, last block row) for each band, in order."""
    for r0 in range(0, rows, step):
        yield r0, min(r0 + step, rows)


def _decode_band(b, bw):
    """b: (n, 8) uint8 of BC1 blocks.  Returns (rows*4, bw*4) float32 coverage."""
    nb = len(b)
    c0 = b[:, 0].astype(np.uint16) | (b[:, 1].astype(np.uint16) << 8)
    c1 = b[:, 2].astype(np.uint16) | (b[:, 3].astype(np.uint16) << 8)
    bits = (b[:, 4].astype(np.uint32) | (b[:, 5].astype(np.uint32) << 8)
            | (b[:, 6].astype(np.uint32) << 16) | (b[:, 7].astype(np.uint32) << 24))
    g0 = ((c0 >> 5) & 63).astype(np.float32) * (255.0 / 63)
    g1 = ((c1 >> 5) & 63).astype(np.float32) * (255.0 / 63)
    four = c0 > c1
    pal = np.empty((nb, 4), np.float32)
    pal[:, 0] = g0
    pal[:, 1] = g1
    pal[:, 2] = np.where(four, (2 * g0 + g1) / 3, (g0 + g1) / 2)
    pal[:, 3] = np.where(four, (g0 + 2 * g1) / 3, 0)
    idx = np.empty((nb, 16), np.uint8)
    for i in range(16):
        idx[:, i] = (bits >> (2 * i)) & 3
    v = np.take_along_axis(pal, idx.astype(np.intp), axis=1)
    rows = nb // bw
    return v.reshape(rows, bw, 4, 4).transpose(0, 2, 1, 3).reshape(rows * 4, bw * 4)


def decode(px, w, h):
    """px: BC1 bytes.  Returns the (h, w) uint8 coverage plane (green)."""
    bw, bh = w // 4, h // 4
    nb = bw * bh
    blocks = np.frombuffer(px[:nb * 8], dtype=np.uint8).reshape(nb, 8)
    out = np.empty((h, w), np.uint8)
    for r0, r1 in _bands(bh):
        v = _decode_band(blocks[r0 * bw:r1 * bw], bw)
        out[r0 * 4:r1 * 4] = np.clip(v + 0.5, 0, 255).astype(np.uint8)
    return out


def _encode_band(blocks, out):
    """blocks: (n, 16) uint8.  Writes (n, 8) BC1 bytes into `out`."""
    lo = blocks.min(axis=1).astype(np.int32)
    hi = blocks.max(axis=1).astype(np.int32)
    c0 = (R_BITS | ((hi >> 2) << 5) | (hi >> 3)).astype(np.int32)
    c1 = (R_BITS | ((lo >> 2) << 5) | (lo >> 3)).astype(np.int32)
    solid = c0 <= c1                       # flat block: one colour, index 0
    span = np.maximum(hi - lo, 1)
    t = (blocks.astype(np.int32) - lo[:, None]) * 3.0 / span[:, None]
    q = np.clip(np.rint(t), 0, 3).astype(np.int32)
    # palette: 0=c0(hi) 1=c1(lo) 2=(2hi+lo)/3 3=(hi+2lo)/3, and t runs lo->hi
    idx = np.array([1, 3, 2, 0], np.int32)[q]
    idx[solid] = 0
    c1 = np.where(solid, c0, c1)
    bits = np.zeros(len(blocks), np.uint32)
    for i in range(16):
        bits |= (idx[:, i].astype(np.uint32) & 3) << (2 * i)
    out[:, 0] = c0 & 0xFF
    out[:, 1] = (c0 >> 8) & 0xFF
    out[:, 2] = c1 & 0xFF
    out[:, 3] = (c1 >> 8) & 0xFF
    out[:, 4] = bits & 0xFF
    out[:, 5] = (bits >> 8) & 0xFF
    out[:, 6] = (bits >> 16) & 0xFF
    out[:, 7] = (bits >> 24) & 0xFF


def encode(img):
    """img: (h, w) uint8 coverage.  Returns BC1 bytes with red saturated."""
    h, w = img.shape
    bw, bh = w // 4, h // 4
    out = np.empty((bw * bh, 8), np.uint8)
    for r0, r1 in _bands(bh):
        band = img[r0 * 4:r1 * 4]
        blocks = (band.reshape(r1 - r0, 4, bw, 4)
                      .transpose(0, 2, 1, 3).reshape(-1, 16))
        _encode_band(blocks, out[r0 * bw:r1 * bw])
    return out.tobytes()
