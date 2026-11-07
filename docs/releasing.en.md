# Releasing

[中文](releasing.md) | English

## Versions

Patch versions such as `v0.9.8` and game versions such as `steam-2025-07` are separate. Use the patch version for the Release title and name supported game versions in the notes. Major versions indicate incompatible changes or required reinstallation; minor versions add substantial translation coverage; patch versions cover translation and program fixes.

## Before release

1. Update `CHANGELOG.md` with changes and limitations. Move the 0.9.8 preparation section under a dated version heading only when publishing.
2. Review [known issues](known-issues.md) (Chinese) and include player-facing limitations in the release notes.
3. If the font changed, run `py -3 tools/export_charset.py` to synchronize `data/charset.txt` with the final glyph table.
4. Run validation and self-tests, resolving all errors:

   ```powershell
   py -3 tools/validate.py
   py -3 tools/selftest_validate.py
   py -3 tools/selftest_install.py
   py -3 tools/selftest_install_flow.py
   py -3 tools/exe_sites.py --check
   py -3 tools/selftest_exe_sites.py
   py -3 tools/selftest_gbd_text.py
   py -3 tools/selftest_text_table.py
   py -3 tools/selftest_old_memos.py
   py -3 tools/selftest_workscript.py
   .\native\build.ps1
   py -3 tools/selftest_pe_loader.py
   ```

5. Build, install, and restore using one explicitly selected, supported clean game copy. Do not let automatic detection select the daily-play installation:

   ```powershell
   $game = 'D:\Test\CielnosurgeDX'
   py -3 tools/build.py --game $game --version 0.9.8
   py -3 tools/install.py --game $game --apply
   py -3 tools/install.py --game $game --verify
   ```

   Check nameplates, task menus, and touch interactions. For 0.9.8, also check door subtitles, long HISTORY recaps and paging, ruin names, and summaries/memos from new and old saves. Exit, run `py -3 tools/install.py --game $game --restore`, and compare file hashes with the pre-installation copy. Repeat installation/restoration using tools extracted from the final installer.

   Use separate test saves to check patched-game saves in the original game, Japanese and older Chinese saves in the patched game, uniquely recoverable and ambiguous truncated memos, count boundaries, and display-layer failure fallback. `--verify` reads status files from the last launch; it does not replace observing the current run.

## Package and publish

On Windows with NSIS installed:

```powershell
cd installer
.\build-installer.ps1 -Version 0.9.8
```

The installer and `.sha256` file go to `dist/` in the repository's parent directory. Confirm they belong to this build; an older file with the same name or an `-rc` build is not proof of a final release. At publication time, return to the repository root:

```bash
git tag -a v0.9.8 -m "Simplified Chinese patch v0.9.8"
git push origin v0.9.8
```

Publishing is manual: CI does not create or modify Releases, and the current validation workflow has no tag-push trigger. Create the GitHub Release, write the notes, and attach the locally generated installer and checksum. CI has no game files and cannot perform a complete patch build.

Start from the [release template](../.github/RELEASE_TEMPLATE.md) (Chinese). Describe visible changes, supported game versions, and limitations. `tools/release_notes.py` can help gather local statistics and hashes. See [supported versions](supported-versions.en.md) for adapting to game updates.
