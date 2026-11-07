# -*- coding: utf-8 -*-
"""Self-test for gbd_text.py on synthetic records.

  py -3 tools/selftest_gbd_text.py
"""
import io, os, shutil, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gbd_text as G                    # noqa: E402

failures = []


def ok(cond, what):
    print("  %-52s %s" % (what, "ok" if cond else "失败"))
    if not cond:
        failures.append(what)


AREA = "inc/dream/dream_area_data_01.gbd"
HIST = "inc/dream/event_history_data_01.gbd"


def area_record(i, name, title, leftover=b""):
    r = bytearray(304)
    r[0:4] = i.to_bytes(4, "little")
    r[4:4 + len(name)] = name.encode()
    t = title.encode("utf-8")
    r[28:28 + len(t)] = t
    # whatever an earlier, longer title left behind after the NUL
    r[28 + len(t) + 1:28 + len(t) + 1 + len(leftover)] = leftover
    r[108:124] = b"ruin_area01_ruru"
    return bytes(r)


def hist_record(name, title, summary, event=b"ME01_00H"):
    r = bytearray(844)
    r[4:4 + len(name)] = name.encode()
    r[104:104 + len(title.encode())] = title.encode("utf-8")
    r[160:160 + len(event)] = event
    s = summary.encode("utf-8")
    r[244:244 + len(s)] = s
    return bytes(r)


def trans(*pairs):
    """{key: (jp, zh)} the way load() returns it."""
    out = {}
    for short, field, jp, zh in pairs:
        out[G.text_key(short, field, jp)] = (jp, zh)
    return out


leftover = "イへ".encode("utf-8")
area = area_record(1, "area01", "試練編第一幕：始まりの刻", leftover) + \
    area_record(2, "area02", "試練編第二幕：天地咆吼")
T = "試練編第一幕：始まりの刻"

f = list(G.fields(AREA, area))
ok([x[1:] for x in f] == [("title", "area01", T), ("title", "area02", "試練編第二幕：天地咆吼")],
   "按记录名找到两个标题")
ok(list(G.fields("inc/dream/ruin_control_data_01.gbd", area)) == [],
   "未列入的文件类别：什么都不取")

ok(G.patch_member(AREA, area, {}) is area, "没有译文：原样返回")

new = G.patch_member(AREA, area, trans(("area", "title", T, "试炼篇第一幕：初始时刻")))
jb = T.encode("utf-8")
zb = "试炼篇第一幕：初始时刻".encode("utf-8")
ok(new[28:28 + len(zb)] == zb, "中文写在标题字段起点")
ok(new[28 + len(zb):28 + len(jb)] == bytes(len(jb) - len(zb)), "补零到日文原长")
ok(new[28 + len(jb)] == 0, "原来的结束 NUL 仍在")
ok(new[28 + len(jb) + 1:28 + len(jb) + 1 + len(leftover)] == leftover,
   "NUL 之后的残留字节不动")
diff = [i for i, (a, b) in enumerate(zip(area, new)) if a != b]
ok(diff and min(diff) >= 28 and max(diff) < 28 + len(jb), "所有改动都在标题原文范围内")
ok(new[304:] == area[304:], "第二条记录不变")
ok(new[4:10] == b"area01" and new[108:124] == b"ruin_area01_ruru", "记录名与废墟编号不变")

long_zh = "试炼篇第一幕：初始时刻的开始之前的故事"
try:
    G.patch_member(AREA, area, trans(("area", "title", T, long_zh)))
    ok(False, "译文比日文长：拒绝")
except G.GbdError as e:
    ok("bytes of Chinese" in str(e), "译文比日文长：拒绝")
try:
    G.patch_member(AREA, area, {G.text_key("area", "title", T): ("別の文", "别的")})
    ok(False, "行里的日文与文件不符：拒绝")
except G.GbdError as e:
    ok("not the text" in str(e), "行里的日文与文件不符：拒绝")
try:
    G.patch_member(AREA, area[:300], {})
    list(G.fields(AREA, area[:300]))
    ok(False, "文件长度不是整条记录：拒绝")
except G.GbdError:
    ok(True, "文件长度不是整条记录：拒绝")

hist = hist_record("history000", T, T)
t2 = trans(("history", "summary", T, "概要译法"))
new = G.patch_member(HIST, hist, t2)
ok(new[104:104 + len(jb)] == jb, "同文不同字段：标题保留日文")
ok(new[244:244 + len("概要译法".encode())] == "概要译法".encode(), "同文不同字段：概要用自己的译文")
ok(new[160:168] == b"ME01_00H", "事件编号不变")

spans = G.authorised_spans(HIST, hist, t2)
ok(all(any(lo <= i < hi for lo, hi in spans)
       for i, (a, b) in enumerate(zip(hist, new)) if a != b), "授权范围之外没有改动")



RUIN = "inc/dream/ruin_data_01.gbd"


def ruin_record(rid, name, reading, leftover=b""):
    r = bytearray(352)
    r[4:10] = b"area01"
    r[28:28 + len(rid)] = rid.encode()
    n = name.encode("utf-8")
    r[84:84 + len(n)] = n
    g = reading.encode("utf-8")
    r[140:140 + len(g)] = g
    r[140 + len(g) + 1:140 + len(g) + 1 + len(leftover)] = leftover
    r[220:224] = b"\x01\x02\x03\x04"
    return bytes(r)


reading = "ざっかや　るる　まえ"
ruin = ruin_record("ruin_area01_ruru", "雑貨屋縷縷前", reading, "・えっけんのま".encode("utf-8"))
new = G.patch_member(RUIN, ruin, {})
g = reading.encode("utf-8")
ok(new[140:140 + len(g)] == bytes(len(g)), "废墟读音：没有译文也一律清空")
ok(new[140 + len(g) + 1:] == ruin[140 + len(g) + 1:], "废墟读音：清空只动原读音的字节，残留与数值不变")
ok(new[28:44] == b"ruin_area01_ruru" and new[84:102] == ruin[84:102],
   "废墟读音：编号与地点名不受影响")
new = G.patch_member(RUIN, ruin, trans(("ruin", "name", "雑貨屋縷縷前", "缕缕杂货店前")))
zn = "缕缕杂货店前".encode("utf-8")
ok(new[84:84 + len(zn)] == zn and new[140] == 0, "废墟：地点名译文与读音清空同时生效")
spans = G.authorised_spans(RUIN, ruin, trans(("ruin", "name", "雑貨屋縷縷前", "缕缕杂货店前")))
ok(all(any(lo <= i < hi for lo, hi in spans)
       for i, (a, b) in enumerate(zip(ruin, new)) if a != b), "废墟：所有改动都在授权范围内")
ok([x[1:3] for x in G.fields(RUIN, ruin)] == [("name", "ruin_area01_ruru")],
   "废墟：读音不进翻译表，记录按废墟编号命名")


class FakePak:
    def __init__(self, files):
        self.files = files

    def __iter__(self):
        class E:
            pass
        for p in self.files:
            e = E()
            e.path = p
            yield e

    def read(self, p):
        return self.files[p if isinstance(p, str) else p.path]


pak = FakePak({AREA: area, "inc/dream/dream_area_data_02.gbd": area, HIST: hist})
tmp = tempfile.mkdtemp()
try:
    path, n = G.export(pak, tmp)
    ok(n == 4, "导出：4 种不同文字")
    rows = io.open(path, encoding="utf-8-sig").read()
    ok(",2," in rows, "导出：重复的标题记 2 个落点")
    with io.open(path, "w", encoding="utf-8-sig", newline="") as f:
        f.write("key,jp,zh,max_bytes,landings,src,note\r\n%s,%s,%s,37,2,x,\r\n"
                % (G.text_key("area", "title", T), T, "试炼篇第一幕：初始时刻"))
    out = G.build(pak, path)
    ok(sorted(out) == [AREA, "inc/dream/dream_area_data_02.gbd"],
       "构建：只改含该标题的两个文件")
    problems, changed = G.verify(pak, path)
    ok(not problems and changed > 0, "核验：改动全部落在授权字段内")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print()
print("%d 项未通过" % len(failures) if failures else "全部自检通过")
sys.exit(1 if failures else 0)
