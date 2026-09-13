# -*- coding: utf-8 -*-
"""Enforce the official Chinese names across every translated cell.

  py -3 fix_names.py <export dir> [--dry]

The translator can drift on a name halfway through a chapter (卡侬 instead of
卡诺).  This walks every zh cell and rewrites known wrong variants to the
official wording, then reports what it changed and where.

Only unambiguous variants are listed: strings that have no other legitimate
reading in this game.
"""
import sys, os, io, csv, collections

# wrong variant -> official.  Keep these unambiguous.
VARIANTS = {
    "卡侬": "卡诺", "卡农": "卡诺", "加农": "卡诺",
    "伊恩": "依恩", "伊翁": "依恩", "伊昂": "依恩",
    "凯丝": "凯斯",
    "拉谢拉": "拉榭拉", "拉塞拉": "拉榭拉",
    "可隆": "克隆", "科隆": "克隆",
    "莎尔": "夏尔", "沙尔": "夏尔",
    "索雷依尔": "太阳号", "索莱尔": "太阳号",
    "内罗": "妮诺", "尼禄": "妮诺", "涅罗": "妮诺",
    "涅莉可": "妮莉库", "内莉子": "妮莉库",
    "萨里": "莎丽", "莎莉": "莎丽",
    "谢尔诺特伦": "榭鲁诺特伦", "榭鲁诺托伦": "榭鲁诺特伦",
    "波动爆发": "波动爆炸",
    # drifted during the chapter 05-13 pass; the counts were lopsided enough
    # (e.g. 488 correct vs 34 wrong) to make the intended form obvious
    "歇尔诺琴": "榭鲁诺特伦", "颂歌特伦": "榭鲁诺特伦",
    "基因组": "杰诺姆",
    "德律风根": "泰雷芬肯",
    "拉歇拉": "拉榭拉",
    "露蕾": "鲁雷",
    "依欧娜萨尔": "依欧娜萨鲁",
    "卡诺依尔": "卡诺伊尔",
    "莱娜露露": "蕾娜露露",
    "库拉克特": "库拉肯特",
    "柯萨尔": "考扎尔",
    "利威尔特": "利维尔特",
    "涅普图尔": "尼普楚尔",
    "格雷科夫": "古雷柯夫",
    "纽罗基": "喵洛基", "尼罗基": "喵洛基", "纽洛基": "喵洛基",
    # ルビーグラス is a vegetable (grass), not glassware -- it is shredded,
    # blanched and rolled into cabbage rolls.
    "红宝石杯": "红宝石草", "红宝石玻璃": "红宝石草",
}


def main(argv):
    exportdir = argv[1]
    dry = "--dry" in argv
    hits = collections.Counter()
    where = collections.defaultdict(list)
    for root, _, files in os.walk(exportdir):
        for fn in sorted(files):
            if not fn.endswith(".csv") or fn.startswith("_"):
                continue
            p = os.path.join(root, fn)
            rel = os.path.relpath(p, exportdir).replace(os.sep, "/")
            with io.open(p, encoding="utf-8-sig", newline="") as f:
                rd = csv.DictReader(f)
                cols = rd.fieldnames
                rows = list(rd)
            if not cols or "zh" not in cols:
                continue
            changed = False
            for r in rows:
                z = r["zh"]
                if not z.strip():
                    continue
                new = z
                for bad, good in VARIANTS.items():
                    if bad in new:
                        hits[bad + " -> " + good] += new.count(bad)
                        where[bad].append("%s uid%s" % (rel, r["uid"]))
                        new = new.replace(bad, good)
                if new != z:
                    r["zh"] = new
                    changed = True
            if changed and not dry:
                with io.open(p, "w", encoding="utf-8-sig", newline="") as f:
                    cw = csv.DictWriter(f, fieldnames=cols, lineterminator="\r\n")
                    cw.writeheader()
                    cw.writerows(rows)
    if not hits:
        print("no name variants found -- everything already matches the official wording")
        return
    print("%s official names%s:" % ("would fix" if dry else "fixed", ""))
    for k, n in hits.most_common():
        bad = k.split(" -> ")[0]
        print("  %-28s x%-4d  e.g. %s" % (k, n, where[bad][0]))
        if len(where[bad]) > 1:
            print("      %d rows: %s%s" % (len(where[bad]), " ".join(where[bad][:6]),
                                           " ..." if len(where[bad]) > 6 else ""))


if __name__ == "__main__":
    main(sys.argv)
