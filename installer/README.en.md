# Windows installer

[中文](README.md) | English

The NSIS installer builds and installs the patch on the player's machine.

## Payload

```text
payload/
  python/       Embeddable CPython, NumPy, and Pillow
  tools/        Project tools
  data/         Translations and glossary
  native/build/ cielzh.dll and emit_entry.exe
```

The installer contains no game executable or resource archive. It reads original resources from the player's installed game.

## Build

Use Windows with NSIS and `makensis` on PATH. First run `.\native\build.ps1` from the repository root, then enter `installer/`:

```powershell
.\build-installer.ps1 -Version 0.9.8
```

The script downloads/configures the Python runtime and dependencies, copies tools and data, checks for accidentally included game resources, and invokes NSIS. Output goes to `../../dist/` relative to this directory—the repository parent's `dist/`—including the installer and `.sha256`.

## Installation

1. Locate the game; check required files and free space.
2. Extract tools/data and create the installation log.
3. Run `preflight.py` to check the game version.
4. Run `build.py` in phases.
5. Run `install.py --apply` to back up and install.
6. Remove temporary build files, register uninstall information, and place a copy of the uninstaller in the game's `Backup/` directory.

The free-space threshold is 1,200 MB. Version/build failures stop installation; write failures trigger a rollback attempt. The default log is `%LOCALAPPDATA%\CielNosurgeDX-zh-Hans\install.log`.

## Uninstallation and backups

Uninstallation runs `install.py --restore`, restoring three whole files and the font range in `PACK00_01.PAK` from `Backup/`. It also removes `cielzh.dll` and `cielzh-text.bin` if they still match their ownership records. `Backup/inplace.json` stores the range restoration plan independently of temporary build output.

Recovery errors report the backup location and cause. Steam's file-integrity verification can restore the original game if needed. Preserve the UTF-8 BOM in `NOTICE-INSTALLER.txt` so NSIS displays Chinese correctly.

`assets/patch.ico` is the installer icon. Installer artwork is original; do not include extracted game artwork.
