# 构建指南

## 环境要求

- Python 3.10 或更高版本。
- 合法拥有且版本受支持的 Ciel nosurge DX。
- 游戏所在磁盘至少 1,200 MB 可用空间，构建输出目录也须有足够空间。
- 重建字库所需的 NumPy、Pillow 及本地中文字体。

以下命令在仓库根目录运行，示例使用 Windows PowerShell：

```powershell
py -3 -m pip install numpy pillow
py -3 tools/preflight.py
py -3 tools/build.py --version 0.9.0
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

```powershell
py -3 tools/install.py            # 预览安装操作
py -3 tools/install.py --apply    # 备份并安装
py -3 tools/install.py --verify   # 检查安装状态
py -3 tools/install.py --restore  # 还原原始文件
```

使用自定义输出目录时，安装命令须加上 `--from <构建目录>`。

## 常用参数

| 参数 | 用途 |
|---|---|
| `--game <目录>` | 指定游戏目录 |
| `--out <目录>` | 指定构建输出目录 |
| `--skip-font` | 复用输出目录中已有的字体图集 |
| `--skip-validate` | 跳过数据校验，仅用于调试 |
| `--no-repack` | 完成暂存后停止，不生成安装封包 |
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

## 构建安装程序

安装 NSIS 并将 `makensis` 加入 PATH 后运行：

```powershell
cd installer
.\build-installer.ps1 -Version 0.9.0
```

安装包及 `.sha256` 输出到仓库上级的 `dist/`，与补丁构建目录 `build/dist/` 不同。详见[安装程序说明](../installer/README.md)。
