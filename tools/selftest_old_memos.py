# -*- coding: utf-8 -*-
"""Self-test for old_memos.py.

  py -3 tools/selftest_old_memos.py
"""
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import old_memos as M                   # noqa: E402

failures = []


def check(name, cond):
    print("  %-52s %s" % (name, "ok" if cond else "失败"))
    if not cond:
        failures.append(name)


long_zh = "面对自己不太拿手的裁缝。\n因为有你在旁边守护着，\n我也能竭尽全力做好了♪"   # 104 bytes
check("按字符边界截断：92 字节截掉「做好了♪」",
      M.cut(long_zh, 92) == "面对自己不太拿手的裁缝。\n因为有你在旁边守护着，\n我也能竭尽全力")
check("按字符边界截断：不足上限的原样返回", M.cut("短", 92) == "短")
check("按字符边界截断：不留半个字符", all(M.cut(long_zh, n).encode("utf-8") == long_zh.encode("utf-8")[:len(M.cut(long_zh, n).encode("utf-8"))]
                                     for n in (92, 93, 94)))

now = [("裁縫の日本語", "不太拿手的裁缝，\n我也尽力做好了♪"),
       ("改行\r\nあり", "换行"),
       ("同じ頭Ａ", "甲"), ("同じ頭Ｂ", "乙")]
hist = [("裁縫の日本語", long_zh)]
d = dict(M.pairs(now, hist))
check("旧版完整中文 → 当前译文", d.get(long_zh) == "不太拿手的裁缝，\n我也尽力做好了♪")
check("旧版中文的截断版 → 当前译文", d.get(M.cut(long_zh, 92)) == "不太拿手的裁缝，\n我也尽力做好了♪")
check("当前译文本身不重复收录", "不太拿手的裁缝，\n我也尽力做好了♪" not in d)
check("完整日文不重复收录（由备忘来源负责）", "裁縫の日本語" not in d)

# two memos whose stored texts cut to the same prefix
a = "共" * 31 + "Ａ"
b = "共" * 31 + "Ｂ"
d2 = dict(M.pairs([("Ａ", "甲"), ("Ｂ", "乙")], [("Ａ", a), ("Ｂ", b)]))
check("两条备忘截成同一前缀：不收", M.cut(a, 92) not in d2 and M.cut(a, 92) == M.cut(b, 92))
check("……但各自的完整旧文仍收", d2.get(a) == "甲" and d2.get(b) == "乙")

# a cut that is the whole of another memo
whole = "共" * 30 + "。"                                                  # 93 bytes
longer = whole + "续写"
d3 = dict(M.pairs([("短い方", whole), ("長い方", "长")], [("長い方", longer)]))
check("截断后恰好是另一条完整备忘：不收", d3.get(whole) is None)

jp_long = "あ" * 31 + "。"                                                 # 96 bytes
d4 = dict(M.pairs([(jp_long, "长的日文备忘")], []))
check("原版日文超长被截：截断版 → 当前译文", d4.get(M.cut(jp_long, 92)) == "长的日文备忘")

d5 = dict(M.pairs([("同じ", "甲"), ("同じ", "乙")], [("同じ", "旧")]))
check("同一日文有两种当前译文：不猜", "旧" not in d5)

print()
print("%d 项未通过" % len(failures) if failures else "全部自检通过")
sys.exit(1 if failures else 0)
