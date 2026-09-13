# 更新记录

本文件记录**补丁**的版本。适用的**游戏**版本见
[`data/game-versions.csv`](data/game-versions.csv)。

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

## [未发布]

## [0.9.0] - 2025-09-12

首个公开版本。

### 新增

- 主线全 13 章、支线、日常事件的简体中文翻译（77,486 行，100%）
- 界面文本全部汉化（8,238 行）
- 道具名称与说明全部汉化（1,152 行）
- 可执行文件内 318 条硬编码日文字符串汉化：确认对话框、
  网络提示、菜单项、依恩的状态描述等
- 重建字库：9,351 个字形，GB2312 全覆盖，
  中文部分统一用同一种字体绘制
- NSIS 安装程序：核对游戏版本、自动备份、失败自动回滚、
  支持完整卸载还原
- 自动校验（`tools/validate.py`）：控制码、字节上限、字库覆盖、
  术语一致性等 13 项检查，不需要游戏即可运行
- 校验器自检（`tools/selftest_validate.py`），19 项
- 完整的格式与逆向资料（`docs/reverse-engineering/`）

### 修正

- 修正 105 行译文中残留的日文：未替换的 `{}` 术语，
  以及被当作中文保留的日文促音「ッ」「っ」
- 统一约 380 处跨章节的术语与人名漂移
- 修正 exe 字符串扫描器的正则，此前会在 `※ ★ ® ＆` 和全角数字处
  把字符串截断，导致 71 条（多为确认对话框）无法定位

### 已知问题

见 [docs/known-issues.md](docs/known-issues.md)。

[未发布]: https://github.com/vanillartwork/ciel_zh-Hans/compare/v0.9.0...HEAD
[0.9.0]: https://github.com/vanillartwork/ciel_zh-Hans/releases/tag/v0.9.0
