# -*- coding: utf-8 -*-
"""Self-test for workscript.py and the build steps that read script.zip.

  py -3 tools/selftest_workscript.py

No game needed: a synthetic export with three script files.
"""
import csv, io, os, shutil, sys, tempfile, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import workscript as W                  # noqa: E402

failures = []


def check(name, cond):
    print("  %-52s %s" % (name, "ok" if cond else "失败"))
    if not cond:
        failures.append(name)


def refuses(fn):
    try:
        fn()
    except W.WorkScriptError:
        return True
    return False


HDR = ["uid", "key", "file", "row", "col", "kind", "speaker", "lines", "jp", "zh", "note"]


def script(rows):
    return W.serialize(HDR, rows)


MEMBERS = [
    ("dateeventroot.csv", script([[1, "inc/event/res/a.txt#3#12", "a", 3, 12, "dialog", "イオン", 2,
                                   "{夢セカイ}へ\n行こう", "", ""]])),
    ("dateevent_p.csv", script([[2, "inc/event/res/b.txt#4#12", "b", 4, 12, "dialog", "", 1,
                                 "シャールだ", "", ""]])),
    ("01.csv", script([[3, "inc/event/res/c.txt#5#14", "c", 5, 14, "memo", "", 1,
                        "メモ\r\n二行", "", ""]])),
]

root = tempfile.mkdtemp(prefix="cielzh-ws-")
try:
    exp = os.path.join(root, "work")

    # --- writing and reading back -------------------------------------------
    W.write_all(exp, MEMBERS)
    got = W.read_all(exp)
    check("写入后读回：成员与内容一致", dict(got) == dict(MEMBERS))
    check("成员按 NTFS 的列目录顺序（大写排序）",
          # 'R' (0x52) sorts before '_' (0x5F) once both are upper case
          [n for n, _ in got] == ["01.csv", "dateeventroot.csv", "dateevent_p.csv"])
    with zipfile.ZipFile(W.bundle_path(exp)) as z:
        infos = z.infolist()
    check("不压缩，时间戳固定",
          all(i.compress_type == zipfile.ZIP_STORED and i.date_time == W.STAMP for i in infos))
    first = open(W.bundle_path(exp), "rb").read()
    W.write_all(exp, list(reversed(MEMBERS)))
    check("同样的成员总是写出同样的字节", open(W.bundle_path(exp), "rb").read() == first)
    rows = W.rows(dict(got)["01.csv"])
    check("读出的记录保留字段内换行（含 CRLF）", rows[0]["jp"] == "メモ\r\n二行")
    check("serialize 与 export_text.w 写散文件的字节相同", True)
    loose_dir = os.path.join(root, "loose")
    import export_text
    export_text.w(os.path.join(loose_dir, "x.csv"), HDR, [[1, "k", "f", 1, 12, "dialog", "", 1, "あ,い\n\"う\"", "", ""]])
    check("  ……逐字节比较", open(os.path.join(loose_dir, "x.csv"), "rb").read()
          == W.serialize(HDR, [[1, "k", "f", 1, 12, "dialog", "", 1, "あ,い\n\"う\"", "", ""]]))

    # --- one source only ----------------------------------------------------
    os.makedirs(W.loose_path(exp))
    check("zip 与 script/ 同时存在：拒绝读取", refuses(lambda: W.read_all(exp)))
    check("  ……合并等后续写入也拒绝", refuses(lambda: W.write_all(exp, MEMBERS)))
    W.write_all(exp, MEMBERS, replace_loose=True)
    check("  ……提取阶段重新生成时清掉旧的 script/",
          not os.path.isdir(W.loose_path(exp)) and W.source(exp) == "zip")

    # --- damaged archives ---------------------------------------------------
    bad = os.path.join(root, "dup")
    os.makedirs(bad)
    with zipfile.ZipFile(W.bundle_path(bad), "w") as z:
        z.writestr("01.csv", b"a")
    with zipfile.ZipFile(W.bundle_path(bad), "a") as z:
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            z.writestr("01.csv", b"b")           # what an append-mode update leaves
    check("同名成员出现两次：拒绝", refuses(lambda: W.read_all(bad)))

    corrupt = os.path.join(root, "crc")
    os.makedirs(corrupt)
    shutil.copy(W.bundle_path(exp), W.bundle_path(corrupt))
    data = bytearray(open(W.bundle_path(corrupt), "rb").read())
    i = data.find("シャール".encode("utf-8"))
    data[i] ^= 0xFF
    open(W.bundle_path(corrupt), "wb").write(bytes(data))
    check("成员内容损坏（CRC 不符）：拒绝", refuses(lambda: W.read_all(corrupt)))
    open(W.bundle_path(corrupt), "wb").write(first[:len(first) // 2])
    check("文件被截断：拒绝", refuses(lambda: W.read_all(corrupt)))
    check("写入时成员重名：拒绝", refuses(lambda: W.write_all(corrupt, MEMBERS + MEMBERS[:1])))

    # --- an interrupted write leaves the old archive alone -------------------
    before = open(W.bundle_path(exp), "rb").read()
    real_replace = os.replace

    def boom(a, b):
        raise OSError("disk full")
    os.replace = boom
    try:
        W.write_all(exp, [(n, b + b"x") for n, b in MEMBERS])
        interrupted = False
    except OSError:
        interrupted = True
    finally:
        os.replace = real_replace
    check("写入中断：原来的 script.zip 原样保留",
          interrupted and open(W.bundle_path(exp), "rb").read() == before)
    os.remove(W.bundle_path(exp) + ".part")

    # --- unpack / pack for maintenance tools --------------------------------
    n = W.unpack(exp)
    check("unpack：解成散文件，zip 移除", n == 3 and W.source(exp) == "loose")
    check("  ……散文件读回内容不变", dict(W.read_all(exp)) == dict(MEMBERS))
    W.pack(exp)
    check("pack：重新打包，散文件移除", W.source(exp) == "zip" and dict(W.read_all(exp)) == dict(MEMBERS))

    # --- the merge, through merge_repo.main -----------------------------------
    import merge_repo
    from repo_export import src_hash
    data_dir = os.path.join(root, "data")
    os.makedirs(os.path.join(data_dir, "zh-Hans", "script"))
    with io.open(os.path.join(data_dir, "zh-Hans", "script", "dateevent_p.csv"), "w",
                 encoding="utf-8", newline="") as f:
        cw = csv.writer(f, lineterminator="\n")
        cw.writerow(["id", "jp", "zh", "status", "speaker", "src", "ctl", "lines", "note"])
        cw.writerow(["inc/event/res/b.txt#4#12", "シャールだ", "是夏尔", "translated", "", src_hash("シャールだ"), "", 1, ""])
    import contextlib
    with contextlib.redirect_stdout(io.StringIO()):
        rc = merge_repo.main([data_dir, exp])
    merged = dict(W.read_all(exp))
    check("合并：译文写进 zip 成员", rc == 0 and W.rows(merged["dateevent_p.csv"])[0]["zh"] == "是夏尔")
    check("  ……其他成员不变", merged["01.csv"] == dict(MEMBERS)["01.csv"])
    check("  ……合并后仍只有 zip 一种来源，没有重复成员",
          W.source(exp) == "zip" and len(zipfile.ZipFile(W.bundle_path(exp)).namelist()) == 3)

    # --- the injector's view -------------------------------------------------
    import import_text
    script_rows, _ui, _bin, _sp = import_text.collect(exp)
    check("注入阶段从 zip 读到译文", script_rows.get("inc/event/res/b.txt#4#12", {}).get("zh") == "是夏尔")

    # --- term counting order is the order the loose files were walked in ------
    a = os.path.join(root, "terms_zip")
    b = os.path.join(root, "terms_loose")
    W.write_all(a, MEMBERS)
    os.makedirs(os.path.join(b, "script"))
    for n, d in MEMBERS:
        open(os.path.join(b, "script", n), "wb").write(d)
    export_text.export_terms(a, min_freq=1)
    export_text.export_terms(b, min_freq=1)
    ta = open(os.path.join(a, "glossary_terms.csv"), "rb").read()
    tb = open(os.path.join(b, "glossary_terms.csv"), "rb").read()
    strip = lambda t: [l.split(b",", 1)[1] for l in t.splitlines()[1:]]   # uids differ per call
    check("术语统计：zip 与散文件得到同样的行和顺序", strip(ta) == strip(tb) and len(strip(ta)) >= 2)
finally:
    shutil.rmtree(root, ignore_errors=True)

print()
print("%d 项未通过" % len(failures) if failures else "全部自检通过")
sys.exit(1 if failures else 0)
