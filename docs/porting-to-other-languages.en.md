# Porting to other languages

[中文](porting-to-other-languages.md) | English

Archive and injection code can be reused, but directory conventions, font generation, and validation still include Simplified Chinese assumptions. Adapt the data, font, and checks separately.

## Translation data

Maintain the target language in a separate branch or fork. Initially, keep `data/zh-Hans/` and the `zh` column name:

1. Preserve `id`, `jp`, `src`, `ctl`, and field limits.
2. Clear `zh` for entries to translate and set their status to `todo`.
3. Preserve technically justified `skip` entries and notes.
4. Maintain a target-language glossary, glyph inventory, and reviewed validation exceptions.

Here `zh` is simply the translation column the tools read. Renaming it or changing the language directory requires code changes: `validate.py`, `hydrate.py`, `dehydrate.py`, and `merge_repo.py` still use the `zh-Hans` subdirectory. `validate.py --data` selects the data root; `merge_repo.py` takes `<data-root> <extraction-directory>`. Neither changes the subdirectory convention.

## Reusable components

| Component | Purpose |
|---|---|
| `gustpak.py`, `repack_pak.py` | Archive reading/writing |
| `csvspan.py`, `import_text.py` | Field-range injection |
| `export_text.py`, `export_exe_text.py` | Source extraction |
| `patch_exe_strings.py` | Executable-string replacement |
| `build.py`, `install.py`, `preflight.py` | Building, installation, and version checks |

Review directory conventions, font stages, and installer UI. Keep character keys and write-memo parameters unchanged; generate target-language display mappings instead. Do not carry the Chinese `_memo_history.csv` into another language without deciding which historical saves that port should support.

## Font

`build_charset.py` currently retains required game glyphs and adds GB2312. Collect actual target-language characters and adjust the candidate set, font, and rendering parameters.

Latin or Cyrillic scripts may fit existing coverage; Korean and Traditional Chinese usually require additions. Use actual packing results to determine capacity. Keep the atlas at 8192×4096, UV space at 4096×2048, and allocations aligned to 4 pixels. Export `data/charset.txt` from the final glyph table. See the [font reference](reverse-engineering/font-and-glyph-table.en.md).

## Validation and layout

| Check | Adaptation |
|---|---|
| Kana detection | Decide whether kana indicates missing translation in the target language |
| `MAX_DIALOGUE_LINE` | Adjust for target-language glyph widths and actual UI layout |
| Glossary | Replace preferred and forbidden translations |
| `allow.csv` | Review every exception; language-specific exemptions cannot be copied blindly |
| Byte/character limits | Keep game-format constraints and measure the actual encoding |

`.bin` and executable text usually use UTF-8 byte budgets; settings resources also impose character limits. Even predominantly single-byte languages must obey field sizes and be checked on screen.

## Verification

Pass data validation and unchanged round-trip tests first, then check long text, menus, missing glyphs, and installation/restoration in the game. See the [format reference](reverse-engineering/README.en.md).

General tool improvements can be submitted upstream; maintain target-language translations in the fork.
