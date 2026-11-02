# -*- coding: utf-8 -*-
"""Checks on the display layer's text table, the build side.

  py -3 selftest_text_table.py

No game files.  The C++ side (native/test/selftest.cpp) checks the same FNV-1a
answers and refuses the same malformed tables; between them, a table this
writes is one the DLL reads.
"""
import os, sys, struct, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build_text_table as T          # noqa: E402


def main():
    failures = []

    def check(name, cond):
        print("  %-52s %s" % (name, "ok" if cond else "失败"))
        if not cond:
            failures.append(name)

    def refuses(fn):
        try:
            fn()
        except T.TableError:
            return True
        except Exception as e:            # noqa: BLE001
            print("      不是 TableError，而是 %s: %s" % (type(e).__name__, e))
        return False

    check("FNV-1a 64 与标准答案一致（和 DLL 自检同一组）",
          T.fnv1a64(b"") == 0xCBF29CE484222325
          and T.fnv1a64(b"a") == 0xAF63DC4C8601EC8C
          and T.fnv1a64(b"foobar") == 0x85944171F73967E8)

    speakers = {"イオン": "依恩", "【アイテムで交流しよう！】": "【用道具交流吧！】",
                "神官": "神官", "空": ""}
    held = [("u1", "イオン", "依恩", 9), ("u2", "セーブ", "存档", 9)]
    es = T.entries_from(speakers, held)
    flags = {jp.decode(): f for jp, _zh, f in es}
    check("说话人名：整句与名字位置都替换", flags.get("【アイテムで交流しよう！】") == 3)
    check("EXE 保留词：只整句替换", flags.get("セーブ") == 1)
    check("两边都有且译文一致：标志合并", flags.get("イオン") == 3)
    check("译文与原文相同或为空：不收", "神官" not in flags and "空" not in flags)

    es3 = T.entries_from(speakers, held, [("服飾", "服饰"), ("全部", "全部")])
    f3 = {jp.decode(): f for jp, _zh, f in es3}
    check("手工词表：只整句替换；中日相同的不收",
          f3.get("服飾") == 1 and "全部" not in f3)
    check("手工词表与其他来源译法冲突：拒绝",
          refuses(lambda: T.entries_from({"服飾": "服装"}, [], [("服飾", "服饰")])))
    skipped = []
    es4 = T.entries_from({}, [], [("工作", "手工"), ("服飾", "服饰")],
                         forbid={"工作", "依恩"}, skipped=skipped)
    f4 = {jp.decode() for jp, _zh, _f in es4}
    check("日文键恰好是我们自己的某段中文：排除并报告，不去改写我们的译文",
          "工作" not in f4 and "服飾" in f4
          and skipped == [("工作", "data/zh-Hans/display.csv")])
    d = tempfile.mkdtemp(prefix="cielzh-zh-")
    try:
        os.makedirs(os.path.join(d, "script"))
        with open(os.path.join(d, "script", "x.csv"), "w", encoding="utf-8",
                  newline="") as f:
            f.write("id,jp,zh,status\na:1,仕事,工作,translated\n")
        with open(os.path.join(d, "_index.csv"), "w", encoding="utf-8",
                  newline="") as f:
            f.write("id,jp,zh,status\nb:1,x,不该读到,translated\n")
        ours = T.our_chinese(d)
        check("收集我们自己的中文：含子目录，跳过 _ 开头的索引文件",
              "工作" in ours and "不该读到" not in ours)
    finally:
        import shutil
        shutil.rmtree(d, ignore_errors=True)

    d = tempfile.mkdtemp(prefix="cielzh-disp-")
    try:
        dp = os.path.join(d, "display.csv")
        with open(dp, "w", encoding="utf-8", newline="") as f:
            f.write("id,jp,zh,status,note\n"
                    "display:1,服飾,服饰,translated,\n"
                    "display:2,食料,,todo,\n")
        check("读手工词表：只取已翻译的行",
              T.load_display(dp) == [("服飾", "服饰")]
              and T.load_display(os.path.join(d, "none.csv")) == [])
    finally:
        for fn in os.listdir(d):
            os.remove(os.path.join(d, fn))
        os.rmdir(d)

    data = T.pack(es)
    back = T.parse(data)
    check("写出再读回：条目与译文一致",
          sorted(z for _h, _l, z, _f in back) == sorted(["依恩", "【用道具交流吧！】", "存档"]))
    check("表里没有日文",
          "イオン".encode() not in data and "セーブ".encode() not in data)
    check("按 (摘要, 长度) 排序",
          [(h, l) for h, l, _z, _f in back] == sorted((h, l) for h, l, _z, _f in back))
    count, pool = struct.unpack_from("<II", data, 8)
    check("布局：头 16 字节 + 每条 24 字节 + 译文 + 8 字节校验",
          data[:4] == b"CZT1" and len(data) == 16 + count * 24 + pool + 8)

    check("同一个词两种译法：拒绝",
          refuses(lambda: T.entries_from({"イオン": "依恩"}, [("u", "イオン", "伊恩", 9)])))
    check("译文带标签：拒绝",
          refuses(lambda: T.entries_from({"イオン": "<CLBU>依恩"}, [])))
    bad = bytearray(data)
    bad[-9] ^= 1
    check("校验和不符：读回时拒绝", refuses(lambda: T.parse(bytes(bad))))
    bad = bytearray(data)
    bad[0] = ord("X")
    check("魔数不对：拒绝", refuses(lambda: T.parse(bytes(bad))))

    d = tempfile.mkdtemp(prefix="cielzh-tt-")
    try:
        p = os.path.join(d, "cielzh-text.bin")
        n, size = T.write(p, speakers, held)
        check("写文件：条目数与大小如实报告",
              n == 3 and size == os.path.getsize(p) and not os.path.exists(p + ".tmp"))
    finally:
        for f in os.listdir(d):
            os.remove(os.path.join(d, f))
        os.rmdir(d)

    print()
    if failures:
        print("%d 项未通过" % len(failures))
        return 1
    print("全部自检通过")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
