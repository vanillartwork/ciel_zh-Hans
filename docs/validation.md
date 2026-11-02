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

翻译或脚本注入有改动时，先运行 `tools/validate.py` 和 `tools/selftest_inject.py`。后者检查实际写入的位置：译文校验通过，并不保证角色键没有被改动。

[校验工作流](../.github/workflows/validate.yml) 在 Linux 上检查翻译数据、未定义的 Python 名字、游戏目录选择、替换表以及安装与还原。Windows 任务使用 MSVC x64 编译显示层 DLL 和入口发射工具。可在仓库根目录复现：

```powershell
.\native\build.ps1
py -3 tools/selftest_pe_loader.py
```

第二条命令在临时目录生成 x64 PE，不查找游戏。样本带有调用点、导入表和已有的异常展开记录，也会测试已有 `.fontex` 的布局。测试用刚编译的 `emit_entry.exe` 打补丁，检查入口跳转、节权限、重复应用、篡改拒绝和写盘失败时的文件保护。合成文件不会执行，也不会上传。

若要核对受支持的实际版本，可在本机显式指定输入。测试只对临时副本打补丁：

```powershell
py -3 tools/selftest_pe_loader.py --exe "D:\Test\Backup\CielnosurgeDX.exe"
```

合成 PE 检查文件结构；角色显示、互动流程和卸载后的游戏状态仍须在本地验证。

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
