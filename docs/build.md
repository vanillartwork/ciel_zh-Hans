# 自己构建补丁

## 需要什么

- **Python 3.10 或更高**
- **你自己合法拥有的 Ciel nosurge DX**
- 约 **1 GB** 可用磁盘空间
- 只有重建字库需要：`numpy`、`Pillow`，以及一个中文字体

```bash
py -3 -m pip install numpy pillow
```

## 一条命令

```bash
py -3 tools/build.py --version 0.9.0
```

会在 `build/` 下产出：

```
build/
  work/          从你的游戏提取出来的文本（含日文，不要提交）
  font/          重建的图集和改过的 exe
  stage/         回注后的散文件
  dist/          重打包好的封包
  manifest.json  文件清单与校验和
```

然后：

```bash
py -3 tools/install.py            # 空跑，看看会改什么
py -3 tools/install.py --apply    # 真的装
```

## 常用参数

```bash
--game "D:\SteamLibrary\steamapps\common\CielnosurgeDX"   # 手动指定游戏位置
--skip-font         # 重用上次的字库（改字库以外的东西时能省几分钟）
--skip-validate     # 跳过数据校验（不建议）
--no-repack         # 停在回注，不打包（想看看回注结果时用）
--out <目录>        # 换个输出位置
```

游戏位置也可以用环境变量：

```bash
set CIEL_NOSURGE_DX=D:\SteamLibrary\steamapps\common\CielnosurgeDX
```

## 七个步骤

`build.py` 会逐步打印进度。**任何一步失败都立即停下**，
而且**前六步完全不碰游戏目录**。

| 步 | 做什么 | 大概耗时 |
|---|---|---|
| 1 | 校验翻译数据 | 几秒 |
| 2 | 从你的游戏提取日文 | 半分钟 |
| 3 | 合并仓库里的译文 | 几秒 |
| 4 | 重建字库 | 1–3 分钟 |
| 5 | 回注文本 + 改 exe | 半分钟 |
| 6 | 重打包封包 | 2–5 分钟（1.7 GB） |
| 7 | 写清单和校验和 | 几秒 |

## 常见问题

### 第 3 步说一大堆行"对不上"

```
10176 rows (11.3%) did not match the text in your game
```

**你的游戏目录已经打过补丁了。** 提取出来的是上一版的中文，
不是原文。先还原：

```bash
py -3 tools/install.py --restore
```

或在 Steam 里验证游戏文件完整性。

（正常情况下这个数字是 0。超过 2% 时 `build.py` 会直接中止。）

### 第 4 步说找不到字体

```bash
set CIEL_NOSURGE_FONT=C:\Windows\Fonts\msyhbd.ttc
```

默认用微软雅黑 Bold，它的笔画粗细和原字体 FOT-Skip Std B
相差在 1% 以内。换别的字体要重新校准 `build_font.py` 里的
`ANCHOR_X` / `ANCHOR_Y`，否则字会偏位。

### 装完了满屏乱码

几乎肯定是字库的问题。已知的两个坑：

1. **改了图集尺寸。** 引擎的 UV 除数不是从字体描述符里读的，
   图集必须保持 8192×4096。
2. **字形起始坐标是奇数。** 打包时必须按 4 像素块对齐，
   否则 `x//2` 截断会让后面所有字偏移一个像素。

两个坑 `build_font.py` 里都处理了，改它之前先读
[reverse-engineering/font-and-glyph-table.md](reverse-engineering/font-and-glyph-table.md)。

### 装完了还是日文

引擎**只读封包**，散文件放进游戏目录没有任何效果。
必须重打包（也就是不要加 `--no-repack`）。

这一点花了不少时间才弄明白，所以在这里强调一遍。

## 只想打包安装程序

```powershell
cd installer
.\build-installer.ps1 -Version 0.9.0
```

需要装了 NSIS 的 Windows 机器。脚本会下载可嵌入版 Python、
装上 numpy 和 Pillow、拷进工具和数据、**检查一遍里面没有游戏文件**，
然后编译。

产物在 `dist/`，附带 `.sha256`。
