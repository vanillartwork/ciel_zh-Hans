# -*- coding: utf-8 -*-
"""Export the Japanese strings compiled into the executable as a translation CSV.

  py -3 export_exe_text.py <out dir>

No data file reaches these strings: they were baked into .rdata at build time,
so the executable is the only copy.  They are pulled out here into the same
shape as every other translation file, which means they go through the same
review, validation and injection path as the rest of the project.

Because patching happens in place -- the alternative is repointing every
RIP-relative lea that reaches them -- a translation may not be longer in
UTF-8 than the Japanese it replaces.  `max_bytes` on each row is that budget.

Ids are the first 8 hex digits of the SHA-1 of the Japanese string, so a row
keeps its id when the executable is re-scanned and neighbouring strings come
and go.  Re-running over an existing exe_text.csv carries `zh` and `note`
across and reports what moved.

Debug output, assertion text and animation-timing names are filtered out:
they never reach the screen, and some of them double as identifiers.
"""
import sys, os, io, csv, re, hashlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_charset import pristine_exe

JP = re.compile(r"[぀-ヿ一-鿿]")
# Real UI text in this game practically always contains kana; requiring it
# throws out the thousands of one-character hits where arbitrary binary data
# happens to decode as a CJK ideograph.
KANA = re.compile(r"[぀-ヿ]")

# A run of printable ASCII and well-formed UTF-8 multibyte sequences, ending
# at a NUL.  The multibyte alternatives have to cover the whole range: an
# earlier version stopped at \xe3-\xe9 and so cut strings in half at ※ ★ ®
# ＆ ！ and the fullwidth digits, which silently produced rows that could
# never be matched back into the executable.
STRING = re.compile(
    rb'(?:[\x20-\x7e\x0a\x0d\t]'
    rb'|[\xc2-\xdf][\x80-\xbf]'
    rb'|\xe0[\xa0-\xbf][\x80-\xbf]'
    rb'|[\xe1-\xec\xee\xef][\x80-\xbf]{2}'
    rb'|\xed[\x80-\x9f][\x80-\xbf]'
    rb'|\xf0[\x90-\xbf][\x80-\xbf]{2}'
    rb'|[\xf1-\xf3][\x80-\xbf]{3}'
    rb'|\xf4[\x80-\x8f][\x80-\xbf]{2}'
    rb'){2,400}\x00')

# never shown to the player
DEV = re.compile(
    r"(NULL|Bride|Cielnotron|NullObj|廃止|%[sdufxlu]|=%|::|"
    r"クラス|ノード|ポインタ|引数|範囲外|想定外|無効|不正|失敗|"
    r"取得でき|作成されて|設定されて|見つかり|読み込みに|インスタンス|"
    r"0除算|0割|二重作成|イレギュラー|異常です|空文字列|空になって|"
    r"モーション|タグ名|スレッド|オープン数)")
# animation and behaviour timing labels, used as identifiers in the editor
ANIM = re.compile(
    r"(向き直|へ移動|を持って|に入れる|を開ける|を閉める|"
    r"工程開始|工程終了|開始$|終了$|終了2$|端末がベース|"
    r"^(食事|取り出し|運搬|食器洗い|読書|昼寝|お絵かき|呆ける|"
    r"トイレ|掃除|料理|調合|装備|端末移動)。)")

COLS = ["uid", "max_bytes", "occurrences", "jp", "zh", "note"]


def uid_for(text):
    return "exe:" + hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]


def candidates(exe_path=None):
    d = open(exe_path or pristine_exe(), "rb").read()
    seen = {}
    for m in STRING.finditer(d):
        raw = m.group()[:-1]
        # finditer restarts after the previous match, so a run that begins in
        # the middle of a string cannot happen here -- but a run that begins
        # just after some non-text byte still can.  Only accept a real string.
        if m.start() > 0 and d[m.start() - 1] != 0:
            continue
        try:
            t = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        if not KANA.search(t):
            continue
        if len(JP.findall(t)) < 2:
            continue
        if DEV.search(t) or ANIM.search(t):
            continue
        if "\n" not in t and len(t) < 2:
            continue
        prev = seen.get(t)
        if prev is None:
            seen[t] = [len(raw), 1]
        else:
            prev[1] += 1
    return seen


def main(outdir):
    os.makedirs(outdir, exist_ok=True)
    path = os.path.join(outdir, "exe_text.csv")

    old = {}
    if os.path.exists(path):
        for r in csv.DictReader(io.open(path, encoding="utf-8-sig", newline="")):
            old[r["jp"]] = r

    seen = candidates()
    rows, carried = [], 0
    for t, (nbytes, count) in sorted(seen.items()):
        note = "多行" if "\n" in t else ""
        if count > 1:
            note = (note + " " if note else "") + "出现%d次" % count
        prev = old.get(t)
        if prev:
            carried += 1
            zh = prev["zh"]
            if prev["note"].strip() and not prev["zh"].strip():
                note = prev["note"]
        else:
            zh = ""
        rows.append(dict(zip(COLS, [uid_for(t), nbytes, count, t, zh, note])))

    with io.open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS, lineterminator="\r\n")
        w.writeheader()
        w.writerows(rows)

    gone = [j for j in old if j not in seen]
    print("%d strings -> %s" % (len(rows), path))
    if old:
        print("  carried %d existing translations across, %d rows are new, "
              "%d rows from the old file no longer match the executable"
              % (carried, len(rows) - carried, len(gone)))
    return rows


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ".")
