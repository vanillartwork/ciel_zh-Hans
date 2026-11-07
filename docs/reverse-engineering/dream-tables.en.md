# Dream World tables (GBD)

[中文](dream-tables.md) | English

Version 0.9.8 translates four `.gbd` families under `inc/dream/`, each with 12 chapter files: 48 files in total. `ruin_control_data` and `ruin_parts_data` are not modified.

These are fixed-size record arrays without a separate file header. Later chapters repeat earlier records, so one translation often has multiple write locations. `FAMILIES` in [`gbd_text.py`](../../tools/gbd_text.py) defines the layouts for `steam-2025-07`.

## Fields

Offsets are relative to the record start; all numbers below are decimal.

| Family | Record size, bytes | Translated fields and offsets |
|---|---:|---|
| `dream_area_data` | 304 | Door/chapter subtitle `+28` |
| `event_history_data` | 844 | Story time `+48`, title `+104`, recap `+244` |
| `ruin_data` | 352 | Location name `+84` |
| `ruin_restore_data` | 336 | Restoration object name `+124` |

Record IDs, event IDs, and part IDs are not translated. Hiragana readings in `ruin_data` start at `+140`; 0.9.8 clears the bytes occupied by those readings so Japanese readings no longer accompany translated names. This is a separate clearing rule, not a translated field, and applies even without a translation.

## Write boundaries

Strings are UTF-8 and NUL-terminated. Nonzero residue often follows the NUL, so the distance to the next field is not translation capacity.

- A translation may occupy only as many bytes as the original Japanese. Zero-pad shorter text within that span.
- Preserve the original terminator and all following residue. Record and file lengths remain unchanged.
- Reject files whose lengths are not multiples of the record size, fields without a terminator, overlong translations, and embedded NULs.
- The read bound differs from the write budget. `max_bytes` in `dream.csv` is the original byte length plus one; validation reserves one byte for the terminator.

The `.bin` rule of clearing the entire fixed-width field must not be applied to GBD.

## Translations and repeated records

[`dream.csv`](../../data/zh-Hans/dream.csv) identifies entries by family, field, and source hash. It currently contains 781 entries: 12 subtitles, 552 HISTORY time/title/recap entries, 70 location names, and 147 restoration names.

Extraction records member paths, record names, fields, and offsets. Writing updates every corresponding occurrence. Updating only the earliest chapter is insufficient; identical Japanese strings in different field roles must not be conflated.

## Verification

Synthetic record tests need no game:

```powershell
py -3 tools/selftest_gbd_text.py
```

Locally verify writes against the original archive and the exported translation table:

```powershell
py -3 tools/gbd_text.py verify "D:\Test\Backup\PACK01.PAK" build/work/dream_text.csv
```

This command does not write the archive. Still check door subtitles, long HISTORY recaps and paging, and ruin names in the game. Since readings are cleared, record any unexpected list ordering for investigation.
