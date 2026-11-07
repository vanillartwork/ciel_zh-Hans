# -*- coding: utf-8 -*-
"""Chinese for save summaries written before the patch, at display time only.

A save stores the summary text the game formatted when it was saved
(Documents/KoeiTecmo/CielnosurgeDX/SaveData, the header of each data*.bin),
and the load screen shows that stored text.  Saves made with the original
executable therefore keep showing 試練編第一幕 / 友達 / 工作中 even after the
patch translates the strings the summary is built from (exe_sites.py).

The files are not touched.  The load screen hands each value to the widget
setter as one whole string -- confirmed in a stage-one trace: the slot line
arrives as 試練編第一幕読書中, the panel values as 試練編第一幕 and 友達 --
so the display layer can replace them by exact match, like any other entry.

What may arrive is a closed set: one of twelve chapter names, one of the task
table's display names, one of three relationships, a chapter name followed
directly by a task name (the slot line), or a count of Sharls or cards (1体,
0枚; up to 999 is listed).  Every combination is listed here, at
build time, from the translations already reviewed for the executable; nothing
is split or guessed at run time.  A save written after the patch already
carries Chinese and matches none of these.
"""

CHAPTERS = [p + "編" + a for p in ("試練", "崩壊", "皇帝")
            for a in ("第一幕", "第二幕", "第三幕", "最終幕")]
# the task table at 0xc6c8e0 in steam-2025-07, in table order, duplicates removed
TASKS = ["睡眠中", "食事中", "飲料中", "空腹我慢中", "渇き我慢中", "献立思考中",
         "着替え中", "料理中", "材料調達中", "外出中", "工作中", "知人宅来訪中",
         "外出だるい", "起床", "調合査定中", "掃除中", "風呂中", "シャワー中",
         "手洗い中", "着替え思考中", "お片付け", "読書中", "書き物", "お昼寝中",
         "ぼー…", "髪型変更", "取り出し中", "運搬中", "端末移動中"]
RELATIONS = ["夫婦", "恋人", "友達"]
# the two counted values in the panel, "1体" and "0枚", formatted from these
COUNTERS = ["%d体", "%d枚"]
COUNT_RANGE = range(1000)


class OldSaveError(Exception):
    pass


def pairs(zh_for):
    """[(jp, zh)] whole-text entries.  `zh_for(jp)` returns the reviewed
    translation or None; an untranslated part keeps its Japanese."""
    def tr(jp):
        return zh_for(jp) or jp

    out = {}
    for jp in CHAPTERS + TASKS + RELATIONS:
        out[jp] = tr(jp)
    for c in CHAPTERS:
        for t in TASKS:
            jp = c + t
            if jp in out:
                raise OldSaveError("%r is both a part and a combination" % jp)
            out[jp] = tr(c) + tr(t)
    for fmt in COUNTERS:
        zh = zh_for(fmt)
        if not zh:
            continue
        for n in COUNT_RANGE:
            jp = fmt.replace("%d", str(n))
            if jp in out:
                raise OldSaveError("%r is listed twice" % jp)
            out[jp] = zh.replace("%d", str(n))
    return [(jp, zh) for jp, zh in sorted(out.items()) if zh != jp]


def from_exe_texts(texts):
    """pairs() over exe_sites.load_texts()'s {id: (jp, zh)}."""
    by_jp = {jp: zh for jp, zh in texts.values() if zh}
    return pairs(by_jp.get)
