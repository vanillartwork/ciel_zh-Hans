# Validation

[中文](validation.md) | English

Validation uses repository source text and metadata; game files are not required. Errors fail validation. Warnings need review, and translation quality still requires proofreading.

```powershell
py -3 tools/validate.py
py -3 tools/validate.py --only script/06
py -3 tools/validate.py --changed-only
py -3 tools/validate.py --strict
py -3 tools/validate.py --format github
```

Run a full check before submitting. A partial check cannot find problems in files it did not inspect.

## Checks

| Category | Checks |
|---|---|
| Data structure | Encoding, BOM, record separators, duplicate IDs, status/translation consistency |
| Source consistency | `src` and `ctl` agree with `jp` |
| Control codes | Non-break codes preserved, no added `<CR>`, balanced braces with matching counts |
| Length | Binary-field and executable byte budgets; settings text character limits |
| Display and terminology | Missing glyphs, remaining kana, forbidden translations |
| Consistency | Different translations of the same source within a file |

These generally produce errors. Fewer `<CR>` codes, script lines over 24 characters, and differing script translations of the same source produce warnings. `--strict` also warns about changed physical line counts. Conflicting non-script translations are errors. CRLF validation concerns record separators, not line breaks inside source fields.

## Glyph inventory and exceptions

After rebuilding the font, run:

```powershell
py -3 tools/export_charset.py
```

[data/charset.txt](../data/charset.txt) must come from the final executable's actual glyph table. A candidate character set is insufficient: some candidates may not fit or have drawable glyphs.

Record necessary exceptions in [data/allow.csv](../data/allow.csv), keyed by entry ID and check name, with a nonempty reason. Exceptions require review with the change. The validator defines which checks can be exempted.

## Self-tests and CI

For translation or script-injection changes, run `tools/validate.py` and `tools/selftest_inject.py`. Correct translations alone do not prove that injection preserved character keys.

The [workflow](../.github/workflows/validate.yml) runs data validation, Python undefined-name checks, game-path selection, display-table tests, and installation/restoration tests on Linux. Its Windows job compiles the native DLL and entry emitter with MSVC x64. From the repository root:

```powershell
.\native\build.ps1
py -3 tools/selftest_pe_loader.py
```

The PE test creates synthetic x64 images in a temporary directory without locating the game. Fixtures include the call site, imports, existing unwind records, and a layout with `.fontex`. The test uses the actual `emit_entry.exe` to check the jump, section permissions, repeated application, tamper rejection, and file protection during write failures. Synthetic PE files are not executed or uploaded.

To test a supported real executable locally, explicitly provide it; only temporary copies are patched:

```powershell
py -3 tools/selftest_pe_loader.py --exe "D:\Test\Backup\CielnosurgeDX.exe"
```

The following tests also need no game files and run in CI:

```powershell
py -3 tools/exe_sites.py --check
py -3 tools/selftest_exe_sites.py
py -3 tools/selftest_gbd_text.py
py -3 tools/selftest_text_table.py
py -3 tools/selftest_old_memos.py
py -3 tools/selftest_workscript.py
```

They cover authorized string copies, format specifiers and save delimiters, GBD boundaries, summary mappings, and memo compatibility. Memo tests include UTF-8 truncation, conflicting prefixes, and a truncated string that is also a complete memo.

Mapping tests do not prove that the full build preserves stored text. Locally, compare emitted write-memo parameters with the originals, check that summary source addresses remain Japanese, and read newly created patched-game saves in the original game. Original Japanese memos can also exceed the storage limit. Untranslated parameters do not remove the need for truncation and layout checks.

`selftest_workscript.py`, also in CI, covers CSV encoding/newlines, fixed member order/timestamps, conflicting sources, duplicate/damaged members, protection of an existing ZIP during failed replacement, and merge/injection/term readers. It does not establish rejection of missing expected members or interruption-safe `pack`/`unpack`. Full-build comparison must also cover character collection, glyph tables, and the atlas; a `--skip-font` run is insufficient.

## Checks requiring game files

After changing archive or injection logic, use a separate supported original-game copy. This test modifies extracted CSVs; do not point it at release build intermediates:

```powershell
$game = 'D:\Test\CielnosurgeDX'  # Supported original-game test copy
py -3 tools/export_text.py "$game\Res_x64" build/roundtrip-work
py -3 tools/workscript.py unpack build/roundtrip-work
py -3 tools/test_roundtrip.py "$game\Res_x64" build/roundtrip-work build/roundtrip-out
```

An unchanged rebuild must be byte-identical to the input. For full builds before/after the container optimization, compare CSV member sets/content, `PACK01.PAK`, the executable, replacement table, glyph table, and atlas. Whole-ZIP hashes also depend on metadata such as timestamps; `script.zip` fixes those values, but other ZIP outputs do not necessarily do so. Performance reports should identify the build, font inclusion, and first/subsequent runs. Build time is not total installation time.

After executable-string changes:

```powershell
py -3 tools/check_exe_text.py --archives
```

This checks locations, lengths, and data references. A match requires manual analysis to distinguish a label from a lookup key; see [executable strings](reverse-engineering/executable-strings.en.md).

To verify Dream World writes against an original archive and an exported translation table:

```powershell
py -3 tools/gbd_text.py verify "D:\Test\Backup\PACK01.PAK" build/work/dream_text.csv
```

This command modifies an in-memory copy only. Structural tests cannot replace local checks of character display, interaction sequences, and the game after uninstalling.
