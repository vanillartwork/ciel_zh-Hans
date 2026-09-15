# 贡献指南

提交内容前，请阅读 [NOTICE.md](NOTICE.md#贡献者授权) 中的贡献者授权条款。

## 翻译与校对

小范围纠错可通过 [翻译问题 Issue](../../issues/new?template=mistranslation.yml) 提交，请附截图、出现位置及修改建议。也可直接在 GitHub 编辑对应 CSV 并提交 Pull Request。

批量修改时，先克隆仓库，并准备 Python 3.10 或更高版本：

```bash
git clone https://github.com/vanillartwork/ciel_zh-Hans
cd ciel_zh-Hans
```

日文原文已保存在仓库中，翻译和数据校验无需安装游戏。

### 编辑要求

编辑 `data/zh-Hans/` 下的 CSV，仅修改 `zh`、`status`、`note` 列。保留 `jp`、`id` 及工具生成的元数据。

- 遵循[翻译规范](docs/style-guide.md)，统一使用[术语表](data/glossary/glossary.csv)中的译名。
- 保留控制码、成对花括号和占位符；换行与长度限制见翻译规范。
- 存疑的译文标为 `needs-review`，并在 `note` 中说明。
- 编辑器设置见 [CSV 编辑说明](docs/editing-csv.md)。

如需排序或批量处理，可使用工作副本：

```powershell
py -3 tools/hydrate.py
# 编辑 work/zh-Hans/ 下的文件
py -3 tools/dehydrate.py
```

`hydrate.py --game` 可额外比对本地游戏原文。`dehydrate.py` 仅按 `id` 同步译文、状态和备注，其余字段以仓库数据为准。

### 提交与校验

```powershell
py -3 tools/validate.py
```

修正全部错误后提交 Pull Request，说明修改范围及需要重点复核的内容。警告须检查，但不阻止自动校验通过。

确需豁免的检查应在 `data/allow.csv` 中记录条目、检查项和理由，并随修改一同评审。规则说明见[自动校验](docs/validation.md)。

## 术语

修改既有译名前，先提交[术语讨论 Issue](../../issues/new?template=terminology.yml)，说明官方资料、作品设定或系列既有译法等依据。新增词条可直接提交 Pull Request。

`authority` 记录译名来源，`fixed` 词条原则上保持不变；`forbidden` 中的译法不得使用。字段说明见[术语表文档](docs/glossary.md)。

## 代码

修改 `tools/` 或 `installer/` 时：

- 遵循现有代码风格，说明修改目的、验证命令及结果。
- 涉及封包、注入或字形表的改动，应核对文件结构及游戏内效果。
- 修改注入或打包逻辑后，运行 `py -3 tools/test_roundtrip.py`，确认无改动重建与原文件逐字节一致。
- 新增第三方依赖须说明必要性。
- 涉及安装流程的改动，应说明失败时的处理和恢复方式。

校验器与安装工具可分别通过以下命令自检：

```powershell
py -3 tools/selftest_validate.py
py -3 tools/selftest_install.py
```

## 不接受的内容

- 与 DRM、授权验证、防盗版或访问控制相关的分析、绕过代码。
- 机器翻译结果，或来自其他汉化组及未经授权来源的译文。
- 游戏可执行文件、封包、美术、音频等原始资源，以及超出既有对照数据范围的完整剧本。

## 评审

译文由至少一位熟悉作品的评审者核对语义、术语与表达；代码重点检查文件兼容性和失败后的恢复机制。自动校验通过后，仍须完成评审。

讨论须遵守[行为准则](CODE_OF_CONDUCT.md)。
