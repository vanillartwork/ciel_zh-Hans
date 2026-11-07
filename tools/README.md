# 工具索引

中文 | [English](README.en.md)

工具使用 Python 3.10 或更高版本。核心校验与文本处理可使用标准库运行；字库构建需要 NumPy、Pillow 和本地字体。部分维护脚本另有依赖，以脚本说明为准。

## 常用工具

| 工具 | 用途 |
|---|---|
| `hydrate.py` | 将仓库翻译数据复制到 `work/`，可选核对本地游戏原文 |
| `dehydrate.py` | 将工作副本中的译文、状态与备注同步回仓库 |
| `validate.py` | 校验翻译数据，无需游戏 |
| `build.py` | 构建补丁 |
| `install.py` | 预览、安装、还原及状态检查 |
| `preflight.py` | 安装前检查文件、空间与版本 |

## 构建组件

| 工具 | 用途 |
|---|---|
| `gamepath.py` | 定位游戏与原始备份 |
| `runlog.py`、`progress.py` | 日志和进度输出 |
| `env_strings.py` | 环境设置程序文本提取与写回 |
| `export_text.py`、`export_exe_text.py` | 封包及程序文本提取 |
| `merge_repo.py` | 按标识与摘要合并译文 |
| `workscript.py` | 剧本提取结果的交接容器 `script.zip`；`unpack`/`pack` 在散文件与容器间转换 |
| `build_charset.py` | 生成候选字符集 |
| `build_font.py` | 重建图集与字形表 |
| `export_charset.py` | 从最终字形表导出可显示字符 |
| `import_text.py` | 写回译文 |
| `patch_exe_strings.py` | 替换程序字符串（全部同文副本） |
| `exe_sites.py` | 只在地址清单授权的位置替换程序字符串 |
| `old_saves.py` | 为新旧存档的日文摘要生成整句映射，计数覆盖 0～999 |
| `old_memos.py` | 将历史备忘及无歧义的截断文本映射到当前译文，不回写存档 |
| `build_text_table.py` | 生成名牌、保留词、摘要和备忘录的显示替换表 |
| `gbd_text.py` | 梦世界数据表（`inc/dream/*.gbd`）的导出与写回 |
| `build_patch.py` | 生成暂存文件 |
| `pe_loader.py` | 将 `emit_entry.exe` 生成的入口写入主程序副本 |
| `repack_pak.py` | 打包与生成原地修改计划 |

底层模块包括 PAK 读写 `gustpak.py`、CSV 字节区间处理 `csvspan.py`、字形结构 `font_atlas.py` 和 BC1 编解码 `bc1.py`。

## 验证工具

| 工具 | 用途 | 需要游戏 |
|---|---|---|
| `selftest_validate.py` | 校验器自检 | 否 |
| `selftest_install.py` | 安装与还原自检 | 否 |
| `selftest_pe_loader.py` | 合成 PE 的加载入口、重复应用和拒绝路径（先编译原生工具） | 否 |
| `selftest_exe_sites.py` | 按地址写入：同文两份只改授权的一份、格式串、存档文字、旧存档映射 | 否 |
| `selftest_old_memos.py` | 历史备忘、UTF-8 截断、歧义与完整备忘冲突 | 否 |
| `selftest_preflight.py` | 安装预检的版本核对；升级时原地修改的封包只读一遍 | 否 |
| `selftest_workscript.py` | 剧本交接容器：单一来源、重复与损坏成员、中断写入、合并与注入读取 | 否 |
| `selftest_text_table.py` | 显示表格式、换行变体、重复项与冲突 | 否 |
| `selftest_gbd_text.py` | 梦世界数据表：只改原文占用的字节，残留与编号不动 | 否 |
| `exe_sites.py --check` | 地址清单与译文数据一致 | 否 |
| `test_roundtrip.py` | 无改动重建的逐字节比较 | 是 |
| `check_exe_text.py` | 程序字符串定位、长度及数据引用检查 | 是 |

## 维护工具

| 工具 | 用途 |
|---|---|
| `repo_export.py` | 将提取结果转换为仓库数据 |
| `build_glossary.py` | 汇总术语 |
| `release_notes.py` | 生成发布说明参考（不再由 CI 自动写入 Release） |
| `normalize_cn.py` | 字形规范化 |
| `fix_names.py`、`unify_dupes.py` | 统一译名与重复原文的译法 |
| `apply_official.py`、`official_glossary.py` | 导入官方译名 |
| `make_batches.py`、`merge_batches.py` | 分批处理译文 |
| `sync_from.py`、`audit_clone.py` | 工作目录同步与审计 |
| `workorder.py` | 生成待翻译清单 |
| `dev/import_dream_batches.py` | 验收外部翻译的梦世界数据批次并写回 `dream.csv` |
| `dev/rewrap_memos.py` | 根据脚本提取结果复查备忘录折行，`--apply` 才改译文 |
| `dev/e2e_installer.py` | 用安装包内的 Python 在干净游戏副本上跑预检、构建、安装与还原 |
| `dev/gen_memo_history.py` | 从发布标签生成 `_memo_history.csv`，供旧备忘显示兼容使用 |

## 开发约定

- 无需游戏的模块应可独立导入，游戏路径在使用时解析。
- 文件写入应明确目标与范围，提供必要的预览和恢复措施。
- 错误提示须说明失败原因、相关路径和处理方式。

操作步骤见[构建指南](../docs/build.md)、[构建流程](../docs/pipeline.md)和[自动校验](../docs/validation.md)。
