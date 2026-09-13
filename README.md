# 《シェルノサージュ DX》简体中文化计划

为 **Ciel nosurge DX（シェルノサージュ ～失われた星へ捧ぐ詩～ DX，Steam / Windows）**
制作的非官方简体中文补丁，以及配套的完整工具链。

> **非官方爱好者项目。** 与 GUST、光荣特库摩没有任何隶属或授权关系。
> 本项目不提供游戏本体，使用前请确保你已合法购买并安装游戏。
> 详见 [NOTICE.md](NOTICE.md)。

---

## 进度

**总计 92,040 行，已翻译 90,072 行（97.9%）。**

| 部分 | 行数 | 已翻译 |
|---|---:|---:|
| 剧情脚本（全 13 章 + 支线 + 日常） | 77,486 | 100% |
| 界面文本 | 8,238 | 100% |
| 道具文本 | 1,152 | 100% |
| 术语表与说话人名 | 1,089 | 99.9% |
| 全局文本（帮助、邮件、BGM 说明等） | 3,698 | 48.4% |
| 可执行文件内硬编码文本 | 377 | 84.4% |

未翻译的部分仍显示日文，不会出现方块字——字库同时保留了原有日文字形。

剩下没做的，大部分是**刻意不做**的：

- `sharl_npcrating_data.bin`、`sharl_name_data.bin`（共 1,618 行）是程序拼接
  宠物名用的词根，字节上限只有 4～6 字。
- `ngword_data.bin`（290 行）是屏蔽词表。**翻译它会直接破坏过滤功能**，
  所以永远不译。
- 可执行文件里保留日文的 59 条，是调试信息、动作计时标签和数据表字段名——
  玩家看不到，而且引擎可能按名字查找它们。每一条为什么保留，都写在
  [`data/zh-Hans/executable.csv`](data/zh-Hans/executable.csv) 的 `note` 列里。

---

## 安装

### 一般玩家

1. 到 [Releases](../../releases) 下载 `CielNosurgeDX-zh-Hans-<版本>-setup.exe`
2. 运行，按提示下一步

安装程序会核对游戏版本、备份原始文件，然后**在你的电脑上**用你自己的游戏文件
重新打包生成补丁。需要约 **6 GB 可用磁盘空间**和几分钟时间。

> 为什么要在本地打包？因为这样安装包里就**不必包含任何游戏文件**——
> 它只带上本项目自己的译文和工具。既尊重版权，下载也小得多。

**支持的游戏版本**见 [`data/game-versions.csv`](data/game-versions.csv)。
版本不符时安装程序会中止，而不会去改一个它不认识的文件。

### 卸载 / 还原

在"应用和功能"里卸载即可，原始文件会自动还原。
任何时候也可以用 Steam 的 **验证游戏文件完整性** 取回原版。

详见 [docs/install.md](docs/install.md)。

---

## 报告问题

| 情况 | 用这个模板 |
|---|---|
| 译文错误、别扭、不统一 | [翻译问题](../../issues/new?template=mistranslation.yml) |
| 文字超框、重叠、显示成方块 | [显示问题](../../issues/new?template=display.yml) |
| 安装失败、游戏崩溃、卡住 | [安装与运行问题](../../issues/new?template=bug.yml) |
| 某个术语该怎么译 | [术语讨论](../../issues/new?template=terminology.yml) |

报告译文问题时，**请附上截图**，并尽量写清出现的场景（第几章、什么事件）。
这能让人直接定位到具体那一行。

---

## 参与翻译

不需要会编程。

```bash
git clone https://github.com/vanillartwork/ciel_zh-Hans
cd ciel_zh-Hans
```

直接编辑 `data/zh-Hans/` 下的 CSV，填 `zh` 那一列——日文原文就在旁边。
改完跑一下：

```bash
py -3 tools/validate.py
```

确认没有错误后提交 Pull Request。

想在 git 之外折腾（排序、批量替换）的话，
`tools/hydrate.py` 会复制一份到 `work/`，`tools/dehydrate.py` 再收回来。
加上 `--game` 还能顺便核对你的游戏版本和仓库对不对得上。

- 翻译规范：[docs/style-guide.md](docs/style-guide.md)
- 术语表：[data/glossary/glossary.csv](data/glossary/glossary.csv)（[说明](docs/glossary.md)）
- 完整流程：[CONTRIBUTING.md](CONTRIBUTING.md)

---

## 翻译数据长什么样

一行一句，日文原文和译文并排：

```csv
id,jp,zh,status,speaker,src,ctl,lines,note
inc/event/res/01/ma01_tt01.txt#2#12,<CLBU>ありがと、慰めてくれて……。,<CLBU>谢谢你，安慰了我……,translated,依恩,24248beb4c,<CLBU> br=0 nl=0,1,keep-tags <CLBU>
```

- `id` —— 稳定标识，`封包内路径#行#列`，全项目唯一
- `jp` / `zh` —— 原文与译文，直接对照着改
- `src` —— 原文的 SHA-1 前 10 位
- `ctl` —— 原文的**技术形状**：有哪些控制码、几对花括号、几个换行

`src` 和 `ctl` 都由 `jp` 推出，校验时会和 `jp` 核对。
它们的用处是：CI **不需要游戏文件**就能发现译文弄丢了控制码、多加了换行，
或者某一行来自另一个版本的游戏——也就是那类
"译文本身没错，但改完游戏就坏了"的问题。

> 仓库里有原文，但**没有游戏**：没有程序、美术、音频、视频，
> 补丁是在你自己的机器上、用你自己的游戏文件生成的。
> 详见 [NOTICE.md](NOTICE.md)。

---

## 自己构建

```bash
py -3 tools/validate.py                 # 先查数据
py -3 tools/build.py --version 0.9.0    # 从你的游戏生成补丁
py -3 tools/install.py --apply          # 安装（会先备份）
```

完整流程与每一步在做什么：[docs/build.md](docs/build.md)、[docs/pipeline.md](docs/pipeline.md)。

---

## 给其他语言的社区

格式处理与简体中文是分开的。工具链不认识中文，只认识
"一堆按 id 索引的译文"——换成任何语言都能用。

见 [docs/porting-to-other-languages.md](docs/porting-to-other-languages.md)。

逆向得到的格式资料（封包结构、脚本 CSV、字节受限字段、字形表、PE 改造）
整理在 [docs/reverse-engineering/](docs/reverse-engineering/)。

---

## 授权

| 部分 | 授权 |
|---|---|
| `tools/`、`installer/` | [PolyForm Noncommercial 1.0.0](LICENSE) |
| `data/`、`docs/` 及各 `.md` | [CC BY-NC-SA 4.0](LICENSE-TRANSLATIONS) |

两者**仅覆盖本项目原创内容**，不对原游戏主张任何权利。
**禁止任何未经授权的商业使用。**

完整声明：[NOTICE.md](NOTICE.md)
