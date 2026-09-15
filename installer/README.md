# 安装程序

Windows 安装程序使用 NSIS 构建，在用户本机生成并安装补丁。

## 安装包内容

```text
payload/
  python/   可嵌入版 CPython、NumPy 与 Pillow
  tools/    项目工具
  data/     翻译数据与术语表
```

安装包不包含游戏可执行文件或资源封包，构建所需的原始文件从用户已安装的游戏读取。

## 构建

要求 Windows、NSIS，且 `makensis` 可从 PATH 调用。在本目录运行：

```powershell
.\build-installer.ps1 -Version 0.9.0
```

脚本下载并配置 Python 运行时及依赖，复制工具和数据，检查是否混入游戏资源，然后调用 NSIS。产物位于本目录的 `../../dist/`，即仓库上级的 `dist/`，包括安装程序及 `.sha256`。

## 安装流程

1. 定位游戏目录，检查必要文件及可用空间。
2. 释放工具和数据，创建安装日志。
3. 运行 `preflight.py` 核对游戏版本。
4. 分阶段调用 `build.py` 生成补丁。
5. 调用 `install.py --apply` 备份并写入。
6. 清理临时构建文件，注册卸载信息，并将卸载程序副本放入游戏目录的 `Backup/`。

空间检查阈值为 1,200 MB。版本核对或构建失败时停止安装；写入失败时尝试回滚。日志默认位于 `%LOCALAPPDATA%\CielNosurgeDX-zh-Hans\install.log`。

## 卸载与备份

卸载调用 `install.py --restore`，从 `Backup/` 恢复三个完整文件及 `PACK00_01.PAK` 的字体修改区间。还原计划保存在 `Backup/inplace.json`，不依赖临时构建目录。

还原失败时显示备份位置和错误信息；用户可通过 Steam 验证文件完整性恢复原版。

`NOTICE-INSTALLER.txt` 须保留 UTF-8 BOM，以供 NSIS 正确显示中文。

## 界面资源

`assets/patch.ico` 为安装程序图标。安装界面使用原创素材，不放置从游戏提取的资源。
