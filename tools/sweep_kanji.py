# -*- coding: utf-8 -*-
"""Find on-screen text that is still Japanese because it is written in kanji only.

  py -3 tools/sweep_kanji.py [--trace cielzh-trace.txt ...] [--all]

Maintainer tool; needs zhconv (see normalize_cn.py).  Two places it looks:

  * the executable.  export_exe_text.py only takes strings with kana in them --
    a filter that keeps out the thousands of byte runs that happen to decode as
    one CJK character -- so all-kanji UI words such as 服飾 食料 特別 音量設定
    were never exported at all.  Candidates here are NUL-delimited, kana-free,
    not already in executable.csv or display.csv.
  * the translations in data/zh-Hans.  A row whose Chinese still contains a
    Japanese or Traditional form (設 別 飾 報 連 携 ...) shows that form on
    screen, whether it was missed or kept on purpose as "the same in both".

What decides whether something matters is whether the player sees it, which no
static check can say.  So every candidate is marked with whether any of the
given stage-one traces saw the game set it on a widget.  Executable strings are
also marked when they sit next to strings we already know are UI text -- the
item categories turned up in exactly such a table, beside パジャマ.

It only reports.  Executable strings belong in data/zh-Hans/display.csv (the
display layer, because an all-kanji word in that table may be a key as well);
data rows are fixed where they are.
"""
import argparse, csv, io, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from normalize_cn import normalize            # noqa: E402

ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data", "zh-Hans")
KANA = re.compile(r"[぀-ヿ]")
CJK = re.compile(r"[一-鿿]")
# characters allowed alongside the kanji in a UI word
ALLOWED = re.compile(r"^[一-鿿　-〿！-～"
                     r"0-9A-Za-z ・ー々〆]+$")


def load_rows(path):
    with io.open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def known_exe(data):
    """Japanese strings already handled for the executable."""
    out = set()
    for name in ("executable.csv", "display.csv"):
        p = os.path.join(data, name)
        if os.path.exists(p):
            out.update(r["jp"] for r in load_rows(p))
    return out


def trace_texts(paths):
    seen = set()
    for p in paths:
        with io.open(p, encoding="utf-8", errors="replace", newline="") as f:
            lines = [l for l in f if not l.startswith("#")]
        for r in csv.DictReader(lines):
            if r.get("op") == "set":
                t = re.sub(r"<[A-Z0-9]+>", "", r.get("text", ""))
                seen.add(t)
                seen.update(x for x in re.split(r"\s+", t) if x)
    return seen


def exe_candidates(exe, known):
    d = open(exe, "rb").read()
    found = []
    for m in re.finditer(rb"\x00((?:[\xe3-\xe9][\x80-\xbf]{2}|[\x20-\x7e]){1,48})(?=\x00)", d):
        raw = m.group(1)
        try:
            t = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        if KANA.search(t) or not CJK.search(t) or not ALLOWED.match(t):
            continue
        if t in known:
            continue
        found.append((m.start(1), t))
    # a string is "in a UI table" when a known string sits within 96 bytes
    known_at = []
    for k in known:
        b = k.encode("utf-8") + b"\x00"
        i = d.find(b)
        while i >= 0:
            known_at.append(i)
            i = d.find(b, i + 1)
    known_at.sort()
    import bisect
    out = []
    for off, t in found:
        j = bisect.bisect_left(known_at, off - 96)
        near = j < len(known_at) and known_at[j] <= off + 96
        out.append((off, t, near))
    return out


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=None)
    ap.add_argument("--trace", action="append", default=[])
    ap.add_argument("--all", action="store_true",
                    help="list every executable candidate, not only the likely ones")
    a = ap.parse_args(argv)
    if a.exe is None:
        from build_charset import pristine_exe
        a.exe = pristine_exe()
    seen = trace_texts(a.trace)

    print("=== 封包数据里仍是日文或繁体写法的译文")
    rows_bad = []
    for root, _, names in os.walk(DATA):
        for fn in sorted(names):
            if not fn.endswith(".csv") or fn.startswith("_"):
                continue
            p = os.path.join(root, fn)
            for r in load_rows(p):
                zh = r.get("zh") or ""
                if zh and normalize(zh) != zh:
                    rows_bad.append((os.path.relpath(p, ROOT), r.get("id"), r.get("jp", ""), zh))
    for rel, rid, jp, zh in rows_bad:
        mark = "屏幕上见过" if zh in seen or jp in seen else ""
        print("  %-10s %-30s %-28s %s -> %s" % (mark, rel.replace(os.sep, "/")[:30],
                                              rid[:28], jp[:24], zh[:24]))
    print("  共 %d 条" % len(rows_bad))

    print("\n=== EXE 里未导出的纯汉字字符串")
    cands = exe_candidates(a.exe, known_exe(DATA))
    shown = 0
    for off, t, near in cands:
        japanese = normalize(t) != t
        on_screen = t in seen
        likely = on_screen or (near and (japanese or len(t) >= 2))
        if not (likely or a.all):
            continue
        shown += 1
        flags = " ".join(x for x, y in (("屏幕上见过", on_screen),
                                        ("日文写法", japanese),
                                        ("邻近界面文字", near)) if y)
        print("  0x%07x  %-16s %s" % (off, t, flags))
    print("  共 %d 条候选（全部纯汉字串 %d 条，--all 可全部列出）" % (shown, len(cands)))
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv[1:]))
