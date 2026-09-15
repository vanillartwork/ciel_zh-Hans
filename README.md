**简体中文** · [English](README.en.md)

# 《Ciel nosurge DX》简体中文本地化项目

本项目为 **Ciel nosurge DX**（シェルノサージュ ～失われた星へ捧ぐ詩～ DX）提供非官方简体中文补丁，以及用于文本提取、校验、构建和安装补丁的配套工具链。

> **非官方爱好者项目。** 本项目与 GUST、光荣特库摩不存在任何隶属、合作或授权关系。
>
> **本项目不提供游戏本体。** 使用本补丁前，请确保你已合法购买并安装游戏。游戏购买前往[此处](https://store.steampowered.com/app/1477480)。
>
> **本汉化补丁完全免费**，仅供个人学习与交流使用。任何收费行为与本项目作者无关，请勿付款。如发现有人冒用本项目名义收费，欢迎向项目作者反馈。
>
> 有关版权、授权范围及第三方内容的完整说明，请参阅 [NOTICE.md](NOTICE.md)。

## 翻译进度

共计 **92,094** 行文本，其中 **91,744** 行已完成翻译，整体完成度为 **99.6%**。

| 内容 | 总行数 | 已翻译 |
|---|---:|---:|
| 剧情脚本（全 13 章、支线及日常内容） | 77,486 | 100% |
| 界面文本 | 8,238 | 100% |
| 道具文本 | 1,152 | 100% |
| 术语表与说话人名 | 1,089 | 99.9% |
| 全局文本（帮助、邮件、BGM 说明等） | 3,698 | 92.2% |
| 主程序中的硬编码文本 | 377 | 84.4% |
| 启动环境设置程序 | 54 | 100% |

尚未翻译的文本会继续显示为日文。项目字库保留了原有日文字形，因此不会因未翻译内容而显示为缺字方框。

目前保留未翻译状态的内容，大部分是出于技术或功能兼容性考虑而**有意保留**的：

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

[English version →](README.en.md)
