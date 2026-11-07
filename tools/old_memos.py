# -*- coding: utf-8 -*-
"""Display-time repair of memo texts already sitting in players' saves.

From 0.9.8 the scripts keep the memo texts (EVENT_PROCESS_WRITE_MEMO) in
Japanese, so new saves store the original and the display layer shows the
Chinese.  Saves made with 0.9.4-0.9.7 hold Chinese memos instead, written
from the translations of the time:

  * some of those translations have since been reworded or re-broken, and the
    old wording would keep showing;
  * the save's memo slot is short.  A memo longer than the slot is cut when it
    is stored, at a UTF-8 character boundary -- 面对自己不太拿手的裁缝。……
    我也能竭尽全力 lost its 做好了♪ after 92 bytes in a save made on
    2026-11-02.  The exact limit was not found in the code: the observed cut
    puts it at 92, 93 or 94 bytes, so all three cuts are listed.  Japanese
    memos are cut the same way; three originals are 95 bytes long.

Each such stored text becomes one more whole-text entry for the display layer,
mapped to today's translation of the same memo.  An entry is made only when the
stored text identifies one memo: two memos that cut to the same prefix, or a
cut that happens to be the complete text of another memo, are left alone, and
show what the save holds.  Nothing is written back to any save.

data/zh-Hans/_memo_history.csv lists the earlier translations (id, jp, zh,
release); tools/dev/gen_memo_history.py rebuilds it from the release tags.
"""
import collections, csv, io, os

LIMITS = (92, 93, 94)          # bytes the save's memo slot may hold; see above
HISTORY = "_memo_history.csv"


def load_history(zh_dir):
    """[(jp, zh)] translations of memos shipped by earlier releases."""
    p = os.path.join(zh_dir, HISTORY)
    if not os.path.exists(p):
        return []
    with io.open(p, encoding="utf-8", newline="") as f:
        return [(r["jp"], r["zh"]) for r in csv.DictReader(f) if r["zh"]]


def cut(text, limit):
    """`text` as a slot of `limit` bytes stores it: whole characters only."""
    b = text.encode("utf-8")
    if len(b) <= limit:
        return text
    b = b[:limit]
    while b:
        try:
            return b.decode("utf-8")
        except UnicodeDecodeError:
            b = b[:-1]
    return ""


def pairs(memos, history):
    """[(stored text, today's Chinese)] beyond the plain Japanese entries.

    `memos` is [(jp, zh)] as the build has them now; `history` [(jp, old zh)].
    """
    now = collections.defaultdict(set)
    for jp, zh in memos:
        now[jp.replace("\r\n", "\n")].add(zh)
    full = set(now)                               # every complete Japanese memo
    for zhs in now.values():
        full |= zhs                               # and every complete Chinese one

    stored = collections.defaultdict(set)         # text a save may hold -> jp
    for jp in now:
        stored[jp].add(jp)
        for zh in now[jp]:
            stored[zh].add(jp)                    # what 0.9.8 previews wrote
    for jp, zh in history:
        jp = jp.replace("\r\n", "\n")
        if jp in now:
            stored[zh].add(jp)

    targets = collections.defaultdict(set)        # key -> today's Chinese
    for text, jps in stored.items():
        keys = {text} | {cut(text, n) for n in LIMITS}
        for jp in jps:
            if len(now[jp]) != 1:                 # the memo itself is ambiguous
                continue
            zh = next(iter(now[jp]))
            for k in keys:
                if k and k != zh:
                    targets[k].add(zh)
    out = []
    for k, zhs in sorted(targets.items()):
        if len(zhs) != 1:
            continue                              # two memos share this text
        if k in now:
            continue                              # a complete Japanese memo: already listed
        zh = next(iter(zhs))
        if k in full and k != zh:
            if any(k in v for v in now.values()):
                continue                          # a complete Chinese memo of today's
        out.append((k, zh))
    return out
