# 版权、授权与免责声明

*[English below](#notice-english)*

## 这是什么

本项目是《シェルノサージュ ～失われた星へ捧ぐ詩～ DX》（Ciel nosurge DX）的
**非官方**简体中文化项目，由爱好者制作。

## 与权利人的关系

- 本项目与 GUST CO., LTD.、KOEI TECMO GAMES CO., LTD. 及其任何关联公司
  **没有任何隶属、合作、授权或认可关系**。
- 游戏本体、以及游戏中的程序、剧本、美术、音乐、语音、角色、商标与其他一切
  内容，权利均归其各自权利人所有。
- "シェルノサージュ"、"Ciel nosurge"、"Ar nosurge"、"GUST"、"KOEI TECMO"
  等名称与标识为其各自所有者的商标或注册商标，本项目仅在指称意义上使用。

## 本项目不提供游戏

**本仓库与 Release 都不包含、也不能替代正版游戏。**

本项目刻意不上传下列内容：

- 完整或部分的游戏可执行文件
- 完整或部分的游戏封包（`.PAK`）与解包后的游戏资源
- 游戏的美术、音频、视频、模型、字体文件

仓库中保存的是本项目自己创作的译文、术语表、工具链与文档。
补丁本身不是预先打包好的游戏文件，而是**安装时在使用者本地、
用使用者自己的游戏文件重新打包生成**。

使用本补丁的前提是：**你已经合法购买并安装了该游戏。**

### 关于日文原文

翻译数据中，每一行译文旁边附有对应的**日文原文**。

这样做是为了让译者和校对者能够直接对照原文工作，
也让每一次修改在 Pull Request 中都能看清改的究竟是哪一句——
把原文单独抽走会让协作翻译变得非常困难。

需要说明的是：

- 这些原文是**为翻译与校对而收录的参照文本**，按行拆分、
  与译文成对存放，**不构成可阅读的作品形态**，也不能替代游玩游戏；
- 原文的著作权属于原权利人，本项目不对其主张任何权利，
  也不以任何授权协议对外授予它；
- 仓库中不含游戏的程序、美术、音频、视频，
  **没有游戏本体，这些文本也无法让任何人玩到这部作品**；
- 若权利人认为此种收录方式不妥，请通过 Issue 告知，
  项目将配合调整或移除。

## 授权

本仓库中的内容分两部分授权，各自只覆盖本项目原创的部分：

| 部分 | 授权 |
|---|---|
| 代码：`tools/`、`installer/` | [PolyForm Noncommercial 1.0.0](LICENSE) |
| 译文与文档：`data/`、`docs/`、各 `.md` | [CC BY-NC-SA 4.0](LICENSE-TRANSLATIONS) |

两份授权都**仅适用于本项目贡献者所创作的内容**，
**不对原游戏的任何部分主张权利，也无法向你授予原游戏的任何权利。**

### 禁止商业使用

无论哪一部分，都**禁止任何未经授权的商业使用**，包括但不限于：

- 出售本补丁，或对本补丁收费
- 将本补丁与游戏打包出售，或随付费服务分发
- 把本补丁用于付费代装、付费会员、广告变现等牟利行为
- 将译文用于任何商业产品

### 贡献者授权

向本项目提交内容（Pull Request、Issue 中的译文建议等）即表示你同意：

1. 你的贡献以上表中对应的授权协议发布；
2. 你拥有提交这些内容所需的权利，且内容并非抄袭自其他汉化组、
   机翻服务或任何未经授权的来源；
3. 你保留自己贡献的著作权，署名记录在 Git 历史中；
4. 若将来权利人愿意采纳本项目成果，项目维护者可与贡献者联系，
   在**征得你另行同意**后，以其他条款授权你的贡献。
   **本条不构成事先的自动改授权。**

## 逆向工程说明

`docs/reverse-engineering/` 中记录了封包格式、文本编码、字形表布局等信息，
目的仅限于**让文本能够被提取、翻译并写回**，以及让其他语言的社区能复用同一套工具。

本项目**不包含也不接受**与 DRM、授权验证、防盗版、访问控制等技术保护措施
相关的分析、绕过或破解内容。此类 Issue 与 Pull Request 会被直接关闭。

## 免责声明

本补丁按"现状"提供，不附带任何明示或默示的担保。

补丁会替换游戏文件。安装程序会先把原始文件备份到游戏目录下的 `Backup`，
并提供还原功能；即便如此，**使用风险由使用者自行承担**。
对于因使用本补丁导致的存档损坏、游戏无法运行或其他任何损失，
项目及其贡献者不承担责任。

随时可以通过 Steam 的"验证游戏文件完整性"恢复为原版。

## 权利人通知

若权利人认为本项目侵犯了其权益，请通过 Issue 或仓库中的联系方式告知，
项目将配合处理，包括在必要时下架相关内容。

---

<a name="notice-english"></a>

# Notice (English)

This is an **unofficial**, fan-made Simplified Chinese localisation of
*Ciel nosurge DX*.

**No affiliation.** This project is not affiliated with, endorsed by, or
licensed by GUST CO., LTD., KOEI TECMO GAMES CO., LTD., or any of their
affiliates. The game and everything in it remain the property of their
respective owners. All trademarks belong to their owners and are used here
only to refer to the work.

**This project does not provide the game.** Neither the repository nor its
releases contain the game, and neither can substitute for owning it. No game
executable, archive, unpacked asset, art, audio, video, model or font is
uploaded here. The patch is built on your machine at install time, from the
copy of the game you own. You must legally own the game to use this.

**About the Japanese source text.** Each translation is stored next to the
Japanese line it translates, so that translators and proofreaders can work
against the source and so that a pull request shows which line actually
changed. That text is included as reference material for translation: it is
split line by line, paired with its translation, and is not a readable form of
the work. Copyright in it belongs to the rights holders; this project claims
no rights in it and licenses none of it to anyone. Without the game's code,
art, audio and video — none of which is here — it does not let anyone play the
work. If the rights holders consider this inclusion inappropriate, please open
an issue and we will adjust or remove it.

**Licensing.** Code (`tools/`, `installer/`) is under
[PolyForm Noncommercial 1.0.0](LICENSE). Translations and documentation
(`data/`, `docs/`, prose) are under
[CC BY-NC-SA 4.0](LICENSE-TRANSLATIONS). Both cover **only** the original
material contributed to this project. Neither claims any right in the game,
and neither can grant you rights in it. **Unauthorised commercial use of any
kind is prohibited** — selling the patch, bundling it with the game, charging
for installation, or using the translations in a commercial product.

**Contributions.** By contributing you agree your work is released under the
licenses above, that you have the right to contribute it, and that it is not
copied from another translation group, machine translation service, or other
unauthorised source. You keep the copyright in your contribution. If rights
holders ever wish to adopt this work, maintainers may approach contributors
to relicense — **with your separate, explicit consent at that time**; nothing
here relicenses your work in advance.

**Reverse engineering.** `docs/reverse-engineering/` documents archive
formats, text encodings and the glyph table only so far as is needed to get
text out, translated, and back in, and so other language communities can
reuse the same tooling. This project does **not** include or accept anything
concerning DRM, licence checks, anti-piracy, copy protection or access
control. Issues and pull requests of that kind are closed.

**No warranty.** Provided as is. The patch replaces game files; the installer
backs the originals up to `Backup/` in the game folder and can restore them,
but you use it at your own risk. Steam's "verify integrity of game files"
restores the original game at any time.

**Rights holders:** if you believe this project infringes your rights, please
open an issue or use the contact in this repository. We will cooperate,
including taking material down.
