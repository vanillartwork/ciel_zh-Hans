# -*- coding: utf-8 -*-
"""Vectorised BC1/DXT1 for the font atlas.

The atlas is a coverage mask, not a picture: red is pinned at 255 and the
glyph shape lives in green/blue.  Encoding therefore only has to place two
endpoints along the coverage axis with red saturated, which BC1 reproduces
almost exactly (green keeps 6 bits, blue 5).
"""
import numpy as np

R_BITS = 31 << 11          # red pinned to full


def decode(px, w, h):
    """px: BC1 bytes.  Returns the (h, w) uint8 coverage plane (green)."""
    nb = (w // 4) * (h // 4)
    b = np.frombuffer(px[:nb * 8], dtype=np.uint8).reshape(nb, 8)
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
    v = v.reshape(h // 4, w // 4, 4, 4).transpose(0, 2, 1, 3).reshape(h, w)
    return np.clip(v + 0.5, 0, 255).astype(np.uint8)


def encode(img):
    """img: (h, w) uint8 coverage.  Returns BC1 bytes with red saturated."""
    h, w = img.shape
    blocks = img.reshape(h // 4, 4, w // 4, 4).transpose(0, 2, 1, 3).reshape(-1, 16)
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
    out = np.empty((len(blocks), 8), np.uint8)
    out[:, 0] = c0 & 0xFF
    out[:, 1] = (c0 >> 8) & 0xFF
    out[:, 2] = c1 & 0xFF
    out[:, 3] = (c1 >> 8) & 0xFF
    out[:, 4] = bits & 0xFF
    out[:, 5] = (bits >> 8) & 0xFF
    out[:, 6] = (bits >> 16) & 0xFF
    out[:, 7] = (bits >> 24) & 0xFF
    return out.tobytes()
