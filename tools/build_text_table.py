# -*- coding: utf-8 -*-
"""Build cielzh-text.bin: what the display layer replaces on screen, and with what.

  called from build_patch.py; py -3 tools/selftest_text_table.py checks it

Three sources:

  * the speaker glossary -- names the game uses as keys and also shows as
    nameplates (イオン, 【アイテムで交流しよう！】, システム文 ...).  Matched as
    a whole text and as the name inside a <CLY2>... span, which is how a
    nameplate and a line of the message log carry it.
  * the executable strings exe_keys.py held back -- display text the game ALSO
    indexes its data by, so the executable keeps the Japanese.  Matched only as
    a whole text: a word like はい inside a sentence is not that word.
  * data/zh-Hans/display.csv -- strings the game shows that no other route
    reaches, kept by hand.  The first were the item categories 服飾 食料 工作
    特別: all-kanji executable strings, which the exporter skips because it
    requires kana, sitting in the same table as パジャマ and プラグイン and so
    treated as keys too.  Matched only as a whole text.

The table holds no Japanese.  Each entry is the 64-bit FNV-1a hash and the
length of a Japanese string, plus our Chinese.  The DLL hashes what the game
sets and looks it up.  Both sides check the same published FNV-1a answers, so a
mismatch fails a test rather than a playthrough.

Layout (little-endian):

  0   "CZT1"
  4   u32 version = 1
  8   u32 count
  12  u32 pool bytes
  16  count x { u64 hash; u32 jp_len; u32 zh_off; u32 zh_len; u32 flags }
  ..  pool: the Chinese strings, UTF-8, not terminated
  ..  u64 FNV-1a over everything before it

Sorted by (hash, jp_len), no two entries alike.  native/cielzh/display.cpp
refuses anything else, whole.
"""
import io, os, struct

MAGIC = b"CZT1"
VERSION = 1
WHOLE = 1
NAME = 2
ENTRY = struct.Struct("<QIIII")      # 24 bytes
MAX_TEXT = 1 << 16


class TableError(ValueError):
    """The sources do not make a table the DLL would accept."""


def fnv1a64(data):
    h = 0xCBF29CE484222325
    for b in data:
        h ^= b
        h = (h * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
    return h


def load_display(path):
    """[(jp, zh)] from data/zh-Hans/display.csv: translated rows only."""
    import csv
    if not os.path.exists(path):
        return []
    with io.open(path, encoding="utf-8", newline="") as f:
        return [(r["jp"], r["zh"]) for r in csv.DictReader(f)
                if (r.get("status") or "").strip() == "translated"]


def our_chinese(data_dir):
    """Every Chinese string the patch itself puts on screen, from data/zh-Hans.

    The display layer matches what arrives at the setter by its text alone; it
    cannot tell the game's Japanese from Chinese we already wrote.  So a key
    that is ALSO one of our Chinese strings would rewrite our own translation.
    That happened: 工作 was added as the item category (Japanese for crafts,
    shown as 手工), and our dialogue translates 仕事 as 工作 -- a choice that
    reads 工作 would have been turned into 手工.
    """
    import csv
    out = set()
    for root, _, names in os.walk(data_dir):
        for fn in names:
            if fn.endswith(".csv") and not fn.startswith("_"):
                with io.open(os.path.join(root, fn), encoding="utf-8",
                             newline="") as f:
                    for r in csv.DictReader(f):
                        z = r.get("zh") or ""
                        if z:
                            out.add(z)
    return out


def memo_variants(jp, zh):
    """(jp, zh) pairs for one 嬉しかったことメモ entry.

    EVENT_PROCESS_WRITE_MEMO stores its text in the save, and the memo screen
    shows what was stored -- so a memo written before the patch stays Japanese
    in that save for good, whatever the scripts say now.  The screen hands each
    memo to the setter whole, line breaks included, which is why these are the
    one source allowed to span lines.  Four of the 1,489 memo cells in the
    scripts carry CRLF; both spellings are listed so either matches.
    """
    out = [(jp, zh)]
    lf = jp.replace("\r\n", "\n")
    if lf != jp:
        out.append((lf, zh))
    return out


def entries_from(speakers, held, display=(), forbid=frozenset(), skipped=None,
                 memos=()):
    """[(jp_bytes, zh_bytes, flags)] from the speaker glossary (jp -> zh), the
    held-back executable strings ((uid, jp, zh, cap) as exe_keys.split gives),
    the hand-kept display list ((jp, zh) pairs), and the memo texts the scripts
    write into saves ((jp, zh) pairs, see memo_variants).

    A string in both sources gets both flags -- but only if both agree on the
    Chinese.  Two different Chinese texts for one Japanese string is a decision
    somebody has to make, not one this picks for them.

    A Japanese string that is also one of our own Chinese strings (`forbid`,
    see our_chinese) is left out and named in `skipped`: the display layer
    could not tell the two apart, and leaving the game's word alone costs less
    than rewriting our translation somewhere else.
    """
    found = {}

    def add(jp, zh, flag, where, multiline=False):
        if not jp or not zh or zh == jp:
            return
        if jp in forbid:
            if skipped is not None and (jp, where) not in skipped:
                skipped.append((jp, where))
            return
        if "<" in zh or "\x00" in zh:
            raise TableError("%s: the Chinese for %r holds a tag or a NUL, and "
                             "the display layer would refuse the whole table"
                             % (where, jp))
        if ("\n" in jp and not multiline) or len(jp.encode("utf-8")) > MAX_TEXT:
            return
        if jp in found:
            old_zh, old_flags = found[jp]
            if old_zh != zh:
                raise TableError("%r is translated two ways: %r and %r (%s)"
                                 % (jp, old_zh, zh, where))
            found[jp] = (zh, old_flags | flag)
        else:
            found[jp] = (zh, flag)

    for jp, zh in sorted(speakers.items()):
        add(jp, zh, WHOLE | NAME, "speaker glossary")
    for row in held:
        add(row[1], row[2], WHOLE, "executable strings kept Japanese")
    for jp, zh in display:
        add(jp, zh, WHOLE, "data/zh-Hans/display.csv")
    for jp0, zh0 in memos:
        # a memo with a tag in it is not plain text on that screen; leave it
        if "<" in jp0 or "<" in zh0:
            continue
        for jp, zh in memo_variants(jp0, zh0):
            add(jp, zh, WHOLE, "memo text (EVENT_PROCESS_WRITE_MEMO)", multiline=True)

    out = [(jp.encode("utf-8"), zh.encode("utf-8"), flags)
           for jp, (zh, flags) in found.items()]
    out.sort(key=lambda e: (fnv1a64(e[0]), len(e[0])))
    for a, b in zip(out, out[1:]):
        if (fnv1a64(a[0]), len(a[0])) == (fnv1a64(b[0]), len(b[0])):
            raise TableError("%r and %r hash alike; the table cannot tell them "
                             "apart" % (a[0].decode(), b[0].decode()))
    return out


def pack(entries):
    pool = b""
    body = []
    for jp, zh, flags in entries:
        body.append(ENTRY.pack(fnv1a64(jp), len(jp), len(pool), len(zh), flags))
        pool += zh
    head = MAGIC + struct.pack("<III", VERSION, len(entries), len(pool))
    data = head + b"".join(body) + pool
    return data + struct.pack("<Q", fnv1a64(data))


def parse(data):
    """The same checks display.cpp makes, for the self-test.  [(hash, jp_len,
    zh, flags)] or TableError."""
    if len(data) < 24 or data[:4] != MAGIC:
        raise TableError("not a text table")
    version, count, pool = struct.unpack_from("<III", data, 4)
    if version != VERSION:
        raise TableError("version %d" % version)
    body = 16 + count * ENTRY.size + pool
    if body + 8 != len(data):
        raise TableError("size does not add up")
    if fnv1a64(data[:body]) != struct.unpack_from("<Q", data, body)[0]:
        raise TableError("checksum")
    at = 16 + count * ENTRY.size
    out, prev = [], None
    for i in range(count):
        h, jl, off, zl, flags = ENTRY.unpack_from(data, 16 + i * ENTRY.size)
        if off + zl > pool or zl == 0 or jl == 0 or jl > MAX_TEXT:
            raise TableError("entry %d points outside" % i)
        if flags == 0 or flags & ~(WHOLE | NAME):
            raise TableError("entry %d flags" % i)
        zh = data[at + off:at + off + zl]
        if b"\x00" in zh or b"<" in zh:
            raise TableError("entry %d holds a NUL or a tag" % i)
        if prev is not None and prev >= (h, jl):
            raise TableError("not sorted, or a duplicate")
        prev = (h, jl)
        out.append((h, jl, zh.decode("utf-8"), flags))
    return out


def write(path, speakers, held, display=(), forbid=frozenset(), skipped=None,
          memos=()):
    """Writes the table; returns (entries, bytes).  Keys left out because they
    collide with our own Chinese are appended to `skipped`."""
    entries = entries_from(speakers, held, display, forbid, skipped, memos)
    data = pack(entries)
    parse(data)                       # never write a table the DLL would refuse
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    return len(entries), len(data)
