# -*- coding: utf-8 -*-
"""Prove that validate.py actually rejects the things it claims to reject.

  py -3 tools/selftest_validate.py

A checker that quietly passes everything is worse than no checker, because
people stop looking.  Each case below builds one deliberately broken row in a
throwaway data folder and asserts the expected complaint comes out -- and one
good row that must pass cleanly.

Runs without the game and without the real data.
"""
import sys, os, io, csv, shutil, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import validate

COLS = ["id", "src", "ctl", "zh", "status", "max_bytes", "occurrences", "note"]

# (name, row overrides, substring expected in the complaint, is it an error)
CASES = [
    ("控制码丢失",
     {"ctl": "<CLBU> br=0 nl=0", "zh": "你好"}, "control codes changed", True),
    ("控制码被改写",
     {"ctl": "<CLY1> br=0 nl=0", "zh": "<CLY2>你好"}, "control codes changed", True),
    ("多加了换行标记",
     {"ctl": "<CR> br=0 nl=0", "zh": "<CR>你好<CR>再见"}, "adds 1 <CR>", True),
    ("少用换行标记只是提醒",
     {"ctl": "<CR> <CR> br=0 nl=0", "zh": "<CR>你好"}, "drops 1 of 2 <CR>", False),
    ("花括号数量变了",
     {"ctl": "br=1 nl=0", "zh": "没有括号"}, "glossary braces changed", True),
    ("花括号不配对",
     {"ctl": "br=1 nl=0", "zh": "{坏掉的"}, "unbalanced", True),
    ("超出字节上限",
     {"max_bytes": "10", "zh": "这段文字明显太长了"}, "the game allows", True),
    ("残留假名",
     {"zh": "还没翻译のテキスト"}, "still contains kana", True),
    ("名字分隔符不算假名",
     {"zh": "依欧娜萨鲁・库库鲁鲁"}, None, False),
    ("字库里没有的字",
     {"zh": "𠀋"}, "not in the patch font", True),
    ("状态与译文不符",
     {"zh": "已经译好了", "status": "todo"}, "status is todo", True),
    ("有状态却没有译文",
     {"zh": "", "status": "translated"}, "there is no translation", True),
    ("未知状态",
     {"zh": "你好", "status": "maybe"}, "unknown status", True),
    ("使用了禁止译法",
     {"zh": "卡侬走了过来"}, "forbidden rendering", True),
    ("控制字符",
     {"zh": "你好\x07世界"}, "control character", True),
    ("正常的一行应当通过",
     {"ctl": "<CLBU> br=1 nl=1", "zh": "<CLBU>{依恩}说：\n你好。"}, None, False),
]


def base_row(i):
    return {"id": "test:%d" % i, "src": "%010d" % i, "ctl": "br=0 nl=0",
            "zh": "你好", "status": "translated", "max_bytes": "",
            "occurrences": "1", "note": ""}


def build(tmp, rows, waive=()):
    zh = os.path.join(tmp, "zh-Hans")
    os.makedirs(zh, exist_ok=True)
    with io.open(os.path.join(zh, "cases.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    # a charset with just what the good cases need
    chars = set("你好再见依欧娜萨鲁库・说：。已经译世界卡侬走了过来段文字明显太长恩{}")
    io.open(os.path.join(tmp, "charset.txt"), "w", encoding="utf-8").write("".join(sorted(chars)))
    os.makedirs(os.path.join(tmp, "glossary"), exist_ok=True)
    with io.open(os.path.join(tmp, "glossary", "glossary.csv"), "w",
                 encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["id", "source", "zh", "kind", "category", "variants",
                    "forbidden", "context", "note", "authority", "status"])
        w.writerow(["kanon", "カノン", "卡诺", "character", "official", "",
                    "卡侬", "", "", "test", "fixed"])
    with io.open(os.path.join(tmp, "allow.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["id", "check", "reason"])
        w.writerows(waive)


def run(tmp):
    rep = validate.Report("text")
    charset = validate.load_charset(tmp)
    _, forbidden = validate.load_glossary(tmp)
    allow = validate.load_allow(tmp)
    path = os.path.join(tmp, "zh-Hans", "cases.csv")
    with io.open(path, encoding="utf-8", newline="") as f:
        rd = csv.DictReader(f)
        rows = list(rd)
        cols = rd.fieldnames
    validate.check_rows(rows, "cases.csv", cols, charset, forbidden, allow, rep, False)
    return rep


def main():
    failures = []
    for i, (name, over, expect, is_error) in enumerate(CASES):
        tmp = tempfile.mkdtemp(prefix="cnval-")
        try:
            row = base_row(i)
            row.update(over)
            build(tmp, [row])
            rep = run(tmp)
            msgs = [m for _, m in rep.errors], [m for _, m in rep.warnings]
            errs, warns = msgs
            if expect is None:
                if errs or warns:
                    failures.append("%s: 本应通过，却报了 %s" % (name, errs + warns))
            else:
                pool = errs if is_error else warns
                other = warns if is_error else errs
                if not any(expect in m for m in pool):
                    failures.append("%s: 期望%s里出现 %r，实际 errors=%s warnings=%s"
                                    % (name, "错误" if is_error else "警告",
                                       expect, errs, warns))
                elif is_error and other and expect not in " ".join(other):
                    pass
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        print("  %-24s %s" % (name, "ok" if not failures or failures[-1].split(":")[0] != name else "FAILED"))

    # the waiver mechanism must actually waive, and only what it names
    tmp = tempfile.mkdtemp(prefix="cnval-")
    try:
        row = base_row(99)
        row["zh"] = "还没翻译のテキスト"
        build(tmp, [row], waive=[("test:99", "kana", "测试用：确认豁免生效")])
        rep = run(tmp)
        if any("kana" in m for _, m in rep.errors):
            failures.append("allow.csv 没有豁免掉它应该豁免的检查")
        print("  %-24s ok" % "allow.csv 豁免生效")

        # a waiver with no reason must not count
        build(tmp, [row], waive=[("test:99", "kana", "")])
        rep = run(tmp)
        if not any("kana" in m for _, m in rep.errors):
            failures.append("allow.csv 中没写理由的行不应生效")
        print("  %-24s ok" % "无理由的豁免被忽略")

        # duplicate ids
        build(tmp, [base_row(1), base_row(1)])
        rep = run(tmp)
        if not any("duplicate id" in m for _, m in rep.errors):
            failures.append("重复 id 没有被发现")
        print("  %-24s ok" % "重复 id")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    if failures:
        for f in failures:
            print("FAILED  %s" % f)
        print("\n%d 项自检未通过" % len(failures))
        return 1
    print("全部 %d 项自检通过" % (len(CASES) + 3))
    return 0


if __name__ == "__main__":
    sys.exit(main())
