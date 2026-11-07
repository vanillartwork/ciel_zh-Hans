# Translation data format

[中文](translation-data.md) | English

CSV files under `data/zh-Hans/` are divided by chapter or module. Each entry contains Japanese source text, its translation, and validation metadata.

## Fields

```csv
id,jp,zh,status,speaker,src,ctl,lines,note
inc/event/res/01/ma01_tt01.txt#2#12,<CLBU>ありがと、慰めてくれて……。,<CLBU>谢谢你，安慰了我……,translated,依恩,24248beb4c,<CLBU> br=0 nl=0,1,keep-tags <CLBU>
```

| Field | Meaning | Editing policy |
|---|---|---|
| `id` | Unique entry identifier | Preserve |
| `jp` | Japanese source | Preserve |
| `zh` | Translation | Editable |
| `status` | Translation status | Editable |
| `note` | Notes or questions | Editable |
| `src` | First 10 hexadecimal digits of the source SHA-1 | Generated |
| `ctl` | Source control codes, braces, and line-break metadata | Generated |
| `speaker`, `lines`, `max_bytes`, `max_chars`, `attr`, etc. | Speaker, limits, and structural metadata | Generated |

Routine translation edits should change only `zh`, `status`, and `note`. The validator recomputes `src` and `ctl` to check consistency with `jp`.

## Identifiers

Script IDs use `archive-path#row#column`, for example `inc/event/res/01/ma01_tt01.txt#2#12`.

| Format | Source |
|---|---|
| `ui/...#offset` | UI XML |
| `item:N` | Item tables |
| `global:N` | Help, mail, and other global tables |
| `exe:hash` | Executable strings |
| `area.title:hash`, `history.title:hash`, etc. | Dream World fields in `dream.csv` |
| `display:hash` | Display-only translations in `display.csv` |
| `spk:N` / `term:N` | Speakers or terms |

IDs drive merging and validation exceptions. Do not renumber them or duplicate them across files. Recheck source locations and hashes after game updates.

`display.csv` has only `id,jp,zh,status,note`; it contains no executable offsets. Translated entries become display-table candidates. A source phrase that is already an existing Chinese translation is excluded to avoid translating translated text again.

## Data introduced in 0.9.8

- `dream.csv` deduplicates by table family, field, and source text. `occurrences` counts write locations. `max_bytes` includes the terminator and is the original byte length plus one, not the whole field capacity.
- `exe_sited.csv` adds executable translations using the same `exe:` identifier scheme as `executable.csv`. `data/exe-sites/<game-version>.csv` grants write permission by address and records source hashes and evidence. Adding a translation does not authorize other copies of the same text. Here, `max_bytes` excludes the terminator.
- Format strings must preserve the order and full form of conversions such as `%s` and `%d`. Manifest entries marked `persisted` also preserve newlines, full-width colons, and spaces. Currently only play-time formatting is still translated in place in that category; other summary sources stay Japanese and use the display layer.
- `old_saves.py` generates whole-string summary combinations for old and new saves, including counts from 0 to 999. Current memo translations remain in the script data. `_memo_history.csv` stores translations from earlier releases, generated from tags by `tools/dev/gen_memo_history.py`; it is compatibility data, not a new translation queue. `old_memos.py` derives display mappings for old complete text and unambiguous truncations without rewriting saves.

## Structural metadata

`<CLBU> br=0 nl=1` in `ctl` means the source contains `<CLBU>`, no brace pairs, and one line break. Together with `jp` and `src`, this allows structural validation without game files.

## Status values

| Value | Meaning |
|---|---|
| `translated` | Complete |
| `draft` | Draft awaiting proofreading |
| `needs-review` | Requires review |
| `todo` | Awaiting translation |
| `skip` | Intentionally retained; explain in `note` |

The 290 blocked-word entries and the blank nameplate still use `todo`, but they are not missing UI translations. Injection has separate preservation rules. Do not fill every empty row based on status alone. See [untranslated content](not-translated.md) (Chinese).

## Encoding and line breaks

- UTF-8 without BOM; LF between CSV records.
- Preserve CRLF inside source fields.
- Quote fields containing commas or newlines; double embedded quotes as `""`.
- Keep row order and avoid unrelated file-wide newline changes.

`.gitattributes` marks translation CSV files as `-text` so Git does not normalize embedded line breaks. Editors must preserve them too; see [CSV editing](editing-csv.en.md).

## Working copies

Use the ignored `work/` directory for batch editing:

```powershell
py -3 tools/hydrate.py
py -3 tools/hydrate.py --game  # Alternative: also verify local game sources
# Edit work/zh-Hans/
py -3 tools/dehydrate.py
py -3 tools/validate.py
```

Choose one of the first two commands. `dehydrate.py` copies `zh`, `status`, and `note` back by ID; source and technical fields remain authoritative in `data/`.
