# 术语表

术语保存在 [data/glossary/glossary.csv](../data/glossary/glossary.csv)，供翻译、校对及自动校验使用。

## 字段

| 字段 | 含义 |
|---|---|
| `id` | 稳定标识 |
| `source` | 日文原词 |
| `zh` | 标准译名 |
| `kind` | `character`、`place`、`term`、`proper-noun` 或 `name` |
| `category` | 来源分类 |
| `variants` | 可接受的其他写法 |
| `forbidden` | 禁止译法，多项用 `\|` 分隔 |
| `context` | 出现场合与频次 |
| `note` | 补充说明 |
| `authority` | 译名依据 |
| `status` | `fixed`（固定）、`agreed`（已确认）或 `retired`（停用） |

`category` 常用值：

| 值 | 含义 |
|---|---|
| `official` | 官方公开资料中的译名 |
| `speaker` | 说话人名牌 |
| `in-text-marker` | 游戏用花括号标记的术语 |
| `project-decision` | 项目约定译名 |

## 使用原则

译文优先采用 `zh` 列。引用官方译名时，应在 `authority` 和备注中区分本作官方资料、系列其他作品资料及项目约定，避免混淆来源。

`fixed` 词条原则上保持不变。`forbidden` 收录需避免的错译或混用形式，校验器会报告命中项。该字段用于维护一致性，不代替对上下文的人工判断。

## 修改与新增

修改既有译名前，先提交[术语讨论 Issue](../../issues/new?template=terminology.yml)，附官方资料、作品设定、系列译法或现有译名造成歧义的依据。确认后同步修改相关译文。

新增词条可直接提交 Pull Request，填写原词、译名、类型、来源和状态。项目自定词条通常使用 `category=project-decision`、`status=agreed`；已知错译填入 `forbidden`。

## 重新生成

维护者可从提取目录汇总术语：

```powershell
py -3 tools/build_glossary.py <工作 export 目录> tools data
```

工具合并官方译名、花括号术语与说话人统计，并导入已记录的禁止译法。生成后须检查差异，确认来源与人工维护内容。
