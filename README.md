简体中文 · [English](README.en.md)

# 《Ciel nosurge DX》简体中文本地化项目

本项目提供《Ciel nosurge DX》（シェルノサージュ ～失われた星へ捧ぐ詩～ DX）的非官方简体中文补丁，以及文本提取、校验、构建和安装工具。

补丁免费提供，与 GUST、光荣特库摩及其关联公司无隶属、合作或授权关系。使用前须合法购买并安装游戏。版权与授权说明见 [NOTICE.md](NOTICE.md)。

## 翻译进度

共 92,094 条文本，已译 91,744 条，完成度 99.62%。

| 内容 | 条目数 | 已译比例 |
|---|---:|---:|
| 剧情脚本（全 13 章、支线及日常内容） | 77,486 | 100% |
| 界面文本 | 8,238 | 100% |
| 道具文本 | 1,152 | 100% |
| 术语与说话人名 | 1,089 | 99.9% |
| 全局文本（帮助、邮件、夏尔名字等） | 3,698 | 92.2% |
| 主程序内文本 | 377 | 84.4% |
| 环境设置程序 | 54 | 100% |

剩余 350 条为屏蔽词、程序内部标识及空白名牌，保留原文。图片文字与部分视频字幕尚未处理，详见 [未汉化内容](docs/not-translated.md)。

## 安装与卸载

1. 在 [Releases](../../releases) 下载 `CielNosurgeDX-zh-Hans-<版本>-setup.exe`。
2. 关闭游戏，运行安装程序并按提示选择游戏目录。

支持 Windows 10 及以上 64 位系统。游戏所在磁盘须至少有 1,200 MB 可用空间，安装过程通常需要数分钟。安装器核对游戏版本后，在本机生成补丁，备份原始文件并安装。

当前支持的版本见 [游戏版本说明](docs/supported-versions.md)。安装包包含译文和工具，游戏程序与资源由本机已安装的游戏提供。

可在 Windows「设置 → 应用」中卸载，或运行游戏目录下 `Backup/卸载简体中文补丁.exe`。卸载时还原原始文件；备份缺失时，可通过 Steam「验证游戏文件完整性」恢复。

详细步骤与故障排查见 [安装指南](docs/install.md)。

## 问题反馈

| 问题 | 提交入口 |
|---|---|
| 错译、错字、表达或术语不一致 | [翻译问题](../../issues/new?template=mistranslation.yml) |
| 文字溢出、重叠、缺字 | [显示问题](../../issues/new?template=display.yml) |
| 安装失败、崩溃、卡顿 | [安装与运行问题](../../issues/new?template=bug.yml) |
| 译名讨论 | [术语讨论](../../issues/new?template=terminology.yml) |

请注明补丁版本、出现位置和复现步骤，并附截图；安装问题请附日志。已知问题见 [docs/known-issues.md](docs/known-issues.md)。

## 参与贡献

翻译与校对无需编程经验。可直接编辑 `data/zh-Hans/` 中的 CSV，仅修改 `zh`、`status`、`note` 列，日文原文保存在 `jp` 列。

提交 Pull Request 前运行：

```powershell
py -3 tools/validate.py
```

贡献流程见 [CONTRIBUTING.md](CONTRIBUTING.md)，译文须遵循 [翻译规范](docs/style-guide.md) 和 [术语表](data/glossary/glossary.csv)。

## 构建与开发

在已配置构建环境的仓库根目录运行：

```powershell
py -3 tools/build.py --version 0.9.0
py -3 tools/install.py --apply
```

依赖、参数与安装前检查见 [构建指南](docs/build.md)。其他资料：

- [文档索引](docs/README.md)
- [构建流程](docs/pipeline.md)与[翻译数据格式](docs/translation-data.md)
- [文件格式资料](docs/reverse-engineering/README.md)
- [其他语言移植](docs/porting-to-other-languages.md)

## 授权

| 内容 | 许可证 |
|---|---|
| 工具、脚本及安装程序代码 | [PolyForm Noncommercial 1.0.0](LICENSE) |
| 译文、术语表及文档 | [CC BY-NC-SA 4.0](LICENSE-TRANSLATIONS) |

许可证仅适用于贡献者有权授权的原创内容，不授予原游戏及其他第三方内容的权利。未经另行授权，不得商业使用。完整说明见 [NOTICE.md](NOTICE.md)。
