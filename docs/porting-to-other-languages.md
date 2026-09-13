# 移植到其他语言

工具链不认识中文。它只认识"一堆按 id 索引的译文"，
所以换成任何语言都能用。

## 怎么开始

```bash
cp -r data/zh-Hans data/<语言标签>
```

`jp`、`id`、`src`、`ctl` 这些列直接沿用，不用重新提取——
日文原文已经在仓库里了。

标签用 [BCP 47](https://www.rfc-editor.org/rfc/rfc5646)，
比如 `en`、`ko`、`zh-Hant`、`ru`。

然后清空 `zh` 列、把 `status` 设成 `todo`，开始译。

> 列名仍然叫 `zh`，是历史遗留。改名会让工具链和现有数据全都要动，
> 收益只是好看一点。把它读成"目标语言"就行。

## 哪些是语言无关的

**大部分。** 这些直接可用，不需要改：

| 组件 | 说明 |
|---|---|
| `gustpak.py` | 封包读写 |
| `csvspan.py` | 按字节区间替换 |
| `export_text.py` | 提取文本 |
| `export_exe_text.py` | 提取 exe 字符串 |
| `import_text.py` | 回注 |
| `repack_pak.py` | 重打包 |
| `patch_exe_strings.py` | 改 exe 字符串 |
| `hydrate.py` / `dehydrate.py` | 工作副本 |
| `merge_repo.py` | 合并译文 |
| `build.py` / `install.py` / `preflight.py` | 构建与安装 |
| `validate.py` 的大部分检查 | 控制码、字节数、id、状态、一致性 |

## 哪些要改

### 一定要改：字库

`build_charset.py` 现在的做法是"保留游戏用到的字形 + 加上整个 GB2312"。

换语言就要换字符集：

- **拉丁语言**（英、德、法…）：原字库**已经有**拉丁字母和常用变音符号，
  很可能**完全不用改字库**。这是最省事的情况。
- **韩语**：需要谚文。常用 2,350 字大致装得下；
  完整的 11,172 个音节**装不下**——图集尺寸不能改（见下）。
  实际做法是扫描游戏文本里实际出现的音节。
- **西里尔字母**：字数少，好办。
- **繁体中文**：Big5 常用字约 5,401 个，比 GB2312 还宽松。

**图集尺寸绝对不能改**（8192×4096）。引擎的 UV 除数不是从描述符
读的，改尺寸必然乱码。腾地方只能删掉用不到的字形——
`build_charset.py` 已经会统计"游戏实际画过哪些字"，
换语言时这个统计依然有效。

细节见 [reverse-engineering/font-and-glyph-table.md](reverse-engineering/font-and-glyph-table.md)。

### 一定要改：`data/charset.txt`

从你构建出来的字形表导出，`validate.py` 用它检查有没有字画不出来。

### 需要调整的检查

`validate.py` 里这几条是针对中文的：

| 检查 | 怎么改 |
|---|---|
| `KANA` 残留假名 | 对多数语言仍然有用（漏译检测），保留即可 |
| `MAX_DIALOGUE_LINE = 24` | 按目标语言的字宽重算。拉丁语言一行能放更多字符 |
| 术语 `forbidden` | 换成你自己的术语表 |

分行宽度最好按原作自己的排版统计来定，
`docs/style-guide.md` 里写了中文是怎么算的，方法可以照搬。

### 字节受限字段

`.bin` 字段的上限是**字节**，不是字符。

- 拉丁字母 1 字节 —— 比中日文宽松得多
- 西里尔、谚文 2–3 字节 —— 和中文差不多

拉丁语言在这里基本不会遇到麻烦。

## 目录约定

```
data/
  zh-Hans/       简体中文
  <你的语言>/
  glossary/
    glossary.csv         简体中文的
    glossary.<语言>.csv  你的
  charset.txt            简体中文用的
  charset.<语言>.txt     你的
  game-versions.csv      共用
  allow.csv              共用（按 id 豁免，与语言无关）
```

`validate.py` 和 `merge_repo.py` 都接受 `--data`，
多语言并存时按语言分别跑就行。

## 建议

**别从头写工具，直接 fork。** 踩过的坑都写在
[reverse-engineering/](reverse-engineering/) 里了，
尤其是图集尺寸、块对齐、散文件不生效这三条——
它们的表现都是"满屏乱码"，但原因完全不同，
不知道的话很难查。

做出来的成果如果愿意回馈，工具部分的改进欢迎提 PR。
译文各自维护即可，不必合并到这个仓库。
