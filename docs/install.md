# 安装与卸载

## 安装要求

- Windows 10 或更高版本，64 位系统。
- 已合法购买并安装的 Steam 版 Ciel nosurge DX。
- 游戏所在磁盘至少有 1,200 MB 可用空间。
- 安装前关闭游戏。

支持的游戏版本见[版本说明](supported-versions.md)。安装器在本机读取游戏文件并生成补丁，通常需要数分钟。

## 安装步骤

1. 从 [Releases](https://github.com/vanillartwork/ciel_zh-Hans/releases) 下载 `CielNosurgeDX-zh-Hans-<版本>-setup.exe`。
2. 如需核对下载文件，运行以下命令，并与发布页提供的 SHA-256 比较：

   ```powershell
   Get-FileHash .\CielNosurgeDX-zh-Hans-0.9.7-setup.exe -Algorithm SHA256
   ```

   0.9.7 正式安装包的摘要为 `bf1dc7e13bd0ddb4dfe6f1e062687cbc13a941a69d12f66d9466c129a8be19c9`。其他版本请核对各自的 `.sha256` 文件。

3. 运行安装器，确认游戏目录并按提示完成安装。

0.9.7 安装包未签名，Windows 可能显示未知发布者提示。若文件摘要与发布页不符，请勿运行，重新下载后再核对。

安装器自动查找 Steam 游戏目录；未找到时，可手动选择包含 `CielnosurgeDX.exe` 的目录。工具与日志默认保存在 `%LOCALAPPDATA%\CielNosurgeDX-zh-Hans`。

安装流程为：释放工具与数据、核对版本、生成补丁、备份原始文件、写入补丁。版本检查或构建失败时，游戏文件不会被修改；写入失败时，工具会尝试还原已完成的修改，并记录错误。

## 修改与备份范围

| 文件 | 修改内容 | 备份方式 |
|---|---|---|
| `CielnosurgeDX.exe` | 字形表、可替换的程序文本及显示层加载入口 | 完整备份 |
| `CielnosurgeDX_Env.exe` | 环境设置界面文本 | 完整备份 |
| `Res_x64/PACK01.PAK` | 剧情、界面与数据表文本 | 完整备份 |
| `Res_x64/PACK00_01.PAK` | 字体图集 | 仅备份约 16.8 MB 的修改区间 |
| `cielzh.dll`（新增） | 显示层：在显示时把名牌、教学标题等换成中文 | 无原版；按归属记录管理 |
| `cielzh-text.bin`（新增） | 显示层的替换表，安装时在本机生成 | 无原版；按归属记录管理 |

两个新增文件只在它们仍是本补丁写入的那一份时才会被升级或删除；同名的其他文件不会被覆盖或删除。显示层每次启动会在游戏目录写下一个很小的 `cielzh-loader.log`（加载结果），可以随时删除。排查问题时，在游戏目录放一个名为 `cielzh-trace.on` 的空文件，会额外记录界面文字到 `cielzh-trace.txt`；记录会定期写盘，可能造成轻微卡顿，平时不要开。

备份及还原计划保存在游戏目录的 `Backup/` 中，卸载前请保留该目录。补丁不修改存档格式、存档文件或 Steam 云存档。

如果升级时提示字体图集的修改位置与旧版不同，请先按下面的方法卸载旧版，再运行新安装包。不要删除 `Backup/`。

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

可能由游戏更新、其他补丁或文件损坏引起。先使用 Steam 验证文件完整性，再重试安装。若仍不匹配，请提交[安装与运行问题](https://github.com/vanillartwork/ciel_zh-Hans/issues/new?template=bug.yml)，附日志中的 SHA-256。

### 安装后仍显示日文

确认安装器显示成功，并查看[未汉化内容](not-translated.md)，排除已知保留项。使用源码工具时，可检查文件状态：

```powershell
py -3 tools/install.py --verify
```

若目标文件仍为原版，检查日志中的文件占用或权限错误，关闭游戏后重试。

### 找不到存档

本作需要**手动存档**，标题画面在有存档之后才会出现读取。默认键位下：在依恩的房间按 **I** 打开菜单，再按 **J** 切换到底部的 INFORMATION 栏，其中有设置、SAVE（存档）、LOAD（读档）等图标。底部这一栏需要切换才会出现，这是游戏原本的设计。存档位于 `文档\KoeiTecmo\CielnosurgeDX\SaveData\`，安装、卸载补丁都不会改动它。

### 触摸互动按不出反应

游戏按手柄设计。默认键位下（`文档\KoeiTecmo\CielnosurgeDX\Setting.ini`），触摸、抚摸依恩的操作是：**按住 J**（画面左下角的手掌开关，对应手柄 X／□），再**按 F**（对应按下左摇杆）。用 WASD 移动手指光标。键位可在环境设置程序 `CielnosurgeDX_Env.exe` 中修改。

### 游戏崩溃或显示异常

卸载补丁后复测，并记录问题是否仍存在。提交 Issue 时请附补丁版本、出现位置、复现步骤、截图及 `install.log`。自动恢复失败时，使用 Steam 验证文件完整性。

手动构建与安装见[构建指南](build.md)。
