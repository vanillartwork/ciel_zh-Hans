<a id="readme-top"></a>

**[简体中文](#readme-zh) · [English](#readme-en)**

<a id="readme-zh"></a>

# 《Ciel nosurge DX》简体中文本地化项目

本项目为 **Ciel nosurge DX**（シェルノサージュ ～失われた星へ捧ぐ詩～ DX）提供非官方简体中文补丁，以及用于文本提取、校验、构建和安装补丁的配套工具链。

> **非官方爱好者项目。** 本项目与 GUST、光荣特库摩不存在任何隶属、合作或授权关系。
>
> **本项目不提供游戏本体。** 使用本补丁前，请确保你已合法购买并安装游戏。游戏购买[前往此处](https://store.steampowered.com/app/1477480)
>
> **本汉化补丁完全免费**，仅供个人学习与交流使用。任何收费行为与本项目作者无关，请勿付款。如发现有人冒用本项目名义收费，欢迎向项目作者反馈。
>
> 有关版权、授权范围及第三方内容的完整说明，请参阅 [NOTICE.md](NOTICE.md)。

## 翻译进度

共计 **92,094** 行文本，其中 **90,126** 行已完成翻译，整体完成度为 **97.9%**。

| 内容 | 总行数 | 已翻译 |
|---|---:|---:|
| 剧情脚本（全 13 章、支线及日常内容） | 77,486 | 100% |
| 界面文本 | 8,238 | 100% |
| 道具文本 | 1,152 | 100% |
| 术语表与说话人名 | 1,089 | 99.8% |
| 全局文本（帮助、邮件、BGM 说明等） | 3,698 | 48.4% |
| 主程序中的硬编码文本 | 377 | 84.4% |
| 启动环境设置程序 | 54 | 100% |

尚未翻译的文本会继续显示为日文。项目字库保留了原有日文字形，因此不会因未翻译内容而显示为缺字方框。

目前保留未翻译状态的内容，大部分是出于技术或功能兼容性考虑而**有意保留**的：

- `sharl_npcrating_data.bin` 与 `sharl_name_data.bin`（共 1,618 行）包含程序用于动态拼接宠物名称的词根；相关字段仅允许 4～6 字节，不适合直接翻译。
- `ngword_data.bin`（290 行）为屏蔽词表。翻译这些条目会破坏原有过滤逻辑，因此不进行翻译。
- 可执行文件中仍保留日文的 59 条文本属于调试信息、动作计时标签或数据表字段名。它们不会直接显示给玩家，且引擎可能依赖这些名称进行查找。各条目保留原文的原因均记录在 [`data/zh-Hans/executable.csv`](data/zh-Hans/executable.csv) 的 `note` 列中。

图片文字与过场视频字幕的情况另见 [docs/not-translated.md](docs/not-translated.md)。

## 安装

### 一般玩家

1. 前往 [Releases](../../releases)，下载 `CielNosurgeDX-zh-Hans-<版本>-setup.exe`。
2. 运行安装程序，并按照界面提示完成安装。

安装程序会先检查游戏版本并备份原始文件，随后在本机使用你现有的游戏文件重新打包并生成补丁内容。整个过程需要约 **1 GB** 可用磁盘空间，通常需要数分钟完成。

> **为什么采用本地构建？**
> 这样发布的安装包无需包含原游戏文件，只需要携带本项目自行制作的译文和工具。这样既能减少对原游戏内容的再分发，也能显著减小下载体积。

当前支持的游戏版本见 [`data/game-versions.csv`](data/game-versions.csv)。如果检测到不受支持的游戏版本，安装程序会停止操作，不会修改无法确认兼容性的文件。

### 卸载与还原

可在 Windows 的「应用和功能」中卸载本补丁；安装过程中备份的原始文件会自动还原。卸载程序同时会在游戏目录的 `Backup` 文件夹中保留一份副本。

如有需要，也可以随时通过 Steam 的 **验证游戏文件完整性** 功能恢复原版游戏文件。

更详细的安装、卸载及故障排查说明见 [docs/install.md](docs/install.md)。

## 报告问题

请根据问题类型选择对应的 Issue 模板：

| 问题类型 | Issue 模板 |
|---|---|
| 译文错误、表达不自然或前后不一致 | [翻译问题](../../issues/new?template=mistranslation.yml) |
| 文字超出界面、重叠或显示为缺字方框 | [显示问题](../../issues/new?template=display.yml) |
| 安装失败、游戏崩溃或运行卡住 | [安装与运行问题](../../issues/new?template=bug.yml) |
| 术语译法存在疑问或希望讨论统一译名 | [术语讨论](../../issues/new?template=terminology.yml) |

报告翻译问题时，请尽量附上截图，并注明文本出现的位置或上下文，例如章节、事件或场景。这样可以更快定位到对应的文本条目。

## 参与翻译

参与翻译和校对**不要求具备编程经验**。

```bash
git clone https://github.com/vanillartwork/ciel_zh-Hans
cd ciel_zh-Hans
```

直接编辑 `data/zh-Hans/` 下相应的 CSV 文件，并修改 `zh` 列即可；对应的日文原文保留在相邻字段中，便于对照。

修改完成后运行：

```bash
py -3 tools/validate.py
```

确认校验通过后，即可提交 Pull Request。

如果需要在 Git 工作区之外进行排序、批量替换等处理，可以使用 `tools/hydrate.py` 将工作副本生成到 `work/`，处理完成后再通过 `tools/dehydrate.py` 将修改同步回仓库格式。使用 `--game` 参数时，还可以同时检查本地游戏版本是否与当前仓库数据匹配。

相关文档：

- 翻译规范：[docs/style-guide.md](docs/style-guide.md)
- 术语表：[data/glossary/glossary.csv](data/glossary/glossary.csv)（[使用说明](docs/glossary.md)）
- 完整贡献流程：[CONTRIBUTING.md](CONTRIBUTING.md)

## 翻译数据格式

翻译数据按文本条目保存，每行对应一个文本单元，并同时保留原文、译文及必要的校验信息：

```csv
id,jp,zh,status,speaker,src,ctl,lines,note
inc/event/res/01/ma01_tt01.txt#2#12,<CLBU>ありがと、慰めてくれて……。,<CLBU>谢谢你，安慰了我……,translated,依恩,24248beb4c,<CLBU> br=0 nl=0,1,keep-tags <CLBU>
```

主要字段：

- `id` —— 稳定且全项目唯一的文本标识符，格式为 `封包内路径#行#列`。
- `jp` / `zh` —— 日文原文与对应译文，用于直接对照编辑。
- `src` —— 根据原文计算得到的 SHA-1 摘要前 10 个十六进制字符，用于检测源文本变化。
- `ctl` —— 从原文提取的结构特征，例如控制码、花括号对数和换行数量，用于检测翻译过程中是否破坏技术结构。

`src` 与 `ctl` 均由 `jp` 自动推导，并会在校验过程中与当前原文重新比对。因此，CI **无需访问游戏文件**，也能够发现以下问题：

- 译文遗漏了控制码；
- 译文意外增加或删除了换行；
- 某条翻译数据来自不匹配的游戏版本；
- 其他可能导致「译文本身看似正常，但写回游戏后出现异常」的结构性问题。

> 仓库中包含用于翻译和校对的原文文本，但**不包含游戏本体**，也不提供游戏程序、美术、音频或视频资源。实际补丁由工具在用户本机基于用户自己的游戏文件生成。详见 [NOTICE.md](NOTICE.md)。

## 从源码构建

```bash
py -3 tools/validate.py                 # 校验翻译数据
py -3 tools/build.py --version 0.9.0    # 基于本地游戏文件生成补丁
py -3 tools/install.py --apply          # 安装补丁（安装前会备份原始文件）
```

完整构建流程及各阶段说明见 [docs/build.md](docs/build.md) 和 [docs/pipeline.md](docs/pipeline.md)。

## 移植到其他语言

文件格式处理逻辑与简体中文翻译数据彼此分离。工具链本身并不依赖中文内容，而是处理一组以稳定 `id` 索引的本地化文本，因此可以在相同框架下替换为其他目标语言。

有关创建其他语言版本的说明见 [docs/porting-to-other-languages.md](docs/porting-to-other-languages.md)。

通过逆向分析整理得到的技术资料，包括封包结构、脚本 CSV 格式、字节受限字段、字形表以及 PE 修改方式等，收录于 [docs/reverse-engineering/](docs/reverse-engineering/)。

## 授权

本仓库不同部分采用不同的授权条款：

| 内容 | 许可证 |
|---|---|
| `tools/`、`installer/` | [PolyForm Noncommercial 1.0.0](LICENSE) |
| `data/`、`docs/` 及各 `.md` 文件 | [CC BY-NC-SA 4.0](LICENSE-TRANSLATIONS) |

上述许可证仅适用于本项目及其贡献者有权授权的原创内容，不代表本项目对原游戏、其商标、程序、文本或其他第三方版权内容主张所有权，也不授予这些内容的任何额外权利。

除非另行获得明确授权，不得将受上述许可证约束的项目内容用于商业用途。

完整版权与授权声明见 [NOTICE.md](NOTICE.md)。

[↑ 返回语言选择](#readme-top)

---

<a id="readme-en"></a>

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

The project contains **92,094** text entries in total, of which **90,126** have been translated, for an overall completion rate of **97.9%**.

| Content | Total | Translated |
|---|---:|---:|
| Story scripts (all 13 chapters, side content, and daily events) | 77,486 | 100% |
| UI text | 8,238 | 100% |
| Item text | 1,152 | 100% |
| Glossary and speaker names | 1,089 | 99.8% |
| Global text (help, mail, BGM descriptions, etc.) | 3,698 | 48.4% |
| Hard-coded text in the main executable | 377 | 84.4% |
| Launch settings program | 54 | 100% |

Text that has not been translated will remain in Japanese. The project font retains the original Japanese glyphs, so untranslated content will not appear as missing-character boxes.

Most of the remaining untranslated entries are **intentionally** left unchanged for technical or compatibility reasons:

- `sharl_npcrating_data.bin` and `sharl_name_data.bin` (1,618 entries in total) contain word fragments that the game combines dynamically to generate pet names. The corresponding fields are limited to only 4–6 bytes, making direct translation impractical.
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

[↑ Back to language selection](#readme-top)
