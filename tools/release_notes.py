# -*- coding: utf-8 -*-
"""Write the release notes for one version.

  py -3 tools/release_notes.py --version 0.9.0 [--out RELEASE_NOTES.md]

The notes have to answer, without anyone having to dig: what changed, which
game version this is for, how far along the translation is, what is known to
be wrong, what you need in order to install it, and how to check that the
download is the file this project published.

The patch version and the game version are deliberately kept apart. "v0.9.0"
is this project's; "Steam 2025-07" is the game's. Conflating them is how
people end up installing a patch built for a build they do not have.
"""
import sys, os, io, csv, glob, argparse, re, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")


def progress(data):
    tot = done = skip = 0
    for p in sorted(glob.glob(os.path.join(data, "zh-Hans", "**", "*.csv"),
                              recursive=True)):
        if os.path.basename(p).startswith("_"):
            continue
        for r in csv.DictReader(io.open(p, encoding="utf-8", newline="")):
            tot += 1
            if r.get("zh", "").strip():
                done += 1
            elif r.get("status") == "skip":
                skip += 1
    return tot, done, skip


def game_versions(data):
    rows = []
    p = os.path.join(data, "game-versions.csv")
    if os.path.exists(p):
        for r in csv.DictReader(io.open(p, encoding="utf-8-sig", newline="")):
            if r["status"].strip() == "supported":
                rows.append(r)
    return rows


def changelog_section(path, version):
    """The one section of CHANGELOG.md for this version."""
    if not os.path.exists(path):
        return ""
    text = io.open(path, encoding="utf-8").read()
    # ## [0.9.0] - 2025-09-12   ... up to the next "## "
    m = re.search(r"^##\s*\[?%s\]?.*?$(.*?)(?=^##\s|\Z)"
                  % re.escape(version), text, re.M | re.S)
    return m.group(1).strip() if m else ""


def known_issues(path):
    if not os.path.exists(path):
        return ""
    return io.open(path, encoding="utf-8").read().strip()


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", required=True)
    ap.add_argument("--data", default=os.path.join(ROOT, "data"))
    ap.add_argument("--changelog", default=os.path.join(ROOT, "CHANGELOG.md"))
    ap.add_argument("--issues", default=os.path.join(ROOT, "docs", "known-issues.md"))
    ap.add_argument("--out")
    a = ap.parse_args(argv)

    tot, done, skip = progress(a.data)
    versions = game_versions(a.data)
    labels = sorted({r["label"] for r in versions}) or ["未记录"]
    today = datetime.date.today().isoformat()

    L = []
    L.append("## 《Ciel nosurge DX》简体中文补丁 v%s" % a.version)
    L.append("")
    L.append("| | |")
    L.append("|---|---|")
    L.append("| **补丁版本** | v%s |" % a.version)
    L.append("| **适用游戏版本** | %s |" % "、".join(labels))
    L.append("| **发布日期** | %s |" % today)
    L.append("| **翻译进度** | %s / %s 行（%.1f%%）|"
             % (format(done, ","), format(tot, ","), 100.0 * done / max(tot, 1)))
    L.append("")
    L.append("> 补丁版本和游戏版本是两回事。上面的**适用游戏版本**指的是原游戏，")
    L.append("> 安装程序会核对；版本不符时会中止安装，而不会去改它不认识的文件。")
    L.append("")

    body = changelog_section(a.changelog, a.version)
    if body:
        L.append("### 本次更新")
        L.append("")
        L.append(body)
        L.append("")

    L.append("### 安装")
    L.append("")
    L.append("下载下面的 `CielNosurgeDX-zh-Hans-%s-setup.exe`，运行即可。" % a.version)
    L.append("")
    L.append("**需要：**")
    L.append("")
    L.append("- 64 位 Windows 10 或更高版本")
    L.append("- 已合法购买并安装的 Ciel nosurge DX")
    L.append("- 约 1 GB 可用磁盘空间")
    L.append("")
    L.append("安装程序**不包含任何游戏文件**。它会读取你自己的游戏，在本机重新")
    L.append("打包，所以需要那么多磁盘空间，也需要几分钟时间。")
    L.append("")
    L.append("被替换的原始文件会先备份到游戏目录下的 `Backup`，")
    L.append("在「应用和功能」里卸载即可还原。")
    L.append("")

    if versions:
        L.append("### 支持的游戏文件校验和")
        L.append("")
        L.append("安装程序核对的就是这些。如果你的文件对不上，说明游戏版本不同。")
        L.append("")
        L.append("| 文件 | 大小 | SHA-256 |")
        L.append("|---|---:|---|")
        for r in versions:
            L.append("| `%s` | %s | `%s` |"
                     % (r["file"], format(int(r["bytes"]), ","), r["sha256"]))
        L.append("")

    L.append("### 下载校验")
    L.append("")
    L.append("安装程序旁附有 `.sha256` 文件。核对方法：")
    L.append("")
    L.append("```powershell")
    L.append("Get-FileHash .\\CielNosurgeDX-zh-Hans-%s-setup.exe -Algorithm SHA256" % a.version)
    L.append("```")
    L.append("")
    L.append("对不上就不要运行，请从本页重新下载。")
    L.append("")

    issues = known_issues(a.issues)
    if issues:
        L.append("### 已知问题")
        L.append("")
        L.append(issues)
        L.append("")

    L.append("### 说明")
    L.append("")
    L.append("非官方爱好者作品，与 GUST、光荣特库摩没有任何隶属或授权关系；")
    L.append("不提供游戏本体，也不能替代正版。**禁止任何未经授权的商业使用。**")
    L.append("详见仓库中的 NOTICE.md。")
    if skip:
        L.append("")
        L.append("另有 %d 行按技术原因保留原文（调试信息、动作标签、屏蔽词表等），" % skip)
        L.append("每一条的理由都记在数据文件的 `note` 列里。")

    text = "\n".join(L) + "\n"
    if a.out:
        io.open(a.out, "w", encoding="utf-8", newline="\n").write(text)
        print("release notes -> %s" % a.out)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
