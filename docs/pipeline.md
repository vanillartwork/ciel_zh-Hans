# 构建流程

中文 | [English](pipeline.en.md)

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
| `inc/dream/*.gbd` | `gbd_text.py` | 进门副标题、HISTORY、废墟与修复对象名 |
| `CielnosurgeDX.exe` | `export_exe_text.py` | 程序内 UTF-8 字符串 |
| `CielnosurgeDX_Env.exe` | `env_strings.py` | Win32 资源中的设置界面文本 |

脚本仅提取可翻译字段，指令与开发者注释保持原样。格式见[剧情脚本](reverse-engineering/event-script.md)与[二进制数据表](reverse-engineering/binary-tables.md)。

剧情脚本的提取结果约 130 个 CSV，存放在提取目录下不压缩的 `script.zip` 中，而不是散文件。术语统计、合并、字库字符统计和写回通过 `workscript.py` 读取。集中存储减少了小文件反复打开的开销；此次本机对照记录为完整构建约 45 秒降到约 29 秒，不代表其他机器的固定耗时。CSV 的编码和序列化规则不变，容器固定成员顺序和时间戳。

- 读取时只认一种来源。`script.zip` 与 `script/` 同时存在、成员重名、名称或顺序不符合约定、ZIP 损坏或 CRC 校验失败时拒绝读取，不会退回另一份。重新提取是例外，会清除旧的 `script/` 并生成容器。
- 当前没有独立的预期成员清单：两种来源都不存在时读取返回空列表，合并遇到缺少的剧本成员仍可能跳过并返回成功。因此尚不能保证“缺少成员必定中止”，发布前应另行核对成员集合。
- 容器不在原处更新：合并结果先写成新的临时文件，读回核对后再替换。
- 需要散文件的维护工具（如 `test_roundtrip.py`、`make_batches.py`）会要求先解包。`repo_export.py`、`hydrate.py`、`dev/rewrap_memos.py` 和 `dev/gen_memo_history.py` 已能读取两种来源。维护命令及转换限制见[构建指南](build.md#剧本中间文件与维护)。

## 3. 合并译文

`merge_repo.py` 按 `id` 匹配条目，并将本地原文摘要与仓库中的 `src` 比较。匹配后写入 `zh`；不匹配的条目保留原文，不匹配比例超过 2% 时中止。

字段说明见[翻译数据格式](translation-data.md)。

## 4. 构建字库

`build_charset.py` 统计游戏使用的字符并加入 GB2312 字符集；`build_font.py` 重建图集，将扩展字形表写入主程序的 `.fontex` 节，并更新引用与计数。

图集尺寸和坐标约束见[字体图集与字形表](reverse-engineering/font-and-glyph-table.md)。

## 5. 写回文本与程序资源

`build_patch.py` 组织以下操作：

- 脚本 CSV：通过 `csvspan.py` 替换目标字段的字节区间，保留其他字节。`build_patch.py` 在注入前排除 `kind=memo` 的条目，写备忘指令的参数保留日文。
- 二进制表：将 UTF-8 译文写入定长字段，剩余空间填零。
- 梦世界数据表：按固定记录布局写回显示字段，只占用原文已用的字节；地点读音另行清空，编号和未知字节保持原样。
- 主程序字符串：在字库补丁结果上写入，译文不得超过原文字节数。`exe_sites.py` 先核对授权地址，全局替换跳过这些条目，避免改到同文的查找键。
- 显示层：保留角色键及备忘原文，生成 `cielzh-text.bin`。摘要的章节、状态、关系和计数移到显示层；`old_saves.py` 的映射用于新旧存档，计数目前枚举 0～999。`old_memos.py` 补充历史中文及可唯一识别的截断文本，匹配时不回写存档。游玩时间格式仍在主程序中翻译，详见[程序文本](reverse-engineering/executable-strings.md)。PE 工具在主程序副本上写入加载 `cielzh.dll` 的入口。
- 环境设置程序：更新 Win32 界面资源。

文本默认暂存为不压缩的 `stage/text.zip`，减少重复访问小文件的开销。`--loose` 可改用散文件，供调试查看。

## 6. 打包与生成清单

`repack_pak.py` 重建 `PACK01.PAK`，保留条目的原始文件名字节与异或密钥。

`PACK00_01.PAK` 中的新旧字体图集长度相同，因此生成约 16.8 MB 的原地修改数据及 `inplace.json` 计划，无需重建整个封包。

`build.py` 最后生成 `manifest.json`，记录补丁版本、原始主程序摘要、产物大小及 SHA-256。

## 7. 安装与还原

`install.py` 核对版本后，将原始文件或修改区间备份到游戏目录的 `Backup/`。完整文件通过临时文件、校验与改名替换，字体图集按计划写入指定区间。

还原计划同时保存到 `Backup/inplace.json`，清理构建目录后仍可卸载。写入失败时尝试回滚，恢复方法见[安装与卸载](install.md)。

安装前，工具把本次操作及回滚副本记在 `Backup/install_tx.json` 和 `Backup/rollback/`。提交前失败会撤销到安装前的状态；提交后中断只清理临时资料。恢复失败会保留副本，下次安装可以重试。

若新版不再覆盖旧版改过的区间，须先还原旧版。新增的 DLL 和替换表由 `Backup/created.json` 记录，安装器不会接管其他来源的同名文件。

## 运行与验证

```powershell
./native/build.ps1
py -3 tools/build.py --version 0.9.8
py -3 tools/install.py --apply
```

无改动重建应通过 `tools/test_roundtrip.py` 的逐字节比较。安装与还原由 `selftest_install.py` 和 `selftest_install_flow.py` 检查；新增文本写回还分别有 EXE 地址和 GBD 自检。完整工具列表见[工具索引](../tools/README.md)。
