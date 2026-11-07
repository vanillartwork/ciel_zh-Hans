# 翻译数据格式

中文 | [English](translation-data.en.md)

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
| `area.title:摘要`、`history.title:摘要` 等 | 梦世界数据表，见 `dream.csv` |
| `display:摘要` | 仅在显示时替换的文字，见 `display.csv` |
| `spk:N` / `term:N` | 说话人或术语 |

`id` 用于译文合并及校验豁免，不得重排编号或在不同文件间重复。游戏更新后须重新核对原文位置与摘要。

`display.csv` 只有 `id,jp,zh,status,note` 五列，不记录 EXE 偏移。构建时，已译条目进入显示层候选表；若原词本身也是现有中文译文，则跳过，以免把已经汉化的文字再替换一次。

## 0.9.8 新增数据

- `dream.csv`：按表族、字段和原文去重。`occurrences` 记录写回位置的数量，同一条译文可能出现在多个章节文件里。`max_bytes` 包含结束符，译文字节数须小于它；它不是字段的完整容量。
- `exe_sited.csv`：补充程序译文，和 `executable.csv` 共用 `exe:` 标识。写入地址、原文摘要与证据在 `data/exe-sites/<游戏版本>.csv` 中；仅新增译文不会自动授权其他同文地址。这里的 `max_bytes` 不含结束符。
- 程序格式串必须保留 `%s`、`%d` 等转换项的顺序和完整格式。地址清单中 `persisted` 项另检查换行、全角冒号和空格；当前只剩游玩时间格式仍原位翻译，其余摘要来源保留日文、仅供显示层使用。
- 新旧存档摘要的整句组合由 `old_saves.py` 生成，计数映射覆盖 0～999。当前备忘译文沿用脚本数据；`_memo_history.csv` 另保存已发布版本的历史译文，由 `tools/dev/gen_memo_history.py` 从标签生成，不作为新的待翻译表。`old_memos.py` 据此生成完整旧文和无歧义截断文本的显示映射，不改存档。

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

`skip` 表示有意保留的条目，详见[未汉化内容](not-translated.md)。目前屏蔽词表的 290 条记录和空白名牌仍标为 `todo`，但并非待补译内容；注入工具另有保留规则，不能仅按状态批量填入译文。

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
