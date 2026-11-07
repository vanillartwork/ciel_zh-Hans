# -*- coding: utf-8 -*-
# Regenerate data/zh-Hans/exe_sited.csv and data/exe-sites/steam-2025-07.csv.
#   py -3 tools/dev/gen_exe_sites.py <repo>
# Needs the original executable (Backup/CielnosurgeDX.exe, see dis_readers.EXE).
# The reviewed list below is the evidence: every reference to each string is
# recomputed from the executable and must equal the set its evidence covers.
import sys, os, io, csv, hashlib
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dis_readers import PE, EXE, BASE
REPO = sys.argv[1]
sys.path.insert(0, os.path.join(REPO, "tools"))
from repo_export import src_hash, ctl_shape
pe = PE(EXE)
t = [s for s in pe.secs if s[0] == ".text"][0]; _n, TVA, _s, TRAW, TRS = t
code = np.frombuffer(pe.d[TRAW:TRAW + TRS], dtype=np.uint8); n = len(code) - 4
disp = (code[:n].astype(np.int64) | (code[1:n+1].astype(np.int64) << 8) |
        (code[2:n+2].astype(np.int64) << 16) | (code[3:n+3].astype(np.int64) << 24))
disp = np.where(disp >= 1 << 31, disp - (1 << 32), disp)
tgt = TVA + np.arange(n) + 4 + disp
modok = (code[np.arange(n) - 1] & 0xC7) == 0x05
datas = [(nm, sva, np.frombuffer(pe.d[raw:raw + rs // 8 * 8], dtype=np.uint64))
         for nm, sva, sz, raw, rs in pe.secs if nm != ".text"]


def refs(rva, L):
    """(code sites, functions, data pointer slots) reaching [rva, rva+L]."""
    hits = np.nonzero(modok & (tgt >= rva) & (tgt <= rva + L))[0]
    sites = sorted(TVA + int(i) for i in hits)
    funcs = sorted(set(pe.func(s)[0] for s in sites if pe.func(s)))
    d = []
    for nm, sva, a in datas:
        d += [sva + 8 * int(j) for j in np.nonzero((a >= BASE + rva) & (a <= BASE + rva + L))[0]]
    return sites, funcs, sorted(d)


def rva_of(text):
    b = text.encode("utf-8") + b"\0"; found = []; k = 0
    while True:
        k = pe.d.find(b, k)
        if k < 0:
            break
        if pe.d[k - 1] == 0:
            for nm, va, sz, raw, rs in pe.secs:
                if raw <= k < raw + rs:
                    found.append(va + k - raw)
        k += 1
    return found


def tid(jp):
    return "exe:" + hashlib.sha1(jp.encode()).hexdigest()[:8]


TASK = (0xc6c8e0, 0xc6dab0)
DEBUG = (0x10604d0, 0x10605a8)
E_DIALOG = "格式化后作为对话框正文：0x7cda30 把第 4 个参数交给 text_message 的设字函数 0x7cc920"
E_SET = "直接交给界面设字函数 0x7cc920（内部调用 ACSpriteText 的 setter）"
NOTE_SAVED = "只供显示层：这段文字会写进存档，主程序保留原文，见 tools/old_saves.py"
E_FMTONLY = ("本地址的每一处引用都只是 snprintf/sprintf 的格式参数，原文本身不被比较或查找；"
             "转换序列相同且字节不增，格式化结果不会比原版长。")
E_QUEUE = (E_FMTONLY + "格式化结果经 std::string 放进弹窗消息队列（+0x2720，经 0x5af8d0；"
           "与已在实机确认上屏的勋章提示同一队列）")
E_LIST = (E_FMTONLY + "格式化结果与命令编号 0x1b 一起构造成列表项（0x5d0bf0，文本在 +0x40），"
          "由 0x5f0880/0x5f1900 加入列表，命令按编号分派")
E_TASK = ("任务表 0xc6c8e0（30 条，步长 0x98）的显示名字段；该表按数字编号建映射（0x759a60），"
          "按名查任务 0x75a490 比较的是英文 TASK_* 标签；显示名仅作 sprintf_s 格式串写入存档摘要（0x4cc117）")
E_TASK_DBG = E_TASK + "；另被调试状态名表 0x10604d0 指向，该表无代码引用"
E_CHAP = ("章节名：0x4ca520 以内联 SSE 拷贝建「事件编号 ME01_00 → 章节名」局部表，"
          "按事件编号查找，章节名只作 sprintf_s 格式串输出到存档摘要")
E_REL = "0x4cacc0 按存档标志 EF_LOVER/EF_MARRIAGE 选出一个，作 sprintf_s 格式串写入存档摘要"
E_SUMMARY = ("存档摘要格式串：0x4cbd90 用 snprintf 写入存档头；读档界面 0x4d1ce0 按换行取第 2/3/4 行、"
             "按全角「：」切开取值，不比较标签文字")

# (jp, zh or None to reuse executable.csv, use, expected functions or None for
#  "any number of direct setter calls" checked by `ncode`, data ranges, evidence)
ROWS = [
    ("%s<CR>に移動しますか？", "%s<CR>要前往该处吗？", "display", 1, [],
     "0x509148 sprintf 后，" + E_DIALOG),
    ("第%sの扉", "第%s扇门", "display", 0, [(0x1069d40, 0x1069d48)],
     "数据指针 0x1069d40 仅由 0x53ca36 读取：snprintf(buf,0x100,fmt,全角数字) 后交给 name_text 的设字函数 0x7cc920"),
    ("この扉に入りますか？<CR>【 %s 】", "要进入这扇门吗？<CR>【 %s 】", "display", 1, [],
     "0x53c431 snprintf(buf,0x100) 后，" + E_DIALOG),
    ("%sを修復しました", "已修复%s", "display", 2, [], "两处均为 sprintf 后交给设字函数 0x7cc920"),
    ("【%s】の回答", "【%s】的回答", "display", 1, [], "snprintf(buf,0x601) 后交给设字函数 0x7cc920"),
    ("■ シャール『%s』の応募状況 ■", "■ 夏尔『%s』的应征状况 ■", "display", 1, [],
     "snprintf(buf,0x601) 后交给设字函数 0x7cc920"),
    ("協力申請可能人数       %d", "可申请协助人数       %d", "display", 2, [],
     "两处均为 snprintf 后交给设字函数 0x7cc920"),
    ("無回答", "未回答", "display", 1, [],
     "作 snprintf 格式串写入与「【%s】の回答」同一缓冲区，随后在 0x5fe95d 交给设字函数 0x7cc920"),
    ("調合結果", "调合结果", "display", 1, [], E_SET),
    ("採取結果", "采集结果", "display", 1, [], E_SET),
    ("所持HymP", "持有HymP", "display", 14, [], "14 处均直接交给设字函数 0x7cc920"),
    ("未取得", "未获得", "display", 1, [], E_SET),
    ("MyGustID紹介", "MyGustID介绍", "display", 1, [], E_SET),
    ("修正", "修改", "display", 1, [],
     "对话框 0x7ce5e0 的第 4 个参数，即「否」按钮文字，经 0x7cc800 设到 button_no"),
    ("\n総プレイ時間：%s\n現在のイオン：%s\nあなたとの関係：%s\n夢セカイ進行状況：%s\nラブラブ：%s\nシャール保有数：%s\n仮想世界カード：%s",
     "\n总游玩时间：%s\n当前的依恩：%s\n与你的关系：%s\n梦世界进展情况：%s\n亲亲密密：%s\n夏尔持有数：%s\n虚拟世界卡片：%s",
     "saved", 1, [], E_SUMMARY),
    ("勲章\n【%s】\nを手に入れました！", "勋章\n【%s】\n已获得！", "display", 1, [],
     "0x575b05 snprintf(buf,0x100) 后存入勋章消息队列（+0x2430，std::string），之后弹窗经设字函数 "
     "0x7cc920 显示（实机记录 2026-11-02 确认上屏）；比较的对象只可能是格式化后的整句，不是本格式串"),
    ("契約のために\n%dHymP消費しますか？", "签订契约\n需要消耗%dHymP，确定吗？", "display", 1, [],
     "0x5b36cd snprintf(buf,0x100) 后，" + E_DIALOG),
    ("時間 / HymPレート ＝ %d分 / 1HymP.", "时间 / HymP比率 ＝ %d分 / 1HymP.", "display", 1, [],
     "0x42dcbb sprintf 后在 0x42dccb 交给设字函数 0x7cc920"),
    ("\n%sの修復が完了しました！", "\n%s的修复已完成！", "display", 1, [], "0x50cdf7 sprintf 后，" + E_DIALOG),
    ("\n%sの修復が完了しました。\nHymP%dPt.ゲット\n【%s】は\nシンクロ率%d％上昇、EXP%dPt.ゲット",
     "\n%s的修复已完成。\n获得HymP%dPt.\n【%s】\n同步率上升%d％，获得EXP%dPt.", "display", 1, [],
     "0x50d2bd sprintf 后，" + E_DIALOG),
    ("\n%sの修復が完了しました。\nHymP%dPt.ゲット\n【%s】は\nシンクロ率%d％上昇、EXP%dPt.ゲット\n【%s】は\nシンクロ率%d％上昇、EXP%dPt.ゲット",
     "\n%s的修复已完成。\n获得HymP%dPt.\n【%s】\n同步率上升%d％，获得EXP%dPt.\n【%s】\n同步率上升%d％，获得EXP%dPt.",
     "display", 1, [], "0x50d322 sprintf 后，" + E_DIALOG),
    ("%s<CR> の採取", "%s<CR>的采集", "display", 1, [], "0x52aabd sprintf 后在 0x52aaf3 交给设字函数 0x7cc920"),
    ("%s<CR> の作成", "%s<CR>的制作", "display", 1, [], "0x52aabd sprintf 后在 0x52aaf3 交给设字函数 0x7cc920"),
    ("%sを修復中です", "正在修复%s", "display", 2, [], "两处均为 sprintf 后交给设字函数 0x7cc920"),
    ("%dHymPを入手しました。\nシンクロ率が少し上昇しました。\nシャールのLPが%d回復しました。",
     "获得了%dHymP。\n同步率稍微上升了。\n夏尔的LP恢复了%d。", "display", 3, [],
     "三处均为 snprintf 后，" + E_DIALOG),
    ("シャール『%s』が\nLV%dになりました！", "夏尔『%s』\n升到了LV%d！", "display", 3, [], E_QUEUE),
    ("装備品が追加されました。\nシャール「%s」のシンクロ率が\n%d%%アップしました！",
     "已追加装备品。\n夏尔「%s」的同步率\n提升了%d%%！", "display", 1, [], "0x584495 snprintf 后，" + E_DIALOG),
    ("今までシャールが取得した\nExpの半分、%dHymPが\n戻って来ます。\n本当にお別れしますか？ ",
     "这只夏尔至今获得的\nExp的一半，即%dHymP\n将会返还。\n真的要告别吗？ ", "display", 1, [],
     "0x58594b snprintf 后，" + E_DIALOG),
    ("シャールから%dmag.の\nエネルギーが送信されました。", "夏尔传送了%dmag.的\n能量。", "display", 1, [], E_QUEUE),
    ("エネルギー送信により\n%dHymPを入手しました。", "通过能量传送\n获得了%dHymP。", "display", 1, [], E_QUEUE),
    ("%sさんの巣", "%s之巢", "display", 3, [], E_QUEUE + "；其中 0x595c4c 一处经局部 std::string 交给设字函数"),
    ("この装備品を\n%dHymP投入して入手しますか？", "这件装备品\n要投入%dHymP获得吗？", "display", 1, [],
     "0x5b3489 snprintf 后，" + E_DIALOG),
    ("このスキルを\n%dHymP投入して入手しますか？", "这项技能\n要投入%dHymP获得吗？", "display", 1, [],
     "0x5b34fb snprintf 后，" + E_DIALOG),
    ("『%s』へのつぶやき", "对『%s』的碎碎念", "display", 2, [], E_LIST),
    ("『%s』の記事", "『%s』的文章", "display", 1, [], E_LIST),
    ("『%s』のフォロワー情報", "『%s』的粉丝信息", "display", 1, [], E_LIST),
    ("%sのすべてのメールを\n既読にしますか？", "要将%s的所有邮件\n标为已读吗？", "display", 1, [],
     "0x5f4501 snprintf 后，" + E_DIALOG),
    ("HymPを%dpt.消費して、『%c』で応募します。\nよろしいですか？", "将消耗%dpt.HymP，以『%c』应征。\n确定吗？",
     "display", 1, [], "0x5f61ff snprintf 后，" + E_DIALOG),
    ("%d日%d時間%d分", "%d天%d小时%d分", "persisted", 4, [],
     "四处均只作 snprintf 格式串：0x4cbd90 两处写入存档摘要与存档栏首段（读档界面按空格切分、不显示首段），"
     "0x4cb190 由个人资料页 0x5547c0 交给 info_totaltime 的设字函数，0x4cb100 无直接调用者"),
    ("%d体", "%d只", "saved", 2, [],
     "只作 snprintf 格式串：0x4cbd90 写入存档摘要（夏尔持有数），0x4cb0e0 由个人资料页 0x5547c0 调用"),
    ("%d枚", "%d张", "saved", 1, [],
     "只作 snprintf 格式串：0x4cb200 由存档摘要 0x4cbd90 与个人资料页 0x5547c0 调用（仮想世界カード）"),
    ("夫婦", "夫妇", "saved", 1, [], E_REL),
    ("友達", "朋友", "saved", 1, [], E_REL),
]
for a, b in [("試練", "试炼"), ("崩壊", "崩坏"), ("皇帝", "皇帝")]:
    for x, y in [("第一幕", "第一幕"), ("第二幕", "第二幕"), ("第三幕", "第三幕"), ("最終幕", "最终幕")]:
        ROWS.append((a + "編" + x, b + "篇" + y, "saved", "chapter", [], E_CHAP))
TASKS_NEW = [("食事中", "用餐中"), ("飲料中", "饮水中"), ("空腹我慢中", "忍耐饥饿中"),
             ("献立思考中", "思考菜单中"), ("料理中", "烹饪中"), ("材料調達中", "采购材料中"),
             ("工作中", "制作中"), ("知人宅来訪中", "拜访熟人中"), ("調合査定中", "调合评估中"),
             ("掃除中", "打扫中"), ("風呂中", "泡澡中"), ("読書中", "读书中"), ("髪型変更", "换发型"),
             ("運搬中", "搬运中"), ("端末移動中", "前往终端中")]
TASKS_OLD = ["渇き我慢中", "着替え中", "外出だるい", "シャワー中", "手洗い中", "着替え思考中",
             "お片付け", "書き物", "お昼寝中", "ぼー…", "取り出し中"]
for jp, zh in TASKS_NEW:
    dbg = jp in ("読書中", "料理中", "食事中")
    ROWS.append((jp, zh, "saved", 0, [TASK] + ([DEBUG] if dbg else []),
                 E_TASK_DBG if dbg else E_TASK))
for jp in TASKS_OLD:
    ROWS.append((jp, None, "saved", 0, [TASK], E_TASK))

exe_rows = {r["jp"]: r for r in csv.DictReader(
    io.open(os.path.join(REPO, "data/zh-Hans/executable.csv"), encoding="utf-8-sig"))}
sited, sites, bad = [], [], []
for jp, zh, use, ncode, ranges, ev in ROWS:
    L = len(jp.encode())
    cand = [(rva,) + refs(rva, L) for rva in rva_of(jp)]
    live = [x for x in cand if x[1] or x[3]]
    if len(live) != 1:
        bad.append("%r: %d referenced copies %s" % (jp, len(live),
                   [(hex(r), [hex(z) for z in s], [hex(z) for z in d]) for r, s, f, d in cand]))
        continue
    rva, csites, funcs, d = live[0]
    if ncode == "chapter":
        cok = funcs == [0x4ca520]
    else:
        cok = len(csites) == ncode
    dok = (all(any(lo <= p < hi for lo, hi in ranges) for p in d)
           and bool(d) == bool(ranges)
           and all(any(lo <= p < hi for p in d) for lo, hi in ranges[:1]))
    if not (dok and cok):
        bad.append("%r at %#x: code %s (funcs %s) data %s" % (
            jp.replace("\n", "|"), rva, [hex(z) for z in csites], [hex(z) for z in funcs],
            [hex(z) for z in d]))
        continue
    i = tid(jp)
    if zh is None:
        if jp not in exe_rows:
            bad.append("%r not in executable.csv" % jp)
            continue
        assert exe_rows[jp]["id"] == i, jp
    else:
        sited.append(dict(id=i, jp=jp, zh=zh, status="translated", max_bytes=L,
                          src=src_hash(jp), ctl=ctl_shape(jp),
                          note=NOTE_SAVED if use == "saved" else
                          "按地址写入，见 data/exe-sites/steam-2025-07.csv"))
    if use == "saved":
        # written into the save: the executable keeps the Japanese so that a
        # save made with the patch reads correctly in the original game, and
        # the display layer shows the Chinese (tools/old_saves.py)
        print("%-24s %#x  display layer only" % (jp.replace("\n", "|")[:24], rva))
        continue
    sites.append(dict(id=i, rva="%x" % rva, bytes=L,
                      sha256=hashlib.sha256(jp.encode()).hexdigest()[:16], use=use, evidence=ev))
    print("%-24s %#x  code=%d data=%d" % (jp.replace("\n", "|")[:24], rva, len(csites), len(d)))
for b in bad:
    print("PROBLEM", b)
if bad:
    sys.exit(1)
with io.open(os.path.join(REPO, "data/zh-Hans/exe_sited.csv"), "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["id", "jp", "zh", "status", "max_bytes", "src", "ctl", "note"],
                       lineterminator="\n")
    w.writeheader(); w.writerows(sited)
os.makedirs(os.path.join(REPO, "data/exe-sites"), exist_ok=True)
with io.open(os.path.join(REPO, "data/exe-sites/steam-2025-07.csv"), "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["id", "rva", "bytes", "sha256", "use", "evidence"],
                       lineterminator="\n")
    w.writeheader(); w.writerows(sites)
print("%d translations, %d sites" % (len(sited), len(sites)))
