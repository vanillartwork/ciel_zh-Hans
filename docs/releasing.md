# 发布流程

中文 | [English](releasing.en.md)

## 版本约定

补丁版本（如 `v0.9.8`）与游戏版本（如 `steam-2025-07`）分别记录。Release 标题使用补丁版本，发布说明注明支持的游戏版本。

- 主版本：不兼容旧版或需要重新安装的改动。
- 次版本：新增较大范围的翻译内容。
- 修订版本：译文及程序修正。

## 发布前检查

1. 在 `CHANGELOG.md` 写明本次发布修了什么、还有哪些限制。正式发布时再将“0.9.8（发布准备）”移到带日期的版本标题下。
2. 核对 `docs/known-issues.md`，并在发布说明中指出仍影响玩家的问题。
3. 若重建字库，运行 `py -3 tools/export_charset.py`，使 `data/charset.txt` 与实际字形表一致。
4. 运行数据校验与工具自检，修正全部错误：

   ```powershell
   py -3 tools/validate.py
   py -3 tools/selftest_validate.py
   py -3 tools/selftest_install.py
   py -3 tools/selftest_install_flow.py
   py -3 tools/exe_sites.py --check
   py -3 tools/selftest_exe_sites.py
   py -3 tools/selftest_gbd_text.py
   py -3 tools/selftest_text_table.py
   py -3 tools/selftest_old_memos.py
   py -3 tools/selftest_workscript.py
   .\native\build.ps1
   py -3 tools/selftest_pe_loader.py
   ```

5. 指定一份受支持的干净游戏副本，在同一个目录上构建、安装和卸载；不要让自动查找选中日常游玩的目录：

   ```powershell
   $game = 'D:\Test\CielnosurgeDX'   # 换成自己的测试副本
   py -3 tools/build.py --game $game --version 0.9.8
   py -3 tools/install.py --game $game --apply
   py -3 tools/install.py --game $game --verify
   ```

   检查对白名牌、任务菜单和触摸互动；0.9.8 另需覆盖进门副标题、HISTORY 长概要、废墟名称，以及新旧存档的摘要和备忘录。退出后运行 `py -3 tools/install.py --game $game --restore`，与安装前的文件摘要比较。发布前还应从最终安装包解出工具，在干净副本上验证一遍安装与卸载。

   备忘与摘要需分别验证：补丁版新增后由原版读取；原有日文和旧中文存档在补丁版显示；可唯一识别和有歧义的截断备忘；计数范围边界；显示层未加载时的退回显示。保留独立测试存档，避免用正式存档覆盖验证。`--verify` 读取上次启动留下的状态文件，不代替本次实机观察。

## 打包与发布

在已安装 NSIS 的 Windows 环境中运行：

```powershell
cd installer
.\build-installer.ps1 -Version 0.9.8
```

安装包和 `.sha256` 位于仓库上级的 `dist/`。核对它们与本次构建对应，勿将旧的同名安装包或 `-rc` 产物当作正式版。正式发布时，回到仓库根目录创建并推送标签：

```bash
git tag -a v0.9.8 -m "简体中文补丁 v0.9.8"
git push origin v0.9.8
```

发布是手动操作，CI **不会创建或修改 Release**；当前校验工作流也没有推送标签的触发条件。在 GitHub 网页上新建 Release，手动填写说明，并附上本地生成的安装包和校验和文件。CI 不持有游戏文件，无法执行完整构建。

## 发布说明

发布说明可从[模板](../.github/RELEASE_TEMPLATE.md)开始，列出玩家能看到的变化、支持的游戏版本和已知限制。需要统计译文进度或整理文件摘要时，可在本地运行 `tools/release_notes.py`。

游戏更新后的适配流程见[支持的游戏版本](supported-versions.md)。
