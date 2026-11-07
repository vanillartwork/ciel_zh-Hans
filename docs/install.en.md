# Installation and restoration

[中文](install.md) | English

## Requirements

- Windows 10 or later, 64-bit.
- A legally purchased Steam copy of Ciel nosurge DX.
- At least 1,200 MB free on the game drive.
- The game must be closed before installation.

See [supported versions](supported-versions.en.md). The installer builds from local game resources, which normally takes several minutes.

## Install

1. Download `CielNosurgeDX-zh-Hans-<version>-setup.exe` from [Releases](https://github.com/vanillartwork/ciel_zh-Hans/releases).
2. Optionally verify the download against the matching `.sha256` file:

   ```powershell
   Get-FileHash ".\CielNosurgeDX-zh-Hans-<version>-setup.exe" -Algorithm SHA256
   ```

   Replace `<version>` with the actual version. Hashes from different builds are not interchangeable. If it does not match, download again before running it.

3. Run the installer, confirm the game directory, and follow the prompts.

Automatic detection uses Steam's installation information. If needed, select the directory containing `CielnosurgeDX.exe`. Tools and logs normally go under `%LOCALAPPDATA%\CielNosurgeDX-zh-Hans`.

The installer extracts tools/data, checks versions, builds, backs up originals, and installs. Version/build failures do not modify game files. A write failure triggers an attempt to roll back completed changes and records the error.

## Files and backups

| File | Changes | Backup |
|---|---|---|
| `CielnosurgeDX.exe` | Glyph table, permitted strings, display-layer entry | Whole file |
| `CielnosurgeDX_Env.exe` | Settings text | Whole file |
| `Res_x64/PACK01.PAK` | Scripts, UI, and tables including HISTORY | Whole file |
| `Res_x64/PACK00_01.PAK` | Font atlas | Approximately 16.8 MB modified range only |
| `cielzh.dll` (new) | Nameplates, tutorial headings, summaries, memos, etc. | Ownership record; no original file |
| `cielzh-text.bin` (new) | Locally generated display replacement table | Ownership record; no original file |

New files are upgraded or removed only when they still match the patch's ownership record. Unrelated same-name files are not taken over. `cielzh-loader.log` records loading results in the game directory and can be deleted. To diagnose text calls, close the game, create an empty `cielzh-trace.on` there, and restart. Tracing writes `cielzh-trace.txt` periodically and may cause stutters; remove the marker and restart after diagnosis.

Keep `Backup/` until uninstalling. Installation/restoration tools do not directly edit saves or Steam cloud saves. If an upgrade reports changed font-range locations, restore the old patch first, retaining `Backup/`, then install the new one.

## Uninstall

Use Windows Settings → Apps, or run `Backup/卸载简体中文补丁.exe`. Source-tool users can run from the repository root:

```powershell
py -3 tools/install.py --restore
```

Restoration uses original backups and the saved plan. If backups are missing or restoration fails, use Steam → Properties → Installed Files → Verify integrity of game files to retrieve originals.

## 0.9.8 and existing saves

- New memos and summary values for chapters, statuses, relationships, Sharl counts, and card counts remain Japanese in saves; the display layer shows Chinese. Play-time formatting is still translated in place, but the original load screen does not show that segment. This does not make entire saves byte-identical to original-game saves.
- Existing saves need no conversion or re-saving. Japanese content is translated on display. Recognized older Chinese memos map to current translations; truncated content is completed only when it identifies a unique result. Replacements do not write back to saves.
- Upgrading or uninstalling does not reverse Chinese previously stored by older builds; the original font may lack some of those glyphs. Keeping Japanese prevents extra truncation caused by longer Chinese translations, but original storage and text-box limits remain.
- Chinese at these locations requires `cielzh.dll` and its table. Without the display layer, newly stored Japanese remains Japanese. Unknown whole strings retain their stored content. Report screenshots and patch versions rather than editing saves manually.

## Troubleshooting

### Game not found or unsupported

Select the directory containing `CielnosurgeDX.exe`, usually `<Steam library>\steamapps\common\CielnosurgeDX`. Updates, other patches, or damage can cause version mismatches. Verify files through Steam and retry. If the mismatch remains, include logged SHA-256 values in an [installation/runtime issue](https://github.com/vanillartwork/ciel_zh-Hans/issues/new?template=bug.yml).

### Text remains Japanese

Confirm installation completed and check [untranslated content](not-translated.md) (Chinese). Source-tool users can run:

```powershell
py -3 tools/install.py --verify
```

If files are still original, inspect permission/file-in-use errors and retry with the game closed. For nameplates, summaries, or memos, the command also reads `cielzh-loader.log` and `cielzh-status.txt` from the last launch. It does not inspect the running process live.

### Saves and controls

Saving is manual. With default keys, press **I** in Ion's room, then **J** to switch to the bottom INFORMATION bar containing settings, SAVE, and LOAD. The title screen offers loading after a save exists. Saves are under `Documents\KoeiTecmo\CielnosurgeDX\SaveData\`; installing/uninstalling does not directly edit that directory.

For touch interactions with default keys, hold **J** for the hand toggle (controller X/□), then press **F** (left-stick click). Move the pointer with WASD. Change bindings in `CielnosurgeDX_Env.exe`; settings are stored in `Documents\KoeiTecmo\CielnosurgeDX\Setting.ini`.

### Crashes or display problems

Retest after uninstalling and report whether the problem persists. Include the patch version, location, reproduction steps, screenshots, and `install.log`. Use Steam verification if automatic restoration fails. For source builds, see [building](build.en.md).
