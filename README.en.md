**[简体中文](README.md)** · English

# Ciel nosurge DX — Simplified Chinese Localization Project

This project provides an unofficial Simplified Chinese localization patch for **Ciel nosurge DX**（シェルノサージュ ～失われた星へ捧ぐ詩～ DX）, together with the supporting toolchain used to extract, validate, build, and install the localized content.

> **Unofficial fan project.** This project is not affiliated with, endorsed by, or authorized by GUST or KOEI TECMO.
>
> **The game itself is not distributed with this project.** Please make sure that you legally own and have installed the game before using the patch. To buy game, go [here](https://store.steampowered.com/app/1477480).
>
> **This patch is entirely free of charge**, intended for personal study and exchange only. Nobody is authorized to sell it, and any charge made for it has nothing to do with this project — please do not pay. If you find someone charging for it in this project's name, please report it to the project authors.
>
> For the full copyright, licensing, and third-party content notice, see [NOTICE.md](NOTICE.md).

## Translation Progress

The project contains **92,094** text entries in total, of which **91,744** have been translated, for an overall completion rate of **99.6%**.

| Content | Total | Translated |
|---|---:|---:|
| Story scripts (all 13 chapters, side content, and daily events) | 77,486 | 100% |
| UI text | 8,238 | 100% |
| Item text | 1,152 | 100% |
| Glossary and speaker names | 1,089 | 99.9% |
| Global text (help, mail, BGM descriptions, etc.) | 3,698 | 92.2% |
| Hard-coded text in the main executable | 377 | 84.4% |
| Launch settings program | 54 | 100% |

Text that has not been translated will remain in Japanese. The project font retains the original Japanese glyphs, so untranslated content will not appear as missing-character boxes.

Most of the remaining untranslated entries are **intentionally** left unchanged for technical or compatibility reasons:

- `ngword_data.bin` (290 entries) is a blocked-word list. Translating these entries would break the original filtering logic, so they are intentionally left untouched.
- The 59 Japanese strings still present in the executable are debugging messages, animation timing labels, or data-table field names. They are not shown directly to players, and the engine may rely on their original names for lookup. The reason for retaining each entry is documented in the `note` column of [`data/zh-Hans/executable.csv`](data/zh-Hans/executable.csv).

Text baked into images, and cutscene subtitles, are covered separately in [docs/not-translated.md](docs/not-translated.md).

## Installation

### For Players

1. Go to [Releases](../../releases) and download `CielNosurgeDX-zh-Hans-<version>-setup.exe`.
2. Run the installer and follow the on-screen instructions.

The installer first verifies the game version and backs up the original files. It then rebuilds the required patch content locally from the game files already installed on your computer. The process requires approximately **1 GB** of free disk space and normally takes a few minutes.

> **Why build the patch locally?**
> This allows the distributed installer to avoid including any original game files. It only contains translations and tools created by this project, reducing unnecessary redistribution of game content while also keeping the download substantially smaller.

Supported game versions are listed in [`data/game-versions.csv`](data/game-versions.csv). If an unsupported version is detected, the installer stops without modifying files whose compatibility cannot be verified.

### Uninstalling and Restoring the Original Files

The patch can be removed from Windows **Apps & features**. Original files backed up during installation will be restored automatically. A copy of the uninstaller is also kept in the game's `Backup` folder.

You can also restore the original game files at any time by using Steam's **Verify integrity of game files** feature.

For detailed installation, removal, and troubleshooting instructions, see [docs/install.md](docs/install.md).

## Reporting Issues

Please use the Issue template that best matches the problem:

| Issue | Template |
|---|---|
| Incorrect, awkward, or inconsistent translation | [Translation issue](../../issues/new?template=mistranslation.yml) |
| Text overflow, overlap, or missing-character boxes | [Display issue](../../issues/new?template=display.yml) |
| Installation failure, crash, or hang | [Installation / runtime issue](../../issues/new?template=bug.yml) |
| Terminology question or proposed standardized translation | [Terminology discussion](../../issues/new?template=terminology.yml) |

When reporting a translation issue, please include a screenshot whenever possible and describe where the text appears, such as the chapter, event, or scene. This makes it much easier to locate the exact source entry.

## Contributing Translations

**No programming experience is required** to help with translation or proofreading.

```bash
git clone https://github.com/vanillartwork/ciel_zh-Hans
cd ciel_zh-Hans
```

Edit the relevant CSV files under `data/zh-Hans/` and update the `zh` column. The corresponding Japanese source text is stored alongside the translation for direct reference.

After making changes, run:

```bash
py -3 tools/validate.py
```

Once validation completes without errors, submit a Pull Request.

If you need to perform operations such as sorting or bulk replacement outside the Git working tree, `tools/hydrate.py` can generate a working copy under `work/`, and `tools/dehydrate.py` can convert the edited data back into the repository format. When used with `--game`, the tools can also verify that your local game version matches the data expected by the repository.

Related documentation:

- Translation style guide: [docs/style-guide.md](docs/style-guide.md)
- Glossary: [data/glossary/glossary.csv](data/glossary/glossary.csv) ([documentation](docs/glossary.md))
- Full contribution workflow: [CONTRIBUTING.md](CONTRIBUTING.md)

## Translation Data Format

Translation data is stored as individual text entries. Each row contains the source text, translation, and metadata required for validation:

```csv
id,jp,zh,status,speaker,src,ctl,lines,note
inc/event/res/01/ma01_tt01.txt#2#12,<CLBU>ありがと、慰めてくれて……。,<CLBU>谢谢你，安慰了我……,translated,依恩,24248beb4c,<CLBU> br=0 nl=0,1,keep-tags <CLBU>
```

Key fields:

- `id` — A stable, project-wide unique text identifier in the form `path-inside-archive#line#column`.
- `jp` / `zh` — The Japanese source text and its corresponding translation, stored side by side for direct comparison.
- `src` — The first 10 hexadecimal characters of the SHA-1 digest derived from the source text, used to detect source-text changes.
- `ctl` — Structural characteristics extracted from the source text, such as control codes, brace-pair counts, and newline counts. These are used to detect structural damage introduced during translation.

Both `src` and `ctl` are derived automatically from `jp` and are recomputed during validation. This allows CI to detect problems **without access to the game files**, including:

- missing control codes;
- accidentally added or removed line breaks;
- translation entries originating from a different game version; and
- other structural changes that may cause the game to malfunction even when the visible translation itself appears correct.

> The repository contains source text needed for translation and proofreading, but **does not contain the game itself**, nor does it distribute the game's executable, artwork, audio, or video assets. The actual patch is generated locally from the user's own installed game files. See [NOTICE.md](NOTICE.md) for details.

## Building from Source

```bash
py -3 tools/validate.py                 # Validate translation data
py -3 tools/build.py --version 0.9.0    # Build the patch from local game files
py -3 tools/install.py --apply          # Install the patch (original files are backed up first)
```

For the complete build process and an explanation of each stage, see [docs/build.md](docs/build.md) and [docs/pipeline.md](docs/pipeline.md).

## Porting to Other Languages

Game-format handling is separated from the Simplified Chinese localization data. The toolchain itself does not depend on Chinese text; it operates on localized strings indexed by stable `id` values, so the same workflow can be adapted to other target languages.

See [docs/porting-to-other-languages.md](docs/porting-to-other-languages.md) for guidance on creating another language version.

Technical documentation produced from the reverse-engineering work — including archive structures, script CSV formats, byte-limited fields, glyph tables, and PE modifications — is collected under [docs/reverse-engineering/](docs/reverse-engineering/).

## Licensing

Different parts of this repository are distributed under different licenses:

| Content | License |
|---|---|
| `tools/`, `installer/` | [PolyForm Noncommercial 1.0.0](LICENSE) |
| `data/`, `docs/`, and `.md` files | [CC BY-NC-SA 4.0](LICENSE-TRANSLATIONS) |

These licenses apply only to original material that this project and its contributors are entitled to license. They do not assert ownership of, or grant additional rights to, the original game, its trademarks, executable code, text, or other third-party copyrighted material.

Unless separately authorized, commercial use of project material covered by the licenses above is not permitted.

For the complete copyright and licensing notice, see [NOTICE.md](NOTICE.md).

[简体中文版 →](README.md)
