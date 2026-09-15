# CSV 编辑说明

翻译 CSV 使用 UTF-8，字段中可能含逗号、引号及多行文本。仅修改 `zh`、`status`、`note` 列，并保留原文字段的内容与换行。

## 表格编辑器

建议先生成工作副本，再用 LibreOffice Calc 或 Excel 编辑：

```powershell
py -3 tools/hydrate.py
```

编辑 `work/zh-Hans/` 中的文件时：

| 设置 | LibreOffice Calc | Excel |
|---|---|---|
| 导入方式 | 文本导入对话框 | 「数据 → 从文本/CSV」 |
| 编码 | Unicode (UTF-8) | UTF-8 |
| 字段分隔符 | 逗号 | 逗号 |
| 列类型 | 文本；启用「将带引号的字段作为文本」 | 全部设为文本 |
| 数字与日期识别 | 关闭「检测特殊数字」 | 禁用自动类型转换 |

保存时使用 CSV 格式，字段分隔符为 `,`，文本分隔符为 `"`。完成后同步回仓库：

```powershell
py -3 tools/dehydrate.py
py -3 tools/validate.py
```

该流程可避免将工作副本的 BOM、排序或技术字段改动带回仓库。

## 文本编辑器与网页

小范围修改可使用 VS Code、Notepad++，或 GitHub 网页编辑器。

直接编辑仓库 CSV 时：

- 保存为 UTF-8，不带 BOM。
- 记录间使用 LF，保留字段内部原有的 CRLF，勿全文件转换行尾。
- 含换行或逗号的字段须用双引号包围，内部双引号写为 `""`。
- 保持记录顺序，提交前检查差异。

编辑后运行 `py -3 tools/validate.py`。数据结构见[翻译数据格式](translation-data.md)。
