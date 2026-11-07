# 构建指南

中文 | [English](build.en.md)

## 环境要求

- Python 3.10 或更高版本。
- 合法拥有且版本受支持的 Ciel nosurge DX。
- 游戏所在磁盘至少 1,200 MB 可用空间，构建输出目录也须有足够空间。
- 默认构建包含显示层，需要 Visual Studio 或 Build Tools 的 MSVC x64 工具链和 Windows SDK。使用预编译安装包的玩家不需要安装这些工具。
- 重建字库所需的 NumPy、Pillow 及本地中文字体。

以下命令在仓库根目录运行，示例使用 Windows PowerShell：

```powershell
py -3 -m pip install numpy pillow
./native/build.ps1               # 编译显示层、发射工具并运行原生自检
py -3 tools/preflight.py
py -3 tools/build.py --version 0.9.8
```

构建依次执行数据校验、原文提取、译文合并、字库重建、文本写回、打包和清单生成。任一阶段失败即停止；构建过程不写入游戏目录。

## 输出与安装

```text
build/
  work/          提取结果与合并后的译文
  font/          字体图集与修改后的主程序
  stage/         文本中间包 text.zip、可执行文件及字体资源
  dist/          可安装的封包与原地修改数据
  manifest.json  构建版本、文件清单与校验和
```

构建产物含游戏数据，不得提交到仓库。

`work/script.zip` 保存提取、合并后的剧本 CSV；`stage/text.zip` 保存写回后的游戏资源。两者用途不同。`--loose` 只控制后者的暂存方式，不会把 `script.zip` 改成散文件。

```powershell
py -3 tools/install.py            # 预览安装操作
py -3 tools/install.py --apply    # 备份并安装
py -3 tools/install.py --verify   # 检查安装状态
py -3 tools/install.py --restore  # 还原原始文件
```

使用自定义输出目录时，安装命令须加上 `--from <构建目录>`。

## 剧本中间文件与维护

需要直接编辑提取后的剧本 CSV 时，在构建副本上运行：

```powershell
py -3 tools/workscript.py unpack build/work
# 编辑 build/work/script/*.csv，或运行需要散文件的维护工具
py -3 tools/workscript.py pack build/work
```

参数是提取目录，不是 ZIP 路径。`unpack` 成功后移除 ZIP；`pack` 成功后只保留 ZIP。两种来源同时存在时读取会报错，不能依赖自动选择新的一份。重新执行提取阶段会覆盖中间结果，不用于保留手工修改。

转换本身尚不是可恢复事务：`pack` 会先删除散文件目录再写 ZIP，`unpack` 中断可能留下两种来源。操作前保留独立副本，尤其是其中有未同步回仓库的修改时。不要把“ZIP 替换前读回校验”理解为整个转换过程均可中断恢复。

## 常用参数

| 参数 | 用途 |
|---|---|
| `--game <目录>` | 指定游戏目录 |
| `--out <目录>` | 指定构建输出目录 |
| `--skip-font` | 复用输出目录中已有的字体图集 |
| `--skip-validate` | 跳过数据校验，仅用于调试 |
| `--no-repack` | 完成暂存后停止，不生成安装封包 |
| `--no-loader` | 诊断用：不写显示层入口，不安装 DLL 或替换表 |
| `--loose` | 使用散文件暂存文本，便于检查 |
| `--phase <阶段>` | 单独执行 `check`、`extract`、`font`、`inject` 或 `repack` |

各阶段共享输出目录，须按上述顺序执行。游戏目录和字体也可通过环境变量指定：

```powershell
$env:CIEL_NOSURGE_DX = "D:\SteamLibrary\steamapps\common\CielnosurgeDX"
$env:CIEL_NOSURGE_FONT = "C:\Windows\Fonts\msyhbd.ttc"
```

## 常见问题

### 原文匹配失败

合并时会核对 `id` 与原文摘要。大量不匹配通常表示游戏版本不同，或提取时读取了已修改的文件；不匹配比例超过 2% 时构建中止。

工具优先读取原始备份。若备份缺失或不正确，请还原游戏后重建，必要时通过 Steam 验证文件完整性。

### 找不到字体或字形错位

默认字体为微软雅黑 Bold。可用 `CIEL_NOSURGE_FONT` 指定字体；更换字体后须重新校准 `build_font.py` 中的渲染参数。

图集尺寸须保持 8192×4096，字形按 4 像素块对齐。详细约束见[字体图集与字形表](reverse-engineering/font-and-glyph-table.md)。

### 安装后仍显示日文

引擎从封包读取资源，暂存散文件不会直接生效。确认已完成打包与安装，且未使用 `--no-repack` 中止构建。

名牌、摘要和备忘等文字还依赖显示层。`--no-loader` 构建不会提供这部分中文；正常构建可用 `install.py --verify` 检查上次启动留下的加载结果和显示表状态。

## 构建安装程序

安装 NSIS 并将 `makensis` 加入 PATH 后运行：

```powershell
cd installer
.\build-installer.ps1 -Version 0.9.8
```

安装包及 `.sha256` 输出到仓库上级的 `dist/`，与补丁构建目录 `build/dist/` 不同。详见[安装程序说明](../installer/README.md)。
