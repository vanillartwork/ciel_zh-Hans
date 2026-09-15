# 自动校验

校验依据仓库中的原文和元数据运行，无需游戏文件。错误会导致校验失败，警告供人工复核；译文质量仍须评审。

```powershell
py -3 tools/validate.py                     # 全量校验
py -3 tools/validate.py --only script/06     # 按路径筛选
py -3 tools/validate.py --changed-only       # 仅检查变更文件
py -3 tools/validate.py --strict             # 额外报告实际换行数变化
py -3 tools/validate.py --format github      # GitHub Actions 输出格式
```

提交前应运行全量校验，局部校验不能覆盖未参与检查文件中的问题。

## 检查内容

| 类别 | 检查内容 |
|---|---|
| 数据结构 | 编码、BOM、记录分隔符、重复 `id`、状态与译文是否一致 |
| 原文一致性 | `src`、`ctl` 是否与 `jp` 匹配 |
| 控制码 | 非换行控制码是否一致，是否新增 `<CR>`，花括号是否配对且数量一致 |
| 长度 | 二进制字段字节预算、程序字符串预算、设置界面字符上限 |
| 显示与用语 | 字库缺字、残留假名、术语禁止译法 |
| 译文一致性 | 同一文件中相同原文的译法是否一致 |

上述问题通常为错误。以下情况报告警告：

- `<CR>` 数量减少。
- 剧情单行超过 24 个字符。
- 剧情中相同原文存在不同译法。
- 使用 `--strict` 时，实际换行数与原文不同。

非剧情文本的同源多译按错误处理。CSV 的 CRLF 检查仅针对记录分隔符，不针对字段内原文。

## 字库清单

[data/charset.txt](../data/charset.txt) 记录实际字形表支持的字符。每次重建字体后运行：

```powershell
py -3 tools/export_charset.py
```

清单须由最终可执行文件中的字形表导出。构建候选字符可能因字形缺失或图集容量未被收录，不能直接作为校验依据。

## 校验豁免

确需保留的特殊文本应在 [data/allow.csv](../data/allow.csv) 中记录：

```csv
id,check,reason
ui/ui/title/uil_title_confirm_user_name.xml#1155,kana,界面排版中的假名占位，属于界面结构而非可翻译文本
```

豁免按条目和检查项生效，理由不能为空，并须随改动接受评审。具体可豁免的项目以校验器实现为准。

## 工具自检与 CI

```powershell
py -3 tools/selftest_validate.py
py -3 tools/selftest_install.py
```

校验器自检覆盖有效数据和各类错误；安装自检覆盖写入、重复安装、还原及拒绝条件。

`.github/workflows/validate.yml` 在匹配的 Pull Request、推送或手动触发时执行：

- 检查仓库中是否混入游戏原始资源。
- 校验翻译数据并统计进度。
- 检查 Python 语法及无游戏环境下的模块导入。
- 运行校验器与安装工具自检。

## 需要游戏文件的验证

修改封包或注入逻辑后运行：

```powershell
py -3 tools/test_roundtrip.py
```

无改动重建应与原文件逐字节一致。

修改程序字符串后运行：

```powershell
py -3 tools/check_exe_text.py --archives
```

该工具检查字符串定位、长度及运行时数据中的完整字段匹配。命中项需人工判断是否为程序查找键，详见[可执行文件字符串](reverse-engineering/executable-strings.md)。
