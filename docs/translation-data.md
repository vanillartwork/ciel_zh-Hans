# 翻译数据的格式

## 一行长什么样

`data/zh-Hans/script/01.csv`：

```csv
id,jp,zh,status,speaker,src,ctl,lines,note
inc/event/res/01/ma01_tt01.txt#2#12,<CLBU>ありがと、慰めてくれて……。,<CLBU>谢谢你，安慰了我……,translated,依恩,24248beb4c,<CLBU> br=0 nl=0,1,keep-tags <CLBU>
```

日文原文和译文并排，改哪一句一目了然。

| 列 | 是什么 | 能改吗 |
|---|---|---|
| `id` | 稳定标识，`封包内路径#行#列` | ❌ |
| `jp` | 游戏里的日文原文 | ❌ |
| `zh` | 译文 | ✅ |
| `status` | 翻译状态 | ✅ |
| `note` | 备注、疑问 | ✅ |
| `src` | `jp` 的 SHA-1 前 10 位 | ❌ 工具生成 |
| `ctl` | `jp` 的技术形状 | ❌ 工具生成 |
| 其余 | `speaker` `lines` `max_bytes` `attr` 等 | ❌ 工具生成 |

**只改 `zh`、`status`、`note`。** 其余列一改，校验就会报错——这是故意的：
`src` 和 `ctl` 都由 `jp` 推出，三者对不上就说明有人动了不该动的东西，
或者这一行来自另一个版本的游戏。

## `ctl` 这一列

```
<CLBU> br=0 nl=1
```

意思是：原文有一个 `<CLBU>` 标记、0 对花括号、1 个换行。

它看上去是冗余的（从 `jp` 现算就有），但存下来有两个用处：

1. **校验时和 `jp` 对账。** 如果谁手滑改了 `jp`，`ctl` 和 `src` 会立刻不一致。
2. **换语言时不用重新推导。** 其他语言的分支照抄这一列即可，
   不必自己实现一遍"原文有哪些控制码"。

CI 靠它拦住那类"译文本身没错，但改完游戏就坏了"的问题：
丢了颜色标记、多加了换行、花括号不配对。
这些检查**不需要游戏文件**，所以在 GitHub 的服务器上就能跑完。

## `id` 为什么长这样

```
inc/event/res/01/ma01_tt01.txt#2#12
└──────── 封包内路径 ────────┘ └行┘└列┘
```

- **稳定**：只要游戏不更新，这一行永远是这个 id
- **唯一**：全项目不重复（`validate.py` 会检查）
- **可读**：一眼看出是第 1 章哪个事件

不是从脚本里来的行，用别的前缀，同样保证唯一：

| 前缀 | 来源 |
|---|---|
| `ui/...#偏移` | 界面 XML |
| `item:N` | 道具相关的 `.bin` 字段 |
| `global:N` | 帮助、邮件等 `.bin` 字段 |
| `exe:xxxxxxxx` | 可执行文件里的字符串，id 是原文哈希 |
| `spk:N` / `term:N` | 说话人、术语 |

> `item:` 和 `global:` 一开始都叫 `bin:`，结果两边的编号撞了 1,152 个。
> 因为 `data/allow.csv` 之类的地方只用 id 定位一行，重复是不行的，
> 所以加了前缀，`validate.py` 也加了一条跨文件唯一性检查。

## `status`

| 值 | 含义 |
|---|---|
| `translated` | 译好了 |
| `draft` | 初稿，还没校对 |
| `needs-review` | 译者自己拿不准，请人看看 |
| `todo` | 还没译 |
| `skip` | **刻意不译**，理由写在 `note` 里 |

`skip` 很重要。比如屏蔽词表翻译了会破坏过滤功能，
exe 里有些字符串是引擎按名字查找的标签。
这些不是"还没做"，是"不该做"——不把区别记下来，
下一个人会好心地把它们补上。

哪些属于这一类，见 [not-translated.md](not-translated.md)。

## 关于换行

游戏的脚本文件在**字段内部**用 CRLF 换行（一个对话框里的折行），
这段字节必须原样保留。

所以：

- 仓库文件的**记录分隔符**是 LF
- 但**字段内部**可能含 CRLF，那是原文的一部分
- `.gitattributes` 对这些文件设了 `-text`，**禁止 git 转换行尾**——
  否则 git 会把字段内的 CRLF 一起改掉，悄悄改变原文，
  让所有 `src` 哈希失效
- `validate.py` 只在记录分隔符处检查 CRLF，不会误伤字段内的

克隆仓库前建议：

```bash
git config --global core.autocrlf false
```

## diff 长什么样

```diff
-inc/event/res/06/day06_02.txt#14#12,...,"总之，先这样吧。
+inc/event/res/06/day06_02.txt#14#12,...,"总之先这样吧。
```

一行一句。这也是为什么：

- 文件是 UTF-8 不带 BOM
- 行的顺序固定（按 id 排，不重排）
- 一个文件对应游戏里一章或一个模块，不会有单个巨大文件

## 工作副本（可选）

不想直接在 git 工作区里编辑的话：

```bash
py -3 tools/hydrate.py            # data/ -> work/，git 忽略 work/
py -3 tools/hydrate.py --game     # 顺便核对你的游戏版本
py -3 tools/dehydrate.py          # work/ -> data/
```

`dehydrate.py` **只带回 `zh`、`status`、`note`**，
id、原文和技术字段一律以 `data/` 为准。

## 加一种新语言

复制 `data/zh-Hans/` 成 `data/<语言标签>/`，清空 `zh` 列，
把 `status` 改成 `todo`，开始译。`jp` 列直接沿用。

见 [porting-to-other-languages.md](porting-to-other-languages.md)。
