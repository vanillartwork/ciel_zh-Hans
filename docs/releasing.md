# 发布流程

## 版本约定

补丁版本（如 `v0.9.0`）与游戏版本（如 `steam-2025-07`）分别记录。Release 标题使用补丁版本，发布说明注明支持的游戏版本。

- 主版本：不兼容旧版或需要重新安装的改动。
- 次版本：新增较大范围的翻译内容。
- 修订版本：译文及程序修正。

## 发布前检查

1. 更新 `CHANGELOG.md`，版本标题保持 `## [0.9.0] - 2025-09-12` 格式，以供发布脚本提取。
2. 更新 `docs/known-issues.md`，其内容会用于发布说明。
3. 若重建字库，运行 `py -3 tools/export_charset.py`，使 `data/charset.txt` 与实际字形表一致。
4. 运行数据校验与工具自检，修正全部错误：

   ```powershell
   py -3 tools/validate.py
   py -3 tools/selftest_validate.py
   py -3 tools/selftest_install.py
   ```

5. 在原版游戏上完成构建、安装和试玩：

   ```powershell
   py -3 tools/install.py --restore
   py -3 tools/build.py --version 0.9.0
   py -3 tools/install.py --apply
   ```

   检查标题画面、对白、菜单、道具说明、确认对话框及长文本排版，并验证卸载还原。

## 打包与发布

在已安装 NSIS 的 Windows 环境中运行：

```powershell
cd installer
.\build-installer.ps1 -Version 0.9.0
```

安装包和 `.sha256` 位于仓库上级的 `dist/`。回到仓库根目录后创建并推送标签：

```bash
git tag -a v0.9.0 -m "简体中文补丁 v0.9.0"
git push origin v0.9.0
```

CI 校验数据并创建草稿 Release。将本地生成的安装包和校验和文件附到草稿，核对发布说明后发布。CI 不持有游戏文件，无法执行完整构建。

## 发布说明

`release_notes.py` 生成以下内容，发布前须复核：

- 补丁版本、支持的游戏版本、日期与翻译进度。
- 本次更新、安装要求及已知问题。
- 支持的游戏文件 SHA-256，以及安装包校验方法。
- 非官方声明与授权说明。

游戏更新后的适配流程见[支持的游戏版本](supported-versions.md)。
