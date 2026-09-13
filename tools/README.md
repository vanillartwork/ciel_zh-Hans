# 工具链

全部是 Python 3.10+，没有依赖的除了 `build_font.py`（需要 `numpy` 和 `Pillow`）。

## 你大概率会用到的

| 工具 | 干什么 |
|---|---|
| `hydrate.py` | 从**你自己的游戏**读出日文，和译文并排放进 `work/` |
| `dehydrate.py` | 把 `work/` 里的改动写回 `data/` |
| `validate.py` | 检查译文（**不需要游戏**） |
| `build.py` | 生成补丁 |
| `install.py` | 安装 / 还原 / 查看当前状态 |
| `preflight.py` | 装之前先看能不能装 |

## 流程内部

按 `build.py` 调用的顺序：

| 工具 | 干什么 |
|---|---|
| `gamepath.py` | 找游戏（优先读 Steam 注册表项）、找未打补丁的封包 |
| `runlog.py` | 把工具输出同时写入日志文件 |
| `env_strings.py` | 读写设置程序的界面文本 |
| `export_text.py` | 从封包提取文本 |
| `export_exe_text.py` | 从 exe 提取硬编码字符串 |
| `merge_repo.py` | 把 `data/` 的译文合并进提取结果 |
| `build_charset.py` | 决定字库要包含哪些字 |
| `build_font.py` | 重建图集与字形表，改 PE |
| `export_charset.py` | 从打好补丁的 exe 导出 `data/charset.txt` |
| `import_text.py` | 译文写回数据文件 |
| `patch_exe_strings.py` | 改 exe 里的字符串 |
| `build_patch.py` | 汇总成一份可安装的目录 |
| `repack_pak.py` | 重建封包 |

底层：

| 工具 | 干什么 |
|---|---|
| `gustpak.py` | PAK 读写 |
| `csvspan.py` | 保留字节区间的 CSV 扫描与替换 |
| `font_atlas.py` | 字形表结构 |
| `bc1.py` | BC1/DXT1 编解码 |

## 自检

| 工具 | 干什么 |
|---|---|
| `selftest_validate.py` | 证明 `validate.py` 真的拦得住坏数据（19 项） |
| `selftest_install.py` | 证明原地写入能被正确还原（10 项） |
| `test_roundtrip.py` | 证明解包再打包逐字节相同（**需要游戏**） |
| `check_exe_text.py` | 检查 exe 字符串译文（**需要游戏**） |

## 维护者用的

这些是把工作目录整理成仓库格式用的，日常贡献用不到：

| 工具 | 干什么 |
|---|---|
| `repo_export.py` | 工作目录 → `data/` 仓库格式 |
| `build_glossary.py` | 汇总生成术语表 |
| `release_notes.py` | 生成发布说明 |
| `normalize_cn.py` | 繁转简、日文新字体字形归一 |
| `fix_names.py` | 把已知错译统一改成标准译名 |
| `unify_dupes.py` | 同一句原文统一成同一译文 |
| `apply_official.py` / `official_glossary.py` | 导入官方译名 |
| `make_batches.py` / `merge_batches.py` | 分批下发与回收译文 |
| `sync_from.py` / `audit_clone.py` | 在两个工作目录之间同步与审计 |
| `workorder.py` | 按玩家接触顺序排出待翻译清单 |

## 约定

- 不需要游戏也必须能 `import` 的模块：`validate`、`repo_export`、
  `dehydrate`、`gamepath`、`gustpak`、`csvspan`、`font_atlas`、`merge_repo`。
  CI 会检查这一点——游戏路径要在**用到的时候**才解析，不要在模块顶层解析。
- 会写文件的工具都提供空跑（`--dry` 或默认不写），并在真正动手前
  打印将要做什么。
- 出错时把话说清楚：说明哪里出了问题、用户能怎么办，
  而不是抛一个栈回溯。
