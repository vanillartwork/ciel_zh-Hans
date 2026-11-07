# Executable strings

[中文](executable-strings.md) | English

The main executable's `.rdata` contains UTF-8 confirmation prompts, network messages, menus, and status labels. `executable.csv` has 377 base entries, 318 translated; `exe_sited.csv` adds 70 translations in 0.9.8. After moving summary sources to the display layer, the current write manifest has 38 sites: 37 `display` and one `persisted`. Translation counts are not in-place write counts.

## Extraction and global replacement

`tools/export_exe_text.py` scans NUL-terminated UTF-8 strings, selecting candidates by kana/CJK content. The scan must accept complete multibyte sequences; narrow character patterns can truncate strings at symbols such as `※`, `★`, or full-width characters.

`patch_exe_strings.py` overwrites strings in place, preserving instruction references:

- UTF-8 translations must fit the original byte budget; remaining bytes become NULs.
- Matches require NUL boundaries on both sides, so a standalone `食器洗い` does not match the same text inside a longer description.
- Longer source strings are processed first.
- All matching uses the unmodified input, preventing a newly written translation from becoming another source match.
- This pass does not change file size or section headers.

## Retained strings and references

The 59 intentionally retained entries include debug/assertion messages, timing labels, column names, and development text. Reasons are recorded in `executable.csv` notes. Before editing:

```powershell
py -3 tools/check_exe_text.py --archives
```

Matches need manual interpretation:

| Match | What to establish |
|---|---|
| `.inc` | Character-map families are loaded at runtime. A comment, enum label, or identical text elsewhere does not by itself prove a key |
| Script | A word appearing in dialogue does not prove code depends on it |
| `.gbd` | Distinguish record/event IDs from display fields; see [GBD](dream-tables.en.md) |
| `.xml` | Separate comments and display text from structural fields |
| Complete `.bin` field | Determine whether it is a label, independent copy, or lookup key |

For example, `トイレ` in `point_data.bin` is a display name; the key is `ePOINT_YOME_TOILET`. `HymPが足りません。` also has an independent error-table copy. Keep fields whose uses remain uncertain.

## Address-authorized writes

Global replacement affects every identical copy and is suitable only when all copies are known to be display-only. The export filter also omitted format strings containing `%s`/`%d` and some CJK-only words. `exe_sites.py` handles reviewed sites instead:

- `exe_sited.csv` stores translations; entries already in `executable.csv` reuse their IDs.
- `data/exe-sites/<version>.csv` records RVA, source byte length/hash, use (`display` or `persisted`), and evidence. Permission at one address does not authorize other identical copies.
- The build validates source bytes, section, capacity, and overlaps before global replacement. The global pass excludes manifest IDs; the site pass refuses if the global pass changed an authorized range.
- Keep the exact conversion sequence, including flags, width, and `%%`, within the original byte budget. Text used as a format string must not gain `%` characters.
- `persisted` means the formatted text is stored in saves. Newline, full-width colon, and space counts are checked. Only play-time formatting remains in this category in the current manifest.

Review every reference to an address before authorizing it:

| Consumer | Interpretation |
|---|---|
| Format argument of `sprintf`/`snprintf` at `0x42e130`, `0x4bc9d0`, `0xa2f630`, or `0x4314c0` | The source is not compared, but follow the formatted result to establish its use |
| Text setter `0x7cc920`, dialogs `0x7cda30`/`0x7ce5e0`, or popup queue at `+0x2720` via `0x5af8d0` | Display path |
| Column lookup `0x79b4f0` or comparison by `memcmp` at `0xa03bc0` | Lookup key; preserve |
| Bytes shared with action-timing groups, or incomplete reference analysis | Preserve in place; use whole-string display replacement |

Recorded findings for `steam-2025-07`:

- The status table at `0xc6c8e0` has 30 records at stride `0x98` and is mapped by numeric ID. Task-name lookup at `0x75a490` compares English `TASK_*` labels. `起床` shares bytes with an action-timing group name and is not rewritten.
- `0x4ca520` builds a local event-ID-to-chapter-name table with inline copies; lookup uses IDs such as `ME01_00`.
- `名前`, `基準X`, and `嫁X回転` are column names. `回復量`, `創造力`, `指導力`, and `不可` are compared by `memcmp`. All remain Japanese.

## Saved summaries

`0x4cbd90` writes a formatted summary into each `SaveData/data*.bin` header: a `%s %s %s` line containing play time, chapter, and status, plus lines such as `総プレイ時間：…`. The load screen at `0x4d1ce0` reads lines 2/3/4, splits values at full-width colons, and splits the slot line at spaces.

From 0.9.8, the summary template, 12 chapter names, relationship names, status labels, `%d体`, and `%d枚` stay Japanese in the executable. The display layer replaces whole strings when setting UI text. This does not make the entire save byte-identical to an original-game save: play time is an explicit exception.

- The recorded status consumers are `0x4cbd90` for saving and `0x4ca4a0` for profile-page preparation; the latter's status buffer is not subsequently assigned to a widget. Chapters, relationships, and card counts are separately set on `info_*` controls. The load screen submits individual values, while slot labels concatenate chapter and status.
- `old_saves.py` generates exact mappings at build time for chapters, statuses, relationships, chapter/status combinations, and counts 0–999. It serves new saves as well as old ones. Translation data remains in the executable text tables, with display-only notes. It does not perform substring replacement or cover arbitrary counts.
- `%d日%d時間%d分` is still translated in place. The original load screen does not display that segment; the profile page does.
- Without a functioning display layer, retained Japanese values remain Japanese. `install.py --verify` reads `cielzh-loader.log` and `cielzh-status.txt` to report the last launch's result, not the current process state.

## Memos

`EVENT_PROCESS_WRITE_MEMO` stores its parameter in the save. A 104-byte Chinese memo was observed truncated at 92 bytes on a character boundary. The exact limit has not been located in code; 92, 93, and 94 are candidate limits. Three original Japanese memos are 95 bytes long.

From 0.9.8, `build_patch.py` excludes `kind=memo` entries from script injection. The display table derives translations from script data and accepts LF and CRLF forms; memos containing control tags are not treated as plain whole strings. Script-cell counts, newline-variant counts, and deduplicated mapping counts are different measures.

`old_memos.py` adds mappings for older Chinese from 0.9.4–0.9.7, Chinese written by preparation builds, and possible truncated Japanese. Candidates include full stored texts and UTF-8-safe cuts at 92/93/94 bytes. Conflicting candidates and candidates that could misidentify another complete memo are excluded. `tools/dev/gen_memo_history.py` generates `data/zh-Hans/_memo_history.csv` from release tags. Repairs happen at display time only; saves are not rewritten.

Keeping Japanese avoids additional truncation caused by longer translations, but some original texts can still exceed storage capacity. Display replacement does not guarantee that arbitrary text fits the UI.

Memo layout is reviewed at no more than 11 full-width characters per line and three lines. `tools/dev/rewrap_memos.py` requires extracted script data, checks by default, and writes only with `--apply`. This is not the general dialogue wrapping rule.

## Build order

1. `build_font.py` starts from the original executable and adds `.fontex`.
2. `exe_keys.py` identifies candidates to retain; `patch_exe_strings.py` writes allowed entries. Having 318 translations does not mean 318 strings are overwritten.
3. `exe_sites.py` applies authorized sites, validated before step 2.
4. The default build uses `pe_loader.py` to add the display-layer loading entry. The DLL and replacement table are installed separately.

Rebuilding the font from the original executable after translating strings would discard those translations.
