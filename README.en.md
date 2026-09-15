[简体中文](README.md) · English

# Ciel nosurge DX — Simplified Chinese Localization

This project provides an unofficial Simplified Chinese patch for *Ciel nosurge DX* (シェルノサージュ ～失われた星へ捧ぐ詩～ DX), with tools for text extraction, validation, building, and installation.

The patch is free of charge. The project is not affiliated with or authorized by GUST, KOEI TECMO, or their affiliates. You must legally own and install the game before using it. See [NOTICE.md](NOTICE.md) for copyright and licensing details.

## Translation Progress

Of 92,094 text entries, 91,744 are translated (99.62%).

| Content | Entries | Translated |
|---|---:|---:|
| Story scripts: all 13 chapters, side content, and daily events | 77,486 | 100% |
| UI text | 8,238 | 100% |
| Item text | 1,152 | 100% |
| Terms and speaker names | 1,089 | 99.9% |
| Global text: help, mail, Sharl names, etc. | 3,698 | 92.2% |
| Main executable strings | 377 | 84.4% |
| Settings program | 54 | 100% |

The remaining 350 entries are blocked words, internal identifiers, and a blank speaker label. They retain their original values. Image text and some video subtitles remain unfinished; see [untranslated content](docs/not-translated.md) (Chinese).

## Installation and Removal

1. Download `CielNosurgeDX-zh-Hans-<version>-setup.exe` from [Releases](../../releases).
2. Close the game, run the installer, and select the game directory when prompted.

The patch supports 64-bit Windows 10 or later. At least 1,200 MB of free space is required on the game drive. Installation usually takes a few minutes: the installer checks the game version, builds the patch locally, backs up the original files, and applies the patch.

See [supported versions](docs/supported-versions.md). The installer contains translation data and tools; game executables and assets are read from your local installation.

To remove the patch, use Windows **Settings → Apps**, or run `Backup/卸载简体中文补丁.exe` in the game directory. Removal restores the original files. If backups are missing, use Steam's **Verify integrity of game files** option.

See the [installation guide](docs/install.md) for detailed instructions and troubleshooting (Chinese).

## Reporting Issues

| Issue | Template |
|---|---|
| Translation errors, typos, or inconsistent wording | [Translation](../../issues/new?template=mistranslation.yml) |
| Text overflow, overlap, or missing glyphs | [Display](../../issues/new?template=display.yml) |
| Installation failure, crashes, or hangs | [Installation and runtime](../../issues/new?template=bug.yml) |
| Proposed terminology changes | [Terminology](../../issues/new?template=terminology.yml) |

Include the patch version, where the issue occurs, steps to reproduce it, and a screenshot. For installation issues, attach the log. See [known issues](docs/known-issues.md).

## Contributing

Translation and proofreading do not require programming experience. Edit the CSV files under `data/zh-Hans/`, changing only the `zh`, `status`, and `note` columns. Japanese source text is stored in `jp`.

Before submitting a Pull Request, run:

```powershell
py -3 tools/validate.py
```

Follow the [contribution guide](CONTRIBUTING.md), [translation style guide](docs/style-guide.md), and [glossary](data/glossary/glossary.csv).

## Building and Development

After setting up the build environment, run from the repository root:

```powershell
py -3 tools/build.py --version 0.9.0
py -3 tools/install.py --apply
```

See the [build guide](docs/build.md) for dependencies, options, and preflight checks. Further documentation:

- [Documentation index](docs/README.md)
- [Build pipeline](docs/pipeline.md) and [translation data format](docs/translation-data.md)
- [File format reference](docs/reverse-engineering/README.md)
- [Porting to other languages](docs/porting-to-other-languages.md)

## Licensing

| Content | License |
|---|---|
| Tool, script, and installer code | [PolyForm Noncommercial 1.0.0](LICENSE) |
| Translations, glossary, and documentation | [CC BY-NC-SA 4.0](LICENSE-TRANSLATIONS) |

These licenses cover only original contributions that their authors are entitled to license. They grant no rights to the game or other third-party material. Commercial use requires separate authorization. See [NOTICE.md](NOTICE.md) for the full notice.
