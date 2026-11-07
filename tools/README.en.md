# Tool index

[中文](README.md) | English

Tools require Python 3.10 or later. Core validation and text processing use the standard library; font building requires NumPy, Pillow, and a local font. Maintenance scripts may have additional dependencies documented in their source.

## Common commands

| Tool | Purpose |
|---|---|
| `hydrate.py` | Copy translation data to `work/`, optionally checking local game sources |
| `dehydrate.py` | Synchronize translations, statuses, and notes back to the repository |
| `validate.py` | Validate data without the game |
| `build.py` | Build the patch |
| `install.py` | Preview, install, restore, and check status |
| `preflight.py` | Check files, space, and versions before installation |

## Build components

| Tool | Purpose |
|---|---|
| `gamepath.py` | Find the game and original backups |
| `runlog.py`, `progress.py` | Logs and progress reporting |
| `env_strings.py` | Extract/write settings executable text |
| `export_text.py`, `export_exe_text.py` | Extract archive/executable text |
| `merge_repo.py` | Merge by ID and source hash |
| `workscript.py` | Extracted-script handoff in `script.zip`; convert to/from loose files with `unpack`/`pack` |
| `build_charset.py` | Generate candidate characters |
| `build_font.py` | Rebuild the atlas and glyph table |
| `export_charset.py` | Export characters supported by the final glyph table |
| `import_text.py` | Write translations back |
| `patch_exe_strings.py` | Replace all matching executable-string copies |
| `exe_sites.py` | Write only manifest-authorized executable sites |
| `old_saves.py` | Whole-summary mappings for old and new saves; counts 0–999 |
| `old_memos.py` | Map historical and unambiguous truncated memos to current text without editing saves |
| `build_text_table.py` | Build the display table for names, retained strings, summaries, and memos |
| `gbd_text.py` | Export/write Dream World `inc/dream/*.gbd` fields |
| `build_patch.py` | Produce staged files |
| `pe_loader.py` | Write the `emit_entry.exe` output into an executable copy |
| `repack_pak.py` | Package archives and generate in-place plans |

Supporting modules include `gustpak.py` for archives, `csvspan.py` for CSV byte ranges, `font_atlas.py` for glyph structures, and `bc1.py` for compression.

## Verification

| Tool | Coverage | Game needed? |
|---|---|---|
| `selftest_validate.py` | Validator behavior | No |
| `selftest_install.py` | Installation and restoration | No |
| `selftest_workscript.py` | Single-source rules, duplicate/damaged members, interrupted ZIP replacement, merge/injection readers, and term ordering | No |
| `selftest_pe_loader.py` | Synthetic PE loader entries, repeated application, and refusal paths; compile native tools first | No |
| `selftest_exe_sites.py` | Authorized copies, format strings, persisted text, and summary mappings | No |
| `selftest_old_memos.py` | Historical memos, UTF-8 truncation, ambiguity, and complete-text conflicts | No |
| `selftest_text_table.py` | Table format, newline variants, duplicates, and conflicts | No |
| `selftest_gbd_text.py` | GBD write spans, residual bytes, and IDs | No |
| `exe_sites.py --check` | Address-manifest/translation consistency | No |
| `test_roundtrip.py` | Byte-identical unchanged rebuilding | Yes |
| `check_exe_text.py` | Executable locations, lengths, and data references | Yes |

## Maintenance

| Tool | Purpose |
|---|---|
| `repo_export.py` | Convert extraction output to repository data |
| `build_glossary.py` | Gather terminology |
| `release_notes.py` | Generate release-note reference material; CI does not publish it |
| `normalize_cn.py` | Normalize character forms |
| `fix_names.py`, `unify_dupes.py` | Unify names and duplicate-source translations |
| `apply_official.py`, `official_glossary.py` | Import official terminology |
| `make_batches.py`, `merge_batches.py` | Split/merge translation batches |
| `sync_from.py`, `audit_clone.py` | Synchronize/audit working trees |
| `workorder.py` | Generate translation work lists |
| `dev/import_dream_batches.py` | Validate external Dream World batches and write `dream.csv` |
| `dev/rewrap_memos.py` | Check memo wrapping from extracted scripts; writes only with `--apply` |
| `dev/gen_memo_history.py` | Generate `_memo_history.csv` from release tags for display compatibility |

## Development conventions

Modules that do not need the game should import independently and resolve game paths only when needed. File operations must make their destination and scope explicit, with appropriate preview and recovery behavior. Errors should identify the cause, affected path, and next step.

See [building](../docs/build.en.md), the [pipeline](../docs/pipeline.en.md), and [validation](../docs/validation.en.md).
