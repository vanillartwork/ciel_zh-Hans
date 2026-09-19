# -*- coding: utf-8 -*-
"""Checks on the injection itself, run against a fake archive.

  py -3 selftest_inject.py

These exist because of a bug no validator could have caught: every translation
was correct and the patch still broke the game.  The event scripts carry, in
the same columns, both text to show and keys the engine looks things up by:

  * column 11 is the character key.  charanamemap.inc maps it to a model down
    to a trailing fullwidth space ("イオン" is the normal model, "イオン　" the
    chibi one), the row that places a character carries it, and every later row
    -- dialogue included -- uses it to say which placed character a line and
    its expression belong to.  It is also what the nameplate shows, which is
    what made translating it look safe.  It is not.
  * EVENT_PROCESS_CHANGE_DISPLAY_NAME takes the character key first and the
    label to show second.  Only the second may be translated.
  * ngword_data.bin is the blocked-word list, not display text.

Chinese nameplates come from inserting that same command instead, so this also
has to prove the insertion still happens: with no charanamemap in the fixture
the whole feature silently does nothing, and a suite that only guards the keys
passes just as happily with nameplates switched off.
"""
import sys, os, io, csv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import csvspan
import import_text
import nameplates
from export_text import SPEAKER_COL, DIALOG_COL, CMD_COL, CMD_TEXT

BOM = b"\xef\xbb\xbf"
RENAME = nameplates.RENAME


class FakeEntry:
    def __init__(self, path, data):
        self.path, self.data = path, data


class FakePak:
    """Just enough of Pak for import_text.build()."""

    def __init__(self, files):
        self.entries = [FakeEntry(p, d) for p, d in files.items()]

    def __iter__(self):
        return iter(self.entries)

    def get(self, path):
        for e in self.entries:
            if e.path == path:
                return e
        return None

    def read(self, e):
        return e.data


def row(cols):
    n = max(cols) + 1
    return ",".join(csvspan.quote(cols.get(i, "")) for i in range(n))


def main():
    failures = []

    def check(name, cond):
        print("  %-54s %s" % (name, "ok" if cond else "失败"))
        if not cond:
            failures.append(name)

    # A script covering every way column 11 appears, plus the rename command.
    lines = [
        # 0: header, the shape every event script starts with
        row({2: "event"}),
        # 1: places a character on stage -- key only, no dialogue
        row({4: "B", 6: "L1", 7: "BS_NORMAL", 8: "FS_NORMAL", SPEAKER_COL: "神官"}),
        # 2: dialogue that ALSO sets an expression; the key must survive
        row({3: "100000", 8: "FS_CRY", SPEAKER_COL: "イオン",
             DIALOG_COL: "……っ、うぅ……。"}),
        # 3: plain dialogue, no expression
        row({SPEAKER_COL: "神官", DIALOG_COL: "こんにちは。"}),
        # 4: the chibi model -- differs from the normal one only by a space
        row({6: "R1", 7: "BS_ION_BS_DFT_WAIT", SPEAKER_COL: "イオン　"}),
        # 5: the original's own rename: argument 1 the character, 2 the label
        row({CMD_COL: RENAME, CMD_COL + 1: "女Ｂ", CMD_COL + 2: "おねえさん"}),
    ]
    path = "inc/event/res/test/t.txt"
    data = BOM + "\r\n".join(lines).encode("utf-8")

    ng = "inc/globaldata/ngword_data.bin"
    ng_data = b"\x00\x00" + "エッチ".encode("utf-8") + b"\x00" * 8

    # The real charanamemap in its real shape.  Without it known_actors() comes
    # back empty, nothing is renamed, and every key check below would pass with
    # the nameplate feature entirely switched off.
    charamap = "\n".join([
        '"イオン" CHARA_PC00 chara_ion',
        '"イオン　" CHARA_PC22 chara_chibi',
        '"神官" CHARA_NPC12 chara_sinkan',
        '"女Ｂ" CHARA_NPC03 chara_womanB',
    ]).encode("utf-8")

    pak = FakePak({path: data, ng: ng_data, nameplates.CHARAMAP: charamap})

    def cell(p, r, c, zh, jp, kind="dialog"):
        return ("%s#%d#%d" % (p, r, c),
                {"file": p, "row": str(r), "col": str(c),
                 "zh": zh, "jp": jp, "kind": kind})

    script = dict([
        cell(path, 2, DIALOG_COL, "……唔，呜……。", "……っ、うぅ……。"),
        cell(path, 3, DIALOG_COL, "你好。", "こんにちは。"),
        cell(path, 5, CMD_COL + 2, "大姐姐", "おねえさん", "name"),
    ])
    # The two Ion keys are given different labels on purpose: the real data
    # gives both 依恩, which would hide a bug that mixed the two keys up.
    speakers = {"イオン": "依恩", "イオン　": "依恩（Q版）"}
    binmap = {"エッチ": {"zh": "下流", "jp": "エッチ"}}

    out = import_text.build(pak, script, {}, binmap, speakers)
    got = out.get(path, data)
    rows = list(csv.reader(io.StringIO(got[3:].decode("utf-8"))))

    inserted = [r for r in rows
                if len(r) > CMD_COL + 1 and r[CMD_COL].strip() == RENAME
                and r[CMD_COL + 1] != "女Ｂ"]
    body = [r for r in rows if r not in inserted]

    # --- the keys must survive ---------------------------------------------
    check("放置角色的行，第 11 列保持原文", body[1][SPEAKER_COL] == "神官")
    check("有对白且带表情的行，第 11 列也保持原文",
          body[2][SPEAKER_COL] == "イオン")
    check("纯对白行，第 11 列同样保持原文", body[3][SPEAKER_COL] == "神官")
    check("尾随全角空格的角色键原样保留（另一个模型）",
          body[4][SPEAKER_COL] == "イオン　")
    check("动作与表情 ID 未被改动",
          body[1][7] == "BS_NORMAL" and body[2][8] == "FS_CRY"
          and body[4][7] == "BS_ION_BS_DFT_WAIT")
    check("对白本身已翻译",
          body[2][DIALOG_COL] == "……唔，呜……。" and body[3][DIALOG_COL] == "你好。")
    check("改名指令：参数 1（角色键）保持原文", body[5][CMD_COL + 1] == "女Ｂ")
    check("改名指令：参数 2（显示名）已翻译", body[5][CMD_COL + 2] == "大姐姐")
    check("改名指令只导出参数 2",
          CMD_TEXT["EVENT_PROCESS_CHANGE_DISPLAY_NAME"][0] == [2])
    check("屏蔽词表逐字节不变", ng not in out)
    check("移除新增记录后，原脚本记录数还原", len(body) == len(lines))
    check("移除新增记录后，每行列数不变",
          all(len(a) == len(next(csv.reader(io.StringIO(l))))
              for a, l in zip(body, lines)))

    # --- the nameplates must actually be produced ---------------------------
    check("确实生成了中文名牌指令", len(inserted) > 0)
    got_names = {r[CMD_COL + 1]: r[CMD_COL + 2] for r in inserted}
    check("普通模型的键生成了对应指令", got_names.get("イオン") == "依恩")
    check("带全角空格的 Q 版键单独生成，未与普通模型混同",
          got_names.get("イオン　") == "依恩（Q版）")
    check("没有译文的角色键不生成指令（神官 中日同形）", "神官" not in got_names)
    first_new = next((i for i, r in enumerate(rows) if r in inserted), None)
    orig_rename = next((i for i, r in enumerate(rows)
                        if len(r) > CMD_COL + 1 and r[CMD_COL].strip() == RENAME
                        and r[CMD_COL + 1] == "女Ｂ"), None)
    check("默认名紧跟表头（第 1 条记录起）", first_new == 1)
    check("原作自己的改名排在默认名之后",
          first_new is not None and orig_rename is not None
          and first_new < orig_rename)

    print()
    if failures:
        print("%d 项未通过" % len(failures))
        return 1
    print("全部 %d 项自检通过" % (len(failures) + 18))
    return 0


if __name__ == "__main__":
    sys.exit(main())
