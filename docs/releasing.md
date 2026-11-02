# 发布流程

## 版本约定

补丁版本（如 `v0.9.7`）与游戏版本（如 `steam-2025-07`）分别记录。Release 标题使用补丁版本，发布说明注明支持的游戏版本。

- 主版本：不兼容旧版或需要重新安装的改动。
- 次版本：新增较大范围的翻译内容。
- 修订版本：译文及程序修正。

## 发布前检查

1. 在 `CHANGELOG.md` 写明本次发布修了什么、还有哪些限制。
2. 核对 `docs/known-issues.md`，并在发布说明中指出仍影响玩家的问题。
3. 若重建字库，运行 `py -3 tools/export_charset.py`，使 `data/charset.txt` 与实际字形表一致。
4. 运行数据校验与工具自检，修正全部错误：

   ```powershell
   py -3 tools/validate.py
   py -3 tools/selftest_validate.py
   py -3 tools/selftest_install.py
   .\native\build.ps1
   py -3 tools/selftest_pe_loader.py
   ```

5. 指定一份受支持的干净游戏副本，在同一个目录上构建、安装和卸载；不要让自动查找选中日常游玩的目录：

   ```powershell
   $game = 'D:\Test\CielnosurgeDX'   # 换成自己的测试副本
   py -3 tools/build.py --game $game --version 0.9.7
   py -3 tools/install.py --game $game --apply
   py -3 tools/install.py --game $game --verify
   ```

   检查对白名牌、任务菜单和触摸互动。退出后运行 `py -3 tools/install.py --game $game --restore`，与安装前的文件摘要比较。发布前还应从最终安装包解出工具，在干净副本上验证一遍安装与卸载。

## 打包与发布

在已安装 NSIS 的 Windows 环境中运行：

```powershell
cd installer
.\build-installer.ps1 -Version 0.9.7
```

安装包和 `.sha256` 位于仓库上级的 `dist/`。回到仓库根目录后创建并推送标签：

```bash
git tag -a v0.9.7 -m "简体中文补丁 v0.9.7"
git push origin v0.9.7
```

推送标签后 CI 只校验数据，**不会创建或修改 Release**。在 GitHub 网页上新建 Release，手动填写说明，并附上本地生成的安装包和校验和文件。CI 不持有游戏文件，无法执行完整构建。

## 发布说明

发布说明可从[模板](../.github/RELEASE_TEMPLATE.md)开始，列出玩家能看到的变化、支持的游戏版本和已知限制。需要统计译文进度或整理文件摘要时，可在本地运行 `tools/release_notes.py`。

游戏更新后的适配流程见[支持的游戏版本](supported-versions.md)。
