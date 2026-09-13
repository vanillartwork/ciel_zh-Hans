# 术语表

文件：[`data/glossary/glossary.csv`](../data/glossary/glossary.csv)
（1,070 条）

这不只是给人看的参考，**`validate.py` 会拿它来检查译文**。

## 列

| 列 | 含义 |
|---|---|
| `id` | 稳定标识 |
| `source` | 日文原词 |
| `zh` | 标准译名 —— **就用这个** |
| `kind` | 类型：`character` / `place` / `term` / `proper-noun` / `name` |
| `category` | 来源分类，见下 |
| `variants` | 可接受的其他写法（比如官方繁体版的写法） |
| `forbidden` | **禁止译法**，多个用 `\|` 分隔，CI 会拦 |
| `context` | 出现场合、出现次数 |
| `note` | 补充说明 |
| `authority` | 这个译名的依据 |
| `status` | `fixed` 不要改 / `agreed` 已定 / `retired` 已废弃 |

## `category`

| 值 | 含义 |
|---|---|
| `official` | 光荣特库摩台湾公开资料里用过的译名 |
| `speaker` | 说话人名牌 |
| `in-text-marker` | 游戏用 `{}` 标出的术语 |
| `project-decision` | 本项目自己定的 |

## `authority` 与 `status`

标着 `光荣特库摩台湾官方公开资料` 且 `status` 为 `fixed` 的，
**原则上不改**——哪怕有人觉得别的译法更传神。

理由很实际：这些名字在游戏里出现几百上千次，
改一个要动很多行，而且系列的其他作品、周边、讨论区都在用这些写法。
**统一比完美重要。**

## `forbidden` 是怎么来的

这一列里的大多数写法，**都是本项目历史上真的出现过的错译**。

翻译过程中很容易在一章中间漂移：前面写"卡诺"，
后面不知不觉写成了"卡侬"。这类错误人工很难发现，
因为每一处单独看都不像错。

所以每发现一次，就把错误写法记进 `forbidden`。CI 从此替你盯着。

例子：

| 正确 | 曾经写错成 |
|---|---|
| 卡诺 | 卡侬、卡农、加农 |
| 依恩 | 伊恩、伊翁、伊昂 |
| 榭鲁诺特伦 | 谢尔诺特伦、歇尔诺琴、颂歌特伦 |
| 杰诺姆 | 基因组 |
| 红宝石草 | 红宝石杯、红宝石玻璃 |
| 微类星体 | （曾整段漏译） |

## 想改一个译名

**先开 [术语讨论 Issue](../../issues/new?template=terminology.yml)，不要直接提 PR。**

改一个名字会牵连几十上百行，值得先讨论。
讨论时最有力的理由是：

- 官方用过的写法
- 作品内的设定依据
- 系列其他作品的既有译法
- 现在的译名会造成误解

## 想加一个新词

直接提 PR 加一行就行。

填 `source`、`zh`、`kind`、`category`（多半是 `project-decision`）、
`authority`（写"本项目"）、`status`（`agreed`）。

如果这个词已经被人译错过，顺手填上 `forbidden`。

## 重新生成

维护者可以从工作目录重建术语表：

```bash
py -3 tools/build_glossary.py <工作 export 目录> tools data
```

它会合并三个来源：官方译名表、游戏内 `{}` 术语、
说话人统计，并把 `fix_names.py` 里记录的历史错译导入 `forbidden`。
