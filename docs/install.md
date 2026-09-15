# 安装与卸载

## 安装要求

- Windows 10 或更高版本，64 位系统。
- 已合法购买并安装的 Steam 版 Ciel nosurge DX。
- 游戏所在磁盘至少有 1,200 MB 可用空间。
- 安装前关闭游戏。

支持的游戏版本见[版本说明](supported-versions.md)。安装器在本机读取游戏文件并生成补丁，通常需要数分钟。

## 安装步骤

1. 从 [Releases](../../releases) 下载 `CielNosurgeDX-zh-Hans-<版本>-setup.exe`。
2. 如需核对下载文件，运行以下命令，并与发布页提供的 SHA-256 比较：

   ```powershell
   Get-FileHash .\CielNosurgeDX-zh-Hans-0.9.0-setup.exe -Algorithm SHA256
   ```

3. 运行安装器，确认游戏目录并按提示完成安装。

安装器自动查找 Steam 游戏目录；未找到时，可手动选择包含 `CielnosurgeDX.exe` 的目录。工具与日志默认保存在 `%LOCALAPPDATA%\CielNosurgeDX-zh-Hans`。

安装流程为：释放工具与数据、核对版本、生成补丁、备份原始文件、写入补丁。版本检查或构建失败时，游戏文件不会被修改；写入失败时，工具会尝试还原已完成的修改，并记录错误。

## 修改与备份范围

| 文件 | 修改内容 | 备份方式 |
|---|---|---|
| `CielnosurgeDX.exe` | 字形表及程序内文本 | 完整备份 |
| `CielnosurgeDX_Env.exe` | 环境设置界面文本 | 完整备份 |
| `Res_x64/PACK01.PAK` | 剧情、界面与数据表文本 | 完整备份 |
| `Res_x64/PACK00_01.PAK` | 字体图集 | 仅备份约 16.8 MB 的修改区间 |

备份及还原计划保存在游戏目录的 `Backup/` 中，卸载前请保留该目录。补丁不修改存档格式、存档文件或 Steam 云存档。

## 卸载与还原

在 Windows「设置 → 应用」中找到「Ciel nosurge DX 简体中文补丁」并卸载，也可运行 `Backup/卸载简体中文补丁.exe`。

卸载程序依据备份和还原计划恢复原始文件。使用源码工具时，可在仓库根目录运行：

```powershell
py -3 tools/install.py --restore
```

若备份缺失或还原失败，在 Steam 中右键游戏，依次选择「属性 → 已安装文件 → 验证游戏文件完整性」，重新获取原始文件。

## 故障排查

### 未找到游戏目录

手动选择包含 `CielnosurgeDX.exe` 的目录，通常位于：

```text
<Steam 库目录>\steamapps\common\CielnosurgeDX
```

### 游戏版本不匹配

可能由游戏更新、其他补丁或文件损坏引起。先使用 Steam 验证文件完整性，再重试安装。若仍不匹配，请提交[安装与运行问题](../../issues/new?template=bug.yml)，附日志中的 SHA-256。

### 安装后仍显示日文

确认安装器显示成功，并查看[未汉化内容](not-translated.md)，排除已知保留项。使用源码工具时，可检查文件状态：

```powershell
py -3 tools/install.py --verify
```

若目标文件仍为原版，检查日志中的文件占用或权限错误，关闭游戏后重试。

### 游戏崩溃或显示异常

卸载补丁后复测，并记录问题是否仍存在。提交 Issue 时请附补丁版本、出现位置、复现步骤、截图及 `install.log`。自动恢复失败时，使用 Steam 验证文件完整性。

手动构建与安装见[构建指南](build.md)。
