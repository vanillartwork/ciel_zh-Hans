# Building the patch

[中文](build.md) | English

## Requirements

- Python 3.10 or later.
- A legally owned, supported copy of Ciel nosurge DX.
- At least 1,200 MB free on the game drive, plus enough space for build output.
- MSVC x64 and the Windows SDK, provided by Visual Studio or Build Tools, for the default display-layer build. Players using the installer do not need these development tools.
- NumPy, Pillow, and a local Chinese font for rebuilding the atlas.

Run these commands from the repository root in PowerShell:

```powershell
py -3 -m pip install numpy pillow
./native/build.ps1
py -3 tools/preflight.py
py -3 tools/build.py --version 0.9.8
```

The build validates data, extracts source text, merges translations, rebuilds the font, writes text into copies, packages resources, and creates a manifest. It stops on failure and does not write to the game directory.

## Output and installation

```text
build/
  work/          Extracted text and merged translations
  font/          Font atlas and modified main executable
  stage/         text.zip, executables, and font resources
  dist/          Installable archives and in-place patch data
  manifest.json  Build version, file list, sizes, and hashes
```

Build output contains game data. Do not commit it to the repository.

`work/script.zip` holds extracted/merged script CSVs. `stage/text.zip` holds translated game resources ready for packaging. They serve different purposes. `--loose` controls the latter staging format; it does not unpack `script.zip`.

```powershell
py -3 tools/install.py            # Preview
py -3 tools/install.py --apply    # Back up and install
py -3 tools/install.py --verify   # Check installed files and recorded status
py -3 tools/install.py --restore  # Restore original files
```

For a custom build directory, add `--from <build-directory>` to the installation commands.

## Script intermediates and maintenance

To edit extracted script CSVs directly, work on a build copy:

```powershell
py -3 tools/workscript.py unpack build/work
# Edit build/work/script/*.csv or run tools that require loose files
py -3 tools/workscript.py pack build/work
```

The argument is the extraction directory, not the ZIP path. Successful `unpack` removes the ZIP; successful `pack` leaves only the ZIP. Readers reject both sources together instead of guessing which is newer. Re-extraction replaces intermediate data and does not preserve manual edits.

Conversion is not yet a recoverable transaction: `pack` removes the loose directory before writing the ZIP, and interrupted `unpack` can leave both sources. Keep an independent copy first, especially for edits not synchronized to repository data. Read-back verification before ZIP replacement does not make the entire conversion interruption-safe.

## Options

| Option | Purpose |
|---|---|
| `--game <directory>` | Select the game directory |
| `--out <directory>` | Select the build directory |
| `--skip-font` | Reuse the font atlas already in the output directory |
| `--skip-validate` | Skip data validation; for debugging only |
| `--no-repack` | Stop after staging; do not package installation archives |
| `--no-loader` | Diagnostic build without the display-layer entry, DLL, or replacement table |
| `--loose` | Stage text as individual files for inspection |
| `--phase <phase>` | Run `check`, `extract`, `font`, `inject`, or `repack` separately |

Phases share an output directory and must run in that order. The game and font can also be selected through environment variables:

```powershell
$env:CIEL_NOSURGE_DX = "D:\SteamLibrary\steamapps\common\CielnosurgeDX"
$env:CIEL_NOSURGE_FONT = "C:\Windows\Fonts\msyhbd.ttc"
```

## Troubleshooting

Source merging checks both `id` and the source hash. A mismatch rate above 2% stops the build. Many mismatches usually indicate a different game version or extraction from modified files. Tools prefer original backups; restore the game and rebuild if those backups are missing or wrong.

The default font is Microsoft YaHei Bold. Changing `CIEL_NOSURGE_FONT` requires recalibrating the rendering parameters in `build_font.py`. Keep the atlas at 8192×4096 and glyph allocations aligned to 4-pixel blocks; see the [font reference](reverse-engineering/font-and-glyph-table.en.md).

Loose staged files do not override packed resources. If text stays Japanese, check that packaging and installation completed. Nameplates, summaries, and memos also depend on the display layer; a `--no-loader` build omits their display translations. `install.py --verify` reports the loader and table status recorded by the last launch, not a live check of the current process.

## Building the installer

Install NSIS and make `makensis` available on PATH, then run:

```powershell
cd installer
.\build-installer.ps1 -Version 0.9.8
```

The installer and its `.sha256` file go to `dist/` in the repository's parent directory, not `build/dist/`. See the [installer documentation](../installer/README.en.md).
