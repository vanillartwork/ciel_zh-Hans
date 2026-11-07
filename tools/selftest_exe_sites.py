# -*- coding: utf-8 -*-
"""Self-test for exe_sites.py and the global pass in patch_exe_strings.py.

  py -3 tools/selftest_exe_sites.py

No game needed: the "executable" is a byte buffer and every RVA is its own
file offset in a section called .rdata.
"""
import io, os, shutil, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import exe_sites as X                   # noqa: E402
import patch_exe_strings as P           # noqa: E402

failures = []


def ok(cond, what):
    print("  %-52s %s" % (what, "ok" if cond else "失败"))
    if not cond:
        failures.append(what)


def raises(fn, what, needle=None):
    try:
        fn()
    except X.SiteError as e:
        ok(needle is None or needle in str(e), what)
        return
    ok(False, what + " (nothing raised)")


def locate(rva, n, size=None, sec=".rdata"):
    return rva, sec


def image(*strings):
    """NUL-separated strings; returns (bytes, {text: [offsets]})."""
    d, where = bytearray(b"\0" * 16), {}
    for s in strings:
        where.setdefault(s, []).append(len(d))
        d += s.encode("utf-8") + b"\0" * 7
    return bytes(d), where


def site(jp, rva, use="display"):
    jb = jp.encode("utf-8")
    return dict(id=X.text_id(jp), rva=rva, bytes=len(jb),
                sha256=X.short_hash(jb), use=use, evidence="test")


def texts(*pairs):
    return {X.text_id(jp): (jp, zh) for jp, zh in pairs}


data, at = image("イオン", "イオン")
label, key = at["イオン"]
w = X.plan(data, [site("イオン", label)], texts(("イオン", "依恩")), locate)
out = X.apply(data, w)
ok(out[key:key + 10] == data[key:key + 10], "同文两份：未授权的键逐字节不变")
ok(out[label:label + 9] == "依恩".encode("utf-8") + b"\0\0\0", "同文两份：授权的标签改为「依恩」并补零")
ok(len(out) == len(data), "文件大小不变")
ok(sum(a != b for a, b in zip(out, data)) <= 9, "标签 9 字节之外没有任何改动")

w = X.plan(data, [], texts(("イオン", "依恩")), locate)
ok(X.apply(data, w) == data, "只有译文没有清单行：不写")

w = X.plan(data, [site("イオン", label)], texts(("イオン", "")), locate)
ok(w == [] and X.apply(data, w) == data, "清单行没有译文：核对但不写")

data2, at2 = image("友達", "恋人")
raises(lambda: X.plan(data2, [dict(site("友達", at2["友達"][0]), rva=at2["恋人"][0])],
                      texts(("友達", "朋友")), locate),
       "地址上不是审核过的日文：拒绝", "not the reviewed")
raises(lambda: X.plan(data2, [dict(site("友達", at2["友達"][0]), rva=at2["友達"][0] + 3)],
                      texts(("友達", "朋友")), locate),
       "地址落在字符串中间：拒绝", "not the reviewed")
raises(lambda: X.plan(data2, [site("友達", at2["友達"][0])], texts(("友達", "好朋友")), locate),
       "译文超长：拒绝", "available")
raises(lambda: X.plan(data2, [site("友達", at2["友達"][0])], texts(("友達", "朋友")),
                      lambda rva, n: (rva, ".text")),
       "不在 .rdata：拒绝", "not .rdata")
raises(lambda: X.plan(data2, [dict(site("友達", at2["友達"][0]), sha256="0" * 16)],
                      texts(("友達", "朋友")), locate),
       "原文摘要不符：拒绝", "sha256")
raises(lambda: X.plan(data2, [site("友達", at2["友達"][0])], {}, locate),
       "清单行找不到译文：拒绝", "no translation")
raises(lambda: X.plan(data2, [site("友達", at2["友達"][0]), site("友達", at2["友達"][0])],
                      texts(("友達", "朋友")), locate),
       "同一地址两行：报重叠", "overlap")

fmt = "第%sの扉"
data3, at3 = image(fmt)
s3 = site(fmt, at3[fmt][0])
for zh, good, what in [("第%s扇门", True, "保留同一个 %s"),
                       ("第%d扇门", False, "%s 改成 %d"),
                       ("%s%s门", False, "多一个转换"),
                       ("第扇门", False, "少一个转换"),
                       ("第%%s门", False, "%% 是字面量，不算 %s"),
                       ("第%扇门", False, "孤立的 %")]:
    if good:
        X.plan(data3, [s3], texts((fmt, zh)), locate)
        ok(True, "格式串：" + what + "，接受")
    else:
        raises(lambda: X.plan(data3, [s3], texts((fmt, zh)), locate), "格式串：" + what + "，拒绝")
two = "%sを%dPt."
data4, at4 = image(two)
raises(lambda: X.plan(data4, [site(two, at4[two][0])], texts((two, "%d点%s")), locate),
       "格式串：转换顺序调换，拒绝")
data5, at5 = image("試練編第一幕")
raises(lambda: X.plan(data5, [site("試練編第一幕", at5["試練編第一幕"][0])],
                      texts(("試練編第一幕", "100%完成")), locate),
       "被当作格式串的文字：译文不得新增 %")

summ = "\n現在：%s\n関係：%s"
data6, at6 = image(summ)
s6 = site(summ, at6[summ][0], use="persisted")
X.plan(data6, [s6], texts((summ, "\n当前：%s\n关系：%s")), locate)
ok(True, "写入存档的文字：行数与全角冒号一致，接受")
raises(lambda: X.plan(data6, [s6], texts((summ, "\n当前:%s\n关系：%s")), locate),
       "写入存档的文字：改成半角冒号，拒绝", "：")
raises(lambda: X.plan(data6, [s6], texts((summ, "当前：%s 关系：%s")), locate),
       "写入存档的文字：少了换行，拒绝")
data7, at7 = image("工作中")
raises(lambda: X.plan(data7, [site("工作中", at7["工作中"][0], use="persisted")],
                      texts(("工作中", "做 手工")), locate),
       "写入存档的值：含空格（存档栏按空格切），拒绝", "' '")

w = X.plan(data, [site("イオン", label)], texts(("イオン", "依恩")), locate)
clobbered = bytearray(data)
clobbered[label:label + 3] = b"XXX"
raises(lambda: X.apply(bytes(clobbered), w), "全局写回已改动授权地址：按地址写回拒绝", "changed before")

g, gat = image("あいう", "かき")
todo = [("a", "あいう", "かき", 9), ("b", "かき", "XY", 6)]
out, done, miss, total = P.patch(g, todo, verbose=False)
o1, o2 = gat["あいう"][0], gat["かき"][0]
ok(out[o1:o1 + 6] == "かき".encode("utf-8"), "全局写回：前一条译文不被后一条再替换")
ok(out[o2:o2 + 2] == b"XY", "全局写回：真正的那条照常替换")
ok(total == 2, "全局写回：恰好两处改写")

n, problems = X.check_repo()
for p in problems:
    print("     " + p)
ok(not problems, "仓库里的 %d 个地址与译文数据一致" % n)

tmp = tempfile.mkdtemp()
try:
    os.makedirs(os.path.join(tmp, "zh-Hans"))
    os.makedirs(os.path.join(tmp, "exe-sites"))
    with io.open(os.path.join(tmp, "zh-Hans", "exe_sited.csv"), "w", encoding="utf-8") as f:
        f.write("id,jp,zh,status,max_bytes,note\n%s,友達,好朋友们,translated,6,\n"
                % X.text_id("友達"))
    with io.open(os.path.join(tmp, "exe-sites", "v.csv"), "w", encoding="utf-8") as f:
        f.write(",".join(X.COLS) + "\n%s,c33a78,6,%s,display,test\n"
                % (X.text_id("友達"), X.short_hash("友達".encode("utf-8"))))
    n, problems = X.check_repo(tmp)
    ok(any("available" in p for p in problems), "仓库核对：报告放不下的译文")
    with io.open(os.path.join(tmp, "game-versions.csv"), "w", encoding="utf-8") as f:
        f.write("version_id,label,platform,file,bytes,sha256,status,note\n"
                "v,x,x,CielnosurgeDX.exe,1,ABCD,supported,\n")
    ok(X.manifest_for("abcd", os.path.join(tmp, "game-versions.csv"),
                      os.path.join(tmp, "exe-sites")).endswith("v.csv"),
       "按原版主程序摘要选清单")
    ok(X.manifest_for("ef01", os.path.join(tmp, "game-versions.csv"),
                      os.path.join(tmp, "exe-sites")) is None,
       "未知主程序：没有清单")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

import old_saves as O                   # noqa: E402
zh = {"試練編第一幕": "试炼篇第一幕", "読書中": "读书中", "友達": "朋友"}
pairs = dict(O.pairs(zh.get))
ok(pairs.get("試練編第一幕読書中") == "试炼篇第一幕读书中", "旧存档：章节名＋状态名整句映射")
ok(pairs.get("試練編第一幕外出中") == "试炼篇第一幕外出中", "旧存档：未翻译的部分保留原文")
ok("外出中" not in pairs and "恋人" not in pairs, "旧存档：中日相同的不收")
ok(pairs.get("友達") == "朋友", "旧存档：单独的值也收")
ok(len(set(pairs)) == len(pairs) and all("\n" not in j for j in pairs), "旧存档：键唯一、无换行")
real = dict(O.from_exe_texts(X.load_texts()))
ok(real.get("試練編第一幕工作中") == "试炼篇第一幕制作中", "旧存档：用仓库里审核过的译文生成")
ok(real.get("1体") == "1只" and real.get("0枚") == "0张" and real.get("999体") == "999只",
   "旧存档：夏尔数与卡片数按格式串译法生成")
ok(dict(O.pairs({}.get)).get("1体") is None, "旧存档：计数格式串没有译文时不生成")

print()
print("%d 项未通过" % len(failures) if failures else "全部自检通过")
sys.exit(1 if failures else 0)
