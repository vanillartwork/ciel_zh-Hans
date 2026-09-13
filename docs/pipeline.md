# 从游戏文件到补丁：完整流程

一句话版本：

```
你的游戏  ──解包──►  提取文本  ──合并译文──►  回注  ──重打包──►  补丁
                                    ▲
                             仓库里的 data/
```

仓库里有译文和对照用的原文；**游戏本体和成品补丁都不进仓库**，
只在你自己的机器上存在。

---

## 各个阶段

### 0. 找到游戏 · `gamepath.py`

按这个顺序找：命令行参数 → `CIEL_NOSURGE_DX` 环境变量 →
Steam 注册表 + `libraryfolders.vdf` → 几个常见路径。

找不到就报错说清楚去哪找，**不猜**。

还有一个 `source_pak()`：读文本时优先用 `Backup/` 里的原始封包。
装过补丁的游戏目录里，封包已经是中文的了——拿它当"原文"会把
译文和译文自己比对。这个坑踩过一次，所以专门写了函数。

### 1. 解包 · `gustpak.py`

Gust PAK（KTGL 引擎）：

```
头    u32 version(0x20000) | u32 文件数 | u32 头长(16) | u32 flags
条目  char name[128] | u32 size | u8 key[20] | u64 offset | u32 flags   共 168 字节
数据  从 16 + 文件数*168 开始，每个文件用自己的 20 字节 key 循环异或
```

**文件名本身也是加密的**，用同一个 key。key 全零表示明文。

格式细节见 [reverse-engineering/pak-format.md](reverse-engineering/pak-format.md)。

### 2. 提取文本 · `export_text.py` + `export_exe_text.py`

四类文本，来源不同：

| 类别 | 在哪 | 形态 |
|---|---|---|
| 剧情脚本 | `inc/event/res/**/*.txt` | UTF-8 BOM 的 CSV，第 12 列是对白 |
| 界面 | `ui/**/*.xml` | XML 属性 |
| 道具、帮助、邮件等 | `inc/**/*.bin` | 定长二进制字段 |
| 系统提示 | `CielnosurgeDX.exe` | 编译进 `.rdata` 的字符串 |

脚本 CSV 里**不是每一列都能翻译**：第 9、15、18、20、21、22 列是
开发者注释，翻了会出问题。哪一列是什么，见
[reverse-engineering/event-script.md](reverse-engineering/event-script.md)。

### 3. 合并译文 · `merge_repo.py`

把 `data/zh-Hans/**` 的 `zh` 按 `id` 填进上一步的结果。

**每一行都先核对 `src` 哈希**：拿你的游戏里那句原文算出哈希，
和仓库记录的比。对不上就留空不填——那说明这一行的原文
和译者当时看到的不是同一句。

仓库里虽然也存了 `jp`，但这里**以你的游戏为准**：
注入要写回的是你的文件，能不能对上得由它说了算。

如果对不上的比例超过 2%，直接中止，并提示多半是游戏目录已经打过补丁。

### 4. 建字库 · `build_charset.py` + `build_font.py`

原字库有 6,718 个汉字，但这个游戏实际只画其中 2,243 个。
把用不到的扔掉，腾出的位置刚好塞得下整个 GB2312。

**图集尺寸绝对不能改。** 引擎的 UV 除数不是从字体描述符里读的，
把图集放大到 8192×8192 并把描述符改成 4096×4096，结果是每个字
都按两倍高度采样——满屏乱码。这个也踩过。

新字形表装不下原来的位置，所以新建一个 `.fontex` 节，
把唯一一处引用它的 `lea` 指令重新指向那里。

细节见 [reverse-engineering/font-and-glyph-table.md](reverse-engineering/font-and-glyph-table.md)。

### 5. 回注 · `import_text.py` + `csvspan.py`

这里有个关键决定：**不重新序列化 CSV，而是按字节区间替换。**

原因是 Python 的 `csv` 模块重新写出来的文件和原文件不完全一样——
原文件里有些字段带着多余的引号，重新序列化会把它们去掉。
2,958 个脚本文件里有 19 个会因此产生差异。

所以 `csvspan.py` 扫描出每个字段的**精确字节范围**，注入时只替换
那一段，其余字节原样保留。空改动注入后文件逐字节相同。

`.bin` 字段是定长的：写入译文后用 0 填满剩余空间。
译文的 UTF-8 字节数必须 ≤ `max_bytes - 1`（留一个结束符）。

### 6. 改可执行文件 · `patch_exe_strings.py`

硬编码的日文字符串**原地覆盖**，因为散落各处的 RIP 相对 `lea`
指令都指向它们，搬走就得逐个重新定位。

代价是**译文不能比原文长**，多出来的字节用 0 填充。

匹配时要求**前后都是 `\0`**，也就是必须是完整字符串。
这样 `食器洗い` 就不会误伤 `食器洗い。空の食べ物を流しへ入れる`。

`check_exe_text.py --archives` 会额外检查一件事：这个字符串是不是
也作为**完整字段**出现在游戏运行时读取的 `.bin` / `.xml` 里。
如果是，引擎可能按名字查它，改了就会失配。
详见 [reverse-engineering/executable-strings.md](reverse-engineering/executable-strings.md)。

### 7. 重打包 · `repack_pak.py`

```
PACK01.PAK      ← inc/ 和 ui/ 下的文本
PACK00_01.PAK   ← res_x64/ 下的字体图集
```

重建时**每个条目保留原来的 key**，没改动的条目字节不变。
`test_roundtrip.py` 验证的就是这件事：空改动重建出的 33,781,160 字节
封包和原始封包完全相同。

### 8. 安装 · `install.py`

先核对版本，再备份，再用临时文件 + 校验 + 原子改名的方式替换。
任一步失败就把已经替换的文件恢复回去。

---

## 一条命令跑完

```bash
py -3 tools/build.py --version 0.9.0
```

它按顺序做 1–7，任何一步失败就停下，并且**在第 7 步之前完全不碰游戏目录**。

```bash
py -3 tools/install.py --apply
```

---

## 各文件职责

| 文件 | 职责 |
|---|---|
| `gamepath.py` | 找游戏、找未打补丁的封包 |
| `gustpak.py` | PAK 读写 |
| `csvspan.py` | 保留字节区间的 CSV 扫描/替换 |
| `export_text.py` | 从封包提取文本 |
| `export_exe_text.py` | 从 exe 提取硬编码字符串 |
| `merge_repo.py` | 仓库译文 → 提取结果 |
| `repo_export.py` | 提取结果 → 仓库格式（维护者用） |
| `hydrate.py` / `dehydrate.py` | 译者的双语工作副本 |
| `build_charset.py` | 决定字库要包含哪些字 |
| `build_font.py` | 重建图集与字形表，改 PE |
| `import_text.py` | 译文写回数据文件 |
| `patch_exe_strings.py` | 改 exe 里的字符串 |
| `repack_pak.py` | 重建封包 |
| `build.py` | 串起整条流程 |
| `install.py` / `preflight.py` | 安装、还原、装前检查 |
| `validate.py` | 数据校验（不需要游戏） |
| `selftest_validate.py` | 验证校验器本身有效 |
| `test_roundtrip.py` | 验证解包/打包无损 |
