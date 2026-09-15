# 翻译数据格式

翻译数据保存在 `data/zh-Hans/`，按章节或模块划分 CSV。每条记录包含日文原文、译文及校验元数据。

## 字段

```csv
id,jp,zh,status,speaker,src,ctl,lines,note
inc/event/res/01/ma01_tt01.txt#2#12,<CLBU>ありがと、慰めてくれて……。,<CLBU>谢谢你，安慰了我……,translated,依恩,24248beb4c,<CLBU> br=0 nl=0,1,keep-tags <CLBU>
```

| 字段 | 含义 | 编辑要求 |
|---|---|---|
| `id` | 全项目唯一的条目标识 | 保留 |
| `jp` | 日文原文 | 保留 |
| `zh` | 译文 | 可修改 |
| `status` | 翻译状态 | 可修改 |
| `note` | 备注或疑问 | 可修改 |
| `src` | 原文 SHA-1 的前 10 个十六进制字符 | 工具生成 |
| `ctl` | 原文控制码、花括号及换行信息 | 工具生成 |
| `speaker`、`lines`、`max_bytes`、`max_chars`、`attr` 等 | 说话人、长度限制及其他结构信息 | 工具生成 |

日常翻译仅修改 `zh`、`status`、`note`。校验器会重新计算 `src` 与 `ctl`，检查它们是否仍与 `jp` 一致。

## 条目标识

脚本条目的 `id` 使用 `封包内路径#行#列`，例如：

```text
inc/event/res/01/ma01_tt01.txt#2#12
```

其他文本使用以下标识：

| 格式 | 来源 |
|---|---|
| `ui/...#偏移` | 界面 XML |
| `item:N` | 道具数据表 |
| `global:N` | 帮助、邮件等全局数据表 |
| `exe:摘要` | 可执行文件字符串 |
| `spk:N` / `term:N` | 说话人或术语 |

`id` 用于译文合并及校验豁免，不得重排编号或在不同文件间重复。游戏更新后须重新核对原文位置与摘要。

## 结构信息

`ctl` 示例：

```text
<CLBU> br=0 nl=1
```

表示原文含 `<CLBU>`、零对花括号和一个换行。结合 `jp` 与 `src`，校验器可在没有游戏文件的环境中检查控制码、结构和原文一致性。

## 翻译状态

| 值 | 含义 |
|---|---|
| `translated` | 已完成 |
| `draft` | 初稿，待校对 |
| `needs-review` | 存疑，需复核 |
| `todo` | 待翻译 |
| `skip` | 有意保留原文，须在 `note` 中说明原因 |

`skip` 用于屏蔽词表、程序内部标识等保留项，详见[未汉化内容](not-translated.md)。

## 编码与换行

- 使用 UTF-8，无 BOM。
- 记录分隔符使用 LF。
- 字段内部的 CRLF 属于原文内容，须保留。
- 含换行或逗号的字段用双引号包围，字段内的双引号写为 `""`。
- 保持现有记录顺序，避免无关的整文件差异。

`.gitattributes` 对翻译 CSV 设置了 `-text`，防止 Git 转换字段内部的换行。编辑器同样须避免全文件换行转换，见[CSV 编辑说明](editing-csv.md)。

## 工作副本

批量编辑可使用 Git 忽略的 `work/` 目录：

```powershell
py -3 tools/hydrate.py
py -3 tools/hydrate.py --game  # 可选：同时核对本地游戏原文
# 编辑 work/zh-Hans/ 中的文件
py -3 tools/dehydrate.py
py -3 tools/validate.py
```

前两条命令按需选择其一。`dehydrate.py` 按 `id` 同步 `zh`、`status`、`note`，原文及技术字段以 `data/` 为准。
