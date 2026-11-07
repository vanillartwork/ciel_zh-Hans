# Gust PAK archives

[中文](pak-format.md) | English

KTGL resource archives are stored under the game's `Res_x64/` directory.

| File | Approximate size | Main contents |
|---|---:|---|
| `PACK00_01.PAK` | 1.7 GB | Textures, models, and font atlas |
| `PACK00_02.PAK` | 2.3 GB | Other resources |
| `PACK00_03.PAK` | 1.1 GB | Other resources |
| `PACK01.PAK` | 33 MB | Scripts, UI, and data tables |
| `PACK02.PAK` | 125 KB | Small resources |

## Layout

Integers are little-endian:

```text
Offset 0    Header: 16 bytes
            u32 version       0x00020000
            u32 nb_files
            u32 header_size   16
            u32 flags

Offset 16   Entry table: 168 bytes (0xA8) per entry
            char name[128]    XOR-encoded filename
            u32 size          Content length
            u8  key[20]       Entry XOR key
            u64 offset        Relative to the start of the data area
            u32 flags
            4 bytes padding

Data area   Starts at 16 + nb_files * 168
```

Names and contents are XORed cyclically with the entry's 20-byte key. An all-zero key leaves the data unchanged. Decoded names are NUL-terminated UTF-8, normally with a leading backslash and backslash-separated paths:

```text
\inc\event\res\01\ma01_tt01.txt
```

## Rebuilding

`rebuild()` in `tools/gustpak.py` preserves each entry's `raw_name` bytes and key while recalculating sizes and offsets. Re-encoding an unchanged filename must not alter its bytes.

`tools/test_roundtrip.py` compares unchanged rebuilds. The supported `PACK01.PAK` is 33,781,160 bytes; compare the complete contents. With NumPy installed, larger members use vectorized XOR; smaller members and environments without NumPy use the standard-library implementation.

## Contents

`PACK01.PAK` contains 3,750 entries:

| Extension | Count | Content |
|---|---:|---|
| `.txt` | 3,046 | Event scripts and other CSV |
| `.xml` | 248 | UI layouts |
| `.bin` | 158 | Data tables |
| `.inc` | 153 | Definition tables and C++-style fragments, some read at runtime |
| `.gbd` | 72 | Dream World chapters, history, ruins, and control data; see [GBD layout](dream-tables.en.md) |
| Other | 73 | `.bas`, `.frm`, etc. |

Do not treat all `.inc` files as unused compilation artifacts. The character-name, body-stance, face-stance, and action maps are read at runtime. A matching string in another table is not sufficient proof of a lookup key; inspect its code references. See [executable strings](executable-strings.en.md).
