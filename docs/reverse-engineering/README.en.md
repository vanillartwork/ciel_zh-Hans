# File format reference

[中文](README.md) | English

These notes describe resource containers, text encoding, and glyph structures used by localization tools and ports to other languages.

| Document | Contents |
|---|---|
| [Gust PAK](pak-format.en.md) | Archive layout, XOR processing, and rebuilding |
| [Event scripts](event-script.en.md) | CSV fields and control codes |
| [Binary tables](binary-tables.en.md) | Fixed-width fields and length limits |
| [Dream World tables](dream-tables.en.md) | GBD records, HISTORY, repeated records, and readings |
| [Font atlas and glyph table](font-and-glyph-table.en.md) | Atlas encoding, executable tables, and expansion |
| [Executable strings](executable-strings.en.md) | Extraction, write permissions, and display-only text |

## Scope

The notes apply to the [supported Windows DX version](../supported-versions.en.md). Reverify offsets and structures for other versions. No game files are included; local verification requires a legally owned game.

This project does not include or accept analysis or bypasses of DRM, licensing, anti-piracy, access control, or other technical protection measures. Related issues and pull requests will be closed.

## Key constraints

- The engine reads packed resources; loose files do not directly override them.
- Keep the font atlas at 8192×4096 and its UV space at 4096×2048.
- Allocate glyphs on 4×4-pixel boundaries to avoid compression-block conflicts and coordinate truncation.
- Replace script fields by byte range, preserving all other source bytes.
- Check executable-string consumers before editing; displayed strings may also be lookup keys.

An unchanged rebuild must match the input byte for byte. `test_roundtrip.py` takes three arguments: the original resource directory, an unpacked extraction directory, and the output directory. It modifies test CSVs; follow the [validation instructions](../validation.en.md#checks-requiring-game-files) in a separate test directory.
