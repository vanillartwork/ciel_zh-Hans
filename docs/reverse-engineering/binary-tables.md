# 二进制数据表（`.bin`）

`inc/**/*.bin`——道具、帮助、邮件、BGM 说明、服务器错误信息等。

## 布局

这些文件是**定长字段**的记录表。每个字符串字段占固定的字节数，
写入 UTF-8 后**用 `\0` 填满剩余空间**。

```
│ 字段 A (138 B)              │ 字段 B (40 B)      │ ...
│ UTF-8 内容 \0 \0 \0 ... \0  │ UTF-8 内容 \0 ...  │
```

因此：

- 译文的 UTF-8 字节数必须 **≤ 字段宽度 - 1**（留结束符）
- 一个汉字 3 字节，`max_bytes` 是 12 就只能写 4 个字
- 写超会截断后续字段，轻则错位，重则崩溃

`tools/import_text.py` 强制检查这一条，`validate.py` 也会。

## 表头

不少 `.bin` 的开头是一行 CSV 风格的表头，例如
`inc/hair/haircategory_data.bin`：

```
9,8,タグ,名前,インデックス,頭装飾装着可否ID,動きやすさ,ラクさ,かわいさ,…
TAG_HAIRCATEGORY_NORMAL,normal,0,2,80,80,50,30,10,…
```

开头的 `9,8` 是行数与列数，然后是列名，然后是数据行。

**列名是日文，但它们不是界面文本。** 真正的键是 `TAG_*` 这种
ASCII 标识符。列名更像是保留下来的文档。

不过本项目**没有翻译这些列名**，也没有翻译 exe 里同名的字符串——
无法确认引擎是否按列名查找，而这类标签的收益（几个参数名）
远小于猜错的代价。判断依据记在
[executable-strings.md](executable-strings.md)。

## 连续字段

道具说明这类长文本会被拆成多段，每段一个定长字段。
提取时能看到这样的注释：

```
field is a continuation chunk of a longer source string;
translate it as that part only
```

翻译时**只译这一段**，不要试图把整段话塞进一个字段。
`full_source_context` 列（工作副本里）给出完整上下文，供理解语境用。

## 不要翻译的表

| 文件 | 为什么 |
|---|---|
| `inc/globaldata/ngword_data.bin` | **屏蔽词表。翻译它会直接破坏过滤功能。** |
| `inc/sharl/sharl_name_data.bin` | 程序拼接宠物名用的词根，上限 4–6 字节 |
| `inc/sharl/sharl_npcrating_data.bin` | 同上 |

前一个是硬性的：这张表的作用是匹配玩家输入里的不良词汇，
换成中文之后它既拦不住日文，也拦不住中文（因为匹配逻辑不是为中文设计的）。

这些行在数据里的 `status` 是 `skip`，`note` 写明理由。
