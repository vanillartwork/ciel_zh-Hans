# -*- coding: utf-8 -*-
"""Force every translation in the export to real Simplified Chinese.

  py -3 normalize_cn.py <export dir> [--dry]

Three different things can pollute a Simplified patch, and only the first is
caught by an ordinary traditional/simplified check:

  1. Traditional characters   -- 詩 鷹 選 難 ...   fixed by zhconv
  2. Japanese shinjitai       -- 対 発 図 実 転 ...  zhconv leaves these alone
     because they are neither Traditional nor Simplified.  They render fine
     (the game font is Japanese) but read as typos in Chinese.
  3. Anything else outside GB2312 -- rare or variant characters that would
     also need new glyphs drawn for the font atlas.

This tool fixes 1 and 2, then reports 3 so you can decide.
"""
import sys, os, io, csv, collections

try:
    from zhconv import convert
except ImportError:                     # noqa: keep the hint on the exception
    raise ImportError(
        "normalize_cn needs zhconv:  py -3 -m pip install zhconv\n"
        "It is a maintainer tool. Building a patch does not need it -- the "
        "translations in data/ are already normalised.")

# Japanese shinjitai -> Simplified.  zhconv cannot do these.
JP_TO_CN = {
    "姫": "姬", "対": "对", "発": "发", "図": "图", "実": "实", "転": "转",
    "単": "单", "収": "收", "気": "气", "涙": "泪", "児": "儿", "帰": "归",
    "応": "应", "広": "广", "検": "检", "験": "验", "険": "险", "剣": "剑",
    "戦": "战", "経": "经", "続": "续", "読": "读", "楽": "乐", "薬": "药",
    "変": "变", "圧": "压", "増": "增", "徳": "德", "悪": "恶", "満": "满",
    "県": "县", "遅": "迟", "郷": "乡", "関": "关", "竜": "龙", "齢": "龄",
    "総": "总", "覚": "觉", "訳": "译", "権": "权", "様": "样", "撃": "击",
    "沢": "泽", "焼": "烧", "労": "劳", "売": "卖", "従": "从", "恵": "惠",
    "悩": "恼", "拡": "扩", "挙": "举", "捜": "搜", "掲": "揭", "揺": "摇",
    "摂": "摄", "桜": "樱", "毎": "每", "済": "济", "渇": "渴", "瀬": "濑",
    "猟": "猎", "畳": "叠", "絵": "绘", "縁": "缘", "繊": "纤", "聴": "听",
    "脳": "脑", "臓": "脏", "舎": "舍", "蔵": "藏", "蛍": "萤", "覧": "览",
    "観": "观", "譲": "让", "豊": "丰", "軽": "轻", "辺": "边", "醸": "酿",
    "銭": "钱", "隠": "隐", "雑": "杂", "髪": "发", "黙": "默",
    "効": "效", "勧": "劝", "壊": "坏", "奨": "奖", "択": "择", "拝": "拜",
    "拠": "据", "挿": "插", "晩": "晚", "歓": "欢", "歯": "齿", "涼": "凉",
    "渉": "涉", "犠": "牺", "焔": "焰", "巣": "巢", "帯": "带", "塩": "盐",
    "圏": "圈", "弐": "贰", "戸": "户", "桟": "栈", "陥": "陷", "隣": "邻",
    "頼": "赖", "顕": "显", "騒": "骚", "髄": "髓", "鶏": "鸡", "麗": "丽",
    "団": "团", "圏": "圈", "応": "应",
    "継": "继", "廃": "废", "亜": "亚", "逓": "递", "塁": "垒", "勲": "勋",
    "覇": "霸", "稲": "稻", "穏": "稳", "隷": "隶", "麺": "面", "鉱": "矿",
    "鋼": "钢", "銃": "铳", "嬢": "娘", "弾": "弹", "戯": "戏", "抜": "拔",
    "歩": "步", "砕": "碎", "窓": "窗", "粋": "粹", "縄": "绳",
}

# In GB2312, so the mechanical check cannot see them, but in a translation
# from Japanese they are almost always a leftover rather than a real word.
SUSPECT = {
    "芸": "艺?  (Japanese 芸 = 藝; Chinese 芸 only in 芸豆 / 芸香)",
    "机": "机?  (Japanese 机 = desk 桌; Chinese 机 = machine)",
    "娘": "娘?  (Japanese 娘 = daughter 女儿; Chinese 娘 = mother)",
    "湯": "汤?  (also caught as Traditional)",
}


# Punctuation that is not in GB2312, mapped to the GB2312 equivalent.
# GB2312 A1AA decodes to U+2015 HORIZONTAL BAR, not U+2014 EM DASH, and the
# Japanese source itself uses U+2015 (1407x) and U+2500 (1324x), never U+2014.
PUNCT_TO_CN = {
    "—": "―",     # EM DASH        -> HORIZONTAL BAR
    "−": "－",     # MINUS SIGN     -> FULLWIDTH HYPHEN-MINUS
}


def in_gb2312(ch):
    try:
        ch.encode("gb2312")
        return True
    except Exception:
        return False


# zhconv rewrites 么 as 幺 in zh-cn, which turns 什么 into 什幺.  Protect it.
_KEEP = chr(0x4E48)          # 么
_SENTINEL = chr(0xE000)      # private use, never in game text


def normalize(s):
    out = convert(s.replace(_KEEP, _SENTINEL), "zh-cn").replace(_SENTINEL, _KEEP)
    return "".join(PUNCT_TO_CN.get(c, JP_TO_CN.get(c, c)) for c in out)


def residual(s):
    """CJK characters still outside GB2312 after normalising."""
    return [c for c in s
            if ("\u3400" <= c <= "\u9fff" or "\uf900" <= c <= "\ufaff")
            and not in_gb2312(c)]


def main(argv):
    exportdir = argv[1]
    dry = "--dry" in argv
    changed_cells = 0
    fixed_chars = collections.Counter()
    left = collections.Counter()
    suspect = collections.Counter()
    where = {}
    for root, _, files in os.walk(exportdir):
        for fn in sorted(files):
            if not fn.endswith(".csv") or fn.startswith("_"):
                continue
            p = os.path.join(root, fn)
            with io.open(p, encoding="utf-8-sig", newline="") as f:
                rd = csv.DictReader(f)
                cols = rd.fieldnames
                rows = list(rd)
            if not cols or "zh" not in cols:
                continue
            hit = False
            for r in rows:
                old = r["zh"]
                if not old.strip():
                    continue
                new = normalize(old)
                if new != old:
                    for a, b in zip(old, new):
                        if a != b:
                            fixed_chars[a + "->" + b] += 1
                    r["zh"] = new
                    changed_cells += 1
                    hit = True
                for c in residual(r["zh"]):
                    left[c] += 1
                    where.setdefault(c, r.get("key") or r.get("uid"))
                for c in r["zh"]:
                    if c in SUSPECT:
                        suspect[c] += 1
            if hit and not dry:
                with io.open(p, "w", encoding="utf-8-sig", newline="") as f:
                    cw = csv.DictWriter(f, fieldnames=cols, lineterminator="\r\n")
                    cw.writeheader()
                    cw.writerows(rows)
    print("normalised %d cells%s" % (changed_cells, "  (dry run)" if dry else ""))
    if fixed_chars:
        top = fixed_chars.most_common(30)
        print("  fixes: " + "  ".join("%s x%d" % (k, v) for k, v in top))
    if left:
        print("  %d distinct characters are still outside GB2312 "
              "(check by hand, and they need new glyphs):" % len(left))
        for c, n in left.most_common(40):
            print("    %s  x%-5d first at %s" % (c, n, where[c]))
    else:
        print("  every translated character is inside GB2312")
    if suspect:
        print("  possible Japanese leftovers that GB2312 cannot catch:")
        for c, n in suspect.most_common():
            print("    %s x%-5d %s" % (c, n, SUSPECT[c]))


if __name__ == "__main__":
    main(sys.argv)
