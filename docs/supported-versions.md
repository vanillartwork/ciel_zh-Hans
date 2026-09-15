# 支持的游戏版本

当前支持 Windows x64 的 Steam 版 Ciel nosurge DX，版本标识为 `steam-2025-07`。文件大小与 SHA-256 记录在 [data/game-versions.csv](../data/game-versions.csv)。

版本核对以文件摘要为准。安装器检查主程序、环境设置程序、`PACK01.PAK` 与 `PACK00_01.PAK`；无法确认兼容性时停止安装。

## 检查本地版本

在仓库根目录运行：

```powershell
py -3 tools/preflight.py
```

检查包括必要文件、磁盘空间和版本匹配情况。发现未知版本时会输出对应文件的 SHA-256。

补丁依赖特定版本的封包布局、字形表位置和程序指令偏移，不能直接用于其他版本。

## 游戏更新后的适配

若更新后无法安装，请提交[安装与运行问题](../../issues/new?template=bug.yml)，附检查输出与 SHA-256。

维护者适配新版本时须：

1. 验证封包格式及无改动重建。
2. 重新确认字形表、程序引用和字符串位置。
3. 提取原文，核对 `id` 与 `src`，迁移仍匹配的译文。
4. 完成构建、安装、试玩与还原验证。
5. 更新 `data/game-versions.csv`。

## 其他平台

本项目仅支持 Windows DX 版。PS Vita 版及其他版本须单独适配，可参考[文件格式资料](reverse-engineering/README.md)。
