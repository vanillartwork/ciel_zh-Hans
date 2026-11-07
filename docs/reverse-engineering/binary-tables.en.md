# Binary tables

[中文](binary-tables.md) | English

`inc/**/*.bin` contains items, help, mail, Sharl profiles, BGM descriptions, server errors, and other text. This page covers `.bin`; the [Dream World GBD tables](dream-tables.en.md) added in 0.9.8 have different write boundaries.

## Fixed-width fields

Strings occupy fixed-width UTF-8 fields. After writing a translation, zero-fill the remaining field space.

- Reserve one byte for the NUL terminator.
- Common CJK characters usually take three bytes; a 12-byte field fits at most three such characters plus NUL.
- `validate.py` and `import_text.py` check length limits.

Known layouts are defined in `BIN_SCHEMA` in `tools/export_text.py`. Do not infer capacity from a run of zero bytes: fields may contain old residual data.

## Headers and split descriptions

Some tables retain CSV-style headers and field names. Japanese column names may be lookup keys, not UI labels. Keep them until their consumers are understood; see [executable strings](executable-strings.en.md).

Long descriptions may span consecutive fields. Translate only the current segment, using `full_source_context` in the extracted working data for context. Do not put the entire description in one field.

## Sharl names

| File | Record size | Name offset | Field width |
|---|---:|---:|---:|
| `inc/sharl/sharl_name_data.bin` | 72 bytes | `+0x00` | 32 bytes |
| `inc/sharl/sharl_npcrating_data.bin` | 536 bytes | `+0x1DC` | 32 bytes |

Each name is a complete string with 31 usable bytes, allowing up to ten common CJK characters. These names and profile entries are translated. Clear residual bytes at the field's end when writing.

## Preserved content

`inc/globaldata/ngword_data.bin` is the blocked-word list used to match player input. Keep its original entries. The injector's preservation list prevents writes; empty Chinese cells here are not missing UI translations.
