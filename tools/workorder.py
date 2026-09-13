# -*- coding: utf-8 -*-
"""Put the remaining files in the order they should be translated.

  py -3 workorder.py <export dir> [out file]

Order follows what a player runs into and how often, not file size: the
tutorial and the menus come first because every player sees them within
minutes, the daily chatter next because it repeats all game long, and the
one-off side episodes last.  The Sharl name generator is deliberately at the
very bottom -- 1,624 rows of invented pet names with a 4-6 character budget,
worth doing only once everything with actual sentences is done.
"""
import sys, os, io, csv

# (bucket title, why it is here, filename prefixes in order)
PLAN = [
    ("1. 教程与菜单", "玩家开局几分钟内必然看到", [
        "script/tutorialevent", "script/menuevent"]),
    ("2. 日常互动", "贯穿全程、出现频率最高的内容", [
        "script/chatevent", "script/activeevent", "script/passiveevent",
        "script/ownevent"]),
    ("3. 道具反应", "每次给依恩东西都会触发", [
        "script/itemevent"]),
    ("4. 日常事件与系统", "按日期与状态触发的日常", [
        "script/daysevent", "script/dayseventex", "script/dayseventrc",
        "script/daystaskevent", "script/formatevent", "script/relationevent",
        "script/special", "script/useeventall", "script/lockevent",
        "script/haircutevent", "script/cafeevent"]),
    ("5. 同寝与季节", "重复性高的长篇日常", [
        "script/soineevent", "script/seasonevent"]),
    ("6. 角色线", "妮莉库线与约会", [
        "script/nelicoevent", "script/nelico_dateevent",
        "script/dateevents", "script/dateromevent", "script/dateevent"]),
    ("7. 支线剧情", "主线之外的剧情章节", [
        "script/mainscenarioevent"]),
    ("8. 追加篇章", "EXTRA 与 DLC", [
        "script/ex0", "script/ex1", "script/itemeventdlc",
        "script/linkarnosurge"]),
    ("9. 结局与其余", "收尾", ["script/"]),
    ("10. 夏尔名字库", "1,624 条程序生成的宠物名，字节上限 4~6 字，最后再做",
        ["global_text"]),
]


def remaining(exportdir):
    out = {}
    for root, _, files in os.walk(exportdir):
        for fn in sorted(files):
            if not fn.endswith(".csv") or fn.startswith("_") or fn == "official_glossary.csv":
                continue
            p = os.path.join(root, fn)
            rel = os.path.relpath(p, exportdir).replace(os.sep, "/")
            n = c = 0
            with io.open(p, encoding="utf-8-sig", newline="") as f:
                for r in csv.DictReader(f):
                    if "zh" not in (r or {}) or r["zh"].strip():
                        continue
                    n += 1
                    c += len(r["jp"])
            if n:
                out[rel] = (n, c)
    return out


def main(exportdir, out_path=None):
    rem = remaining(exportdir)
    used = set()
    lines = []
    tot_rows = sum(v[0] for v in rem.values())
    tot_ch = sum(v[1] for v in rem.values())
    lines.append("# 剩余翻译工作顺序")
    lines.append("")
    lines.append("共 %d 个文件，%s 行，%s 个日文字符。" %
                 (len(rem), format(tot_rows, ","), format(tot_ch, ",")))
    lines.append("")
    lines.append("按下面的顺序逐组下发。组内按行数从多到少排列，")
    lines.append("每组做完再进下一组，这样任何时候停下来，")
    lines.append("玩家最先接触到的内容都已经是中文的。")
    lines.append("")
    for title, why, prefixes in PLAN:
        picked = []
        for pref in prefixes:
            for rel in sorted(rem):
                if rel in used or not rel.startswith(pref):
                    continue
                used.add(rel)
                picked.append(rel)
        if not picked:
            continue
        picked.sort(key=lambda r: -rem[r][0])
        n = sum(rem[r][0] for r in picked)
        c = sum(rem[r][1] for r in picked)
        lines.append("## %s" % title)
        lines.append("")
        lines.append("%s — %s 行 / %s 字，%d 个文件" %
                     (why, format(n, ","), format(c, ","), len(picked)))
        lines.append("")
        lines.append("| 文件 | 行 | 字 |")
        lines.append("|---|---:|---:|")
        for r in picked:
            lines.append("| `%s` | %s | %s |"
                         % (r, format(rem[r][0], ","), format(rem[r][1], ",")))
        lines.append("")
    text = "\n".join(lines)
    if out_path:
        io.open(out_path, "w", encoding="utf-8", newline="\n").write(text)
        print("work order -> %s  (%d files, %s rows)"
              % (out_path, len(rem), format(tot_rows, ",")))
    else:
        print(text)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
