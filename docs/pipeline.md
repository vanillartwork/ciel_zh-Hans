# 构建流程

工具链从本地游戏提取原文，将仓库译文写回副本，再生成安装数据：

```text
本地游戏 → 提取原文 → 按 id 和 src 合并译文 → 写回文本 → 打包 → 安装
                         ↑                     ↑
                    data/zh-Hans/         字体图集与字形表
```

`build.py` 负责构建，`install.py` 负责备份和写入游戏目录。

## 1. 定位游戏与原始文件

`gamepath.py` 按命令行参数、`CIEL_NOSURGE_DX`、Steam 注册信息及常见目录查找游戏。

`source_file()` 和 `source_pak()` 优先读取 `Backup/` 中的原始文件，避免将已安装补丁的中文内容作为日文原文。

## 2. 提取原文

| 来源 | 工具 | 内容 |
|---|---|---|
| `inc/event/res/**/*.txt` | `export_text.py` | 剧情对白与说话人名 |
| `ui/**/*.xml` | `export_text.py` | 界面文本 |
| `inc/**/*.bin` | `export_text.py` | 道具、帮助、邮件等定长字段 |
| `CielnosurgeDX.exe` | `export_exe_text.py` | 程序内 UTF-8 字符串 |
| `CielnosurgeDX_Env.exe` | `env_strings.py` | Win32 资源中的设置界面文本 |

脚本仅提取可翻译字段，指令与开发者注释保持原样。格式见[剧情脚本](reverse-engineering/event-script.md)与[二进制数据表](reverse-engineering/binary-tables.md)。

## 3. 合并译文

`merge_repo.py` 按 `id` 匹配条目，并将本地原文摘要与仓库中的 `src` 比较。匹配后写入 `zh`；不匹配的条目保留原文，不匹配比例超过 2% 时中止。

字段说明见[翻译数据格式](translation-data.md)。

## 4. 构建字库

`build_charset.py` 统计游戏使用的字符并加入 GB2312 字符集；`build_font.py` 重建图集，将扩展字形表写入主程序的 `.fontex` 节，并更新引用与计数。

图集尺寸和坐标约束见[字体图集与字形表](reverse-engineering/font-and-glyph-table.md)。

## 5. 写回文本与程序资源

`build_patch.py` 组织以下操作：

- 脚本 CSV：通过 `csvspan.py` 替换目标字段的字节区间，保留其他字节。
- 二进制表：将 UTF-8 译文写入定长字段，剩余空间填零。
- 主程序字符串：在字库补丁结果上原地覆盖，译文不得超过原文字节数。
- 环境设置程序：更新 Win32 界面资源。

文本默认暂存为不压缩的 `stage/text.zip`，减少重复访问小文件的开销。`--loose` 可改用散文件，供调试查看。

## 6. 打包与生成清单

`repack_pak.py` 重建 `PACK01.PAK`，保留条目的原始文件名字节与异或密钥。

`PACK00_01.PAK` 中的新旧字体图集长度相同，因此生成约 16.8 MB 的原地修改数据及 `inplace.json` 计划，无需重建整个封包。

`build.py` 最后生成 `manifest.json`，记录补丁版本、原始主程序摘要、产物大小及 SHA-256。

## 7. 安装与还原

`install.py` 核对版本后，将原始文件或修改区间备份到游戏目录的 `Backup/`。完整文件通过临时文件、校验与改名替换，字体图集按计划写入指定区间。

还原计划同时保存到 `Backup/inplace.json`，清理构建目录后仍可卸载。写入失败时尝试回滚，恢复方法见[安装与卸载](install.md)。

## 运行与验证

```powershell
py -3 tools/build.py --version 0.9.0
py -3 tools/install.py --apply
```

无改动重建应通过 `tools/test_roundtrip.py` 的逐字节比较。安装与还原逻辑由 `tools/selftest_install.py` 检查。完整工具列表见[工具索引](../tools/README.md)。
