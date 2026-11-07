# Event scripts

[中文](event-script.md) | English

`inc/event/res/**/*.txt` files are UTF-8 CSV with a BOM and CRLF record separators. Their extension does not mean they are free-form text.

## Fields

Column numbers are zero-based:

| Column | Content | Treatment |
|---:|---|---|
| 11 | Character key, also used as a nameplate | Never translate in place |
| 12 | Dialogue | Translate |
| 13 | `EVENT_PROCESS_*` command | Preserve |
| 9, 15, 18, 20, 21, 22 | Developer comments | Preserve |

Some command parameters contain display text. `CMD_TEXT` in `tools/export_text.py` defines extraction coverage.

`EVENT_PROCESS_WRITE_MEMO` is an exception: parameters are still extracted for translation, but the 0.9.8 build excludes `kind=memo` entries before injection. The stored memo stays Japanese. Chinese display and repairs of old truncated memos are handled by the display layer; see [memos](executable-strings.en.md#memos).

Physical line breaks inside dialogue fields create lines in the game. Translations may consolidate lines, but adding lines requires checking the text box's capacity.

## Control codes

| Code | Meaning | Treatment |
|---|---|---|
| `<CLBU>`, `<CLY1>`, `<CLY2>`, `<OUT>`, `<mess>` | Color or style | Preserve the codes and their scope |
| `<CR>` | In-box break, often in item/help text | Do not increase the count |
| `{term}` | Dictionary index marker | Preserve braces and translate the term |

## Writing back

`tools/csvspan.py` locates the exact byte range of each field. Replace only that range. Reserializing the whole CSV can change quoting, the BOM, or line endings. An unchanged injection must be byte-identical to its input; see the [reference index](README.en.md#key-constraints).

## Speakers and keys

Column 11 is a character key that also appears as a nameplate. `inc/event/charanamemap.inc` indexes models by this string, including trailing full-width spaces: `イオン` is the normal model and `イオン　` the chibi model; `ネイ` and `ネイ　` are likewise distinct.

Placement rows select a character with this key. Subsequent rows, including dialogue, use it to identify which placed character receives speech and expressions. Column 8's `FS_CRY` is generic and must be combined with the character key to resolve `PC00_FS_CRY` in `charafacestancemap.inc`.

Translating the key breaks lookup rather than merely showing the wrong name. Symptoms include missing characters, frozen poses/lip movements, missing camera targets, and stalled positioning-dependent interactions. Patch versions 0.9.4 and 0.9.5 had this fault. Keep keys Japanese; use display-name commands or the display layer for Chinese labels. See [nameplate notes](../not-translated.md) (Chinese).

For `EVENT_PROCESS_CHANGE_DISPLAY_NAME`, parameter 1 (column 14) is the key and parameter 2 (column 15) is the displayed label. Only the latter is translatable.

`export_text.py` still exports keys and frequencies to `glossary_speakers.csv` as translator reference, but does not inject translations into the keys. `tools/selftest_inject.py` checks this distinction.
