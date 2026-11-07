# Font atlas and glyph table

[中文](font-and-glyph-table.md) | English

Offsets below apply to the recorded game version and must be located again for other builds.

## Atlas

```text
Archive path    res_x64/font/fot-skipstd-b_0.g1t
Container       GT1G0600
Format          0x59, BC1 / DXT1
Physical size   8192 × 4096
UV space        4096 × 2048
```

Physical coordinates are twice the glyph UV coordinates. R is fixed at 255; coverage is stored in G/B. Encoding and decoding must preserve this convention.

In the G1T file, `0x25` is the format byte. The high and low nibbles of `0x26` give the power-of-two exponents for height and width. Pixel data starts at `0x2C`. Relevant format values are `0x59` for BC1, `0x5B` for BC3, and `0x01` for RGBA.

## Glyph table and descriptor

The original table starts at executable file offset `0x8D08D0`, with 8,344 records of 28 bytes:

```c
struct Glyph {
    u32 code;        // UTF-8 bytes combined into a big-endian integer
    i16 x, y, w, h;  // UV coordinates and dimensions
    i32 ox, oy;      // Drawing offsets
    i32 adv;         // Advance
    i32 pad;
};
```

`code` is not a Unicode code point. The engine binary-searches by this value, so the table must stay sorted.

The descriptor is at `0x8D08A0`:

```c
struct FontDesc {
    u16 uv_w, uv_h;  // 4096, 2048
    u32 pad;
    char *texture;
    u64 count;       // Only the low 16 bits are read
};
```

The count at `0x8D08B0` is read by `movzx r8d, word [rdx+0x10]`, limiting it to 65,535. A RIP-relative reference to the table is at file offset `0x59656F`:

```asm
lea r9, [rip+disp32]      ; 4C 8D 0D xx xx xx xx
```

## Expansion

The original table contains 6,718 CJK characters, of which 2,243 occur in game text. The build removes unused original glyphs to make room for the 7,445 GB2312 characters. The documented build has 9,351 glyphs and approximately 89.3% atlas occupancy.

The expanded table goes into a new `.fontex` section at RVA `0x145C000`; references and the u16 count are updated. Space after the original 12 section headers accommodates the added header.

## Dimensions and alignment

- Keep the physical atlas at 8192×4096 and UV space at 4096×2048. The engine does not automatically adjust UV scaling to descriptor dimensions.
- Allocate in 4-pixel blocks to match BC1 compression blocks and keep coordinates integral when divided by two.
- Install the atlas and glyph table together. The engine does not read loose overrides; the atlas belongs in `PACK00_01.PAK`.

The atlas remains 16,777,260 bytes long, allowing an in-place archive update instead of a full rebuild.

## Font and rendering

GB2312 characters use Microsoft YaHei Bold. Kana, Latin letters, punctuation, and Japanese-only characters retain original glyphs according to build rules. Characters unavailable in the source font fall back to original glyphs.

Recorded parameters are `msyhbd.ttc`, 55 px, `ANCHOR_X = 67`, and `ANCHOR_Y = 58`. Recalibrate after changing fonts and check weight and baseline in the game.

## Originals and validation

`pristine_exe()` requires an original executable with 12 sections and prefers the copy in `Backup/`, preventing repeated `.fontex` additions. The atlas must also come from the correct original resource; restore before building if necessary.

Run `tools/export_charset.py` after rebuilding to update the actual supported-character inventory. Check dialogue, menus, retained Japanese, and long text in the game.
