# Build pipeline

[中文](pipeline.md) | English

The tools extract Japanese text from a local game, apply repository translations to copies, and generate installation data:

```text
Local game → extract → merge by id and src → write text → package → install
                          ↑                    ↑
                     data/zh-Hans/       Atlas and glyph table
```

`build.py` builds the patch. `install.py` manages backups and writes to the game directory.

## 1. Locate original resources

`gamepath.py` uses the command-line directory, `CIEL_NOSURGE_DX`, Steam registration, and common installation paths. `source_file()` and `source_pak()` prefer originals in `Backup/`, so an installed translation is not mistaken for Japanese source text.

## 2. Extract text

| Source | Tool | Content |
|---|---|---|
| `inc/event/res/**/*.txt` | `export_text.py` | Dialogue and speaker references |
| `ui/**/*.xml` | `export_text.py` | UI text |
| `inc/**/*.bin` | `export_text.py` | Fixed-width item, help, mail, and other fields |
| `inc/dream/*.gbd` | `gbd_text.py` | Chapter subtitles, HISTORY, ruins, and restoration names |
| `CielnosurgeDX.exe` | `export_exe_text.py` | Embedded UTF-8 strings |
| `CielnosurgeDX_Env.exe` | `env_strings.py` | Settings text in Win32 resources |

Only designated script fields are translatable. Commands and developer comments stay unchanged. See [event scripts](reverse-engineering/event-script.en.md) and [binary tables](reverse-engineering/binary-tables.en.md).

About 130 extracted script CSVs are stored in one uncompressed `script.zip`. Term collection, merging, character collection for the font, and injection read it through `workscript.py`. The recorded local comparison reduced a complete build from roughly 45 to 29 seconds; this is not a fixed installation-time promise. CSV encoding and serialization stay unchanged, with fixed ZIP member order and timestamps.

- Readers accept one source: `script.zip` or `script/`. They reject both together, duplicate names, unexpected names/order, damaged archives, or failed CRC checks, without fallback. Fresh extraction is an exception: it removes an old `script/` before generating the archive.
- There is no independent expected-member manifest yet. With neither source present, the reader returns an empty list; merging may skip a missing script member and still succeed. Missing members are therefore not guaranteed to stop the build. Compare member sets separately before release.
- `test_roundtrip.py` and `make_batches.py` require loose files. `repo_export.py`, `hydrate.py`, `dev/rewrap_memos.py`, and `dev/gen_memo_history.py` can read either form. See [maintenance instructions](build.en.md#script-intermediates-and-maintenance) for conversion commands and limitations.

## 3. Merge translations

`merge_repo.py` matches `id` and compares the locally extracted source hash with `src`. Matching entries receive `zh`; mismatches keep the source text. A mismatch rate above 2% stops the build. See the [data format](translation-data.en.md).

## 4. Rebuild the font

`build_charset.py` collects required characters and adds GB2312. `build_font.py` rebuilds the atlas, writes the extended glyph table into `.fontex`, and updates references and counts. See the [font reference](reverse-engineering/font-and-glyph-table.en.md) for dimensions and alignment.

## 5. Write text and executable resources

`build_patch.py` coordinates these operations:

- Script CSV: `csvspan.py` replaces individual field byte ranges and preserves other bytes. Entries with `kind=memo` are excluded before injection, leaving `EVENT_PROCESS_WRITE_MEMO` parameters in Japanese.
- Binary tables: UTF-8 translations occupy fixed-width fields; unused space is zero-filled.
- Dream World tables: writes stay within the bytes occupied by the original text. Location readings are cleared separately; IDs and unknown bytes are preserved.
- Executable strings: translations are applied to the font-patched executable and must fit the original byte budget. `exe_sites.py` validates authorized addresses before global replacement, which excludes those IDs.
- Display layer: character keys and memo source text stay unchanged. `cielzh-text.bin` supplies display translations, including chapter/status/relationship/count summaries. `old_saves.py` serves both old and new saves, with count mappings for 0–999. `old_memos.py` adds historical Chinese and unambiguous truncated texts without editing saves. Play-time formatting remains an in-place executable translation; see [executable strings](reverse-engineering/executable-strings.en.md). The PE tool adds the `cielzh.dll` loading entry to the executable copy.
- Settings executable: translated Win32 resources are written back.

Text is normally staged in an uncompressed `stage/text.zip` to reduce repeated small-file access. `--loose` stages separate files for debugging.

## 6. Package and create the manifest

`repack_pak.py` rebuilds `PACK01.PAK`, retaining raw filename bytes and XOR keys. The old and new font atlas have equal lengths, so `PACK00_01.PAK` needs only about 16.8 MB of replacement data and an `inplace.json` plan, not a full rebuild.

`build.py` writes `manifest.json` with the patch version, original executable hash, output sizes, and SHA-256 hashes.

## 7. Install and restore

After checking the game version, `install.py` backs up original files or ranges under `Backup/`. Whole files are replaced through temporary files, verification, and rename; font data is written to the planned range. `Backup/inplace.json` allows restoration after the build directory is removed.

Before modification, the installer records the entire transaction in `Backup/install_tx.json` and keeps pre-installation copies in `Backup/rollback/`. A failure before commit restores the previous installed state. An interruption after commit requires cleanup only. Failed recovery preserves the copies for retry.

If a new layout would leave old patched ranges behind, restore the old patch first. `Backup/created.json` tracks the DLL and replacement table; the installer does not take ownership of unrelated files with the same names.

## Verification

```powershell
./native/build.ps1
py -3 tools/build.py --version 0.9.8
py -3 tools/install.py --apply
```

An unchanged rebuild must pass `tools/test_roundtrip.py` byte for byte. `selftest_install.py` and `selftest_install_flow.py` cover installation and restoration; EXE sites, GBD fields, and display mappings have separate tests. See the [tool index](../tools/README.en.md).
