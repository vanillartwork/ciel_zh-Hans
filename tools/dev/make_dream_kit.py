# -*- coding: utf-8 -*-
# Build the outside-translation kit for data/zh-Hans/dream.csv.
import csv, io, os, sys, collections, re
REPO, OUT = sys.argv[1], sys.argv[2]
sys.path.insert(0, os.path.join(REPO, "tools"))
from gustpak import Pak
import gbd_text as G

pak = Pak(r"C:/Program Files (x86)/Steam/steamapps/common/CielnosurgeDX/Backup/PACK01.PAK")
lands = G.collect(pak)                      # key -> (jp, [(member, record, field, off)])
rows = {r["id"]: r for r in csv.DictReader(io.open(os.path.join(REPO, "data/zh-Hans/dream.csv"),
                                                   encoding="utf-8", newline=""))}
todo = [k for k in lands if not rows[k]["zh"]]

KIND = {"area.title": "梦世界章节副标题（进门确认框里显示，格式「试炼篇第一幕：XXX」）",
        "history.title": "HISTORY 条目标题（保留开头编号，如「01-00:」「EX01-01:」）",
        "history.summary": "HISTORY 剧情概要（叙述体，过去时，保留换行）",
        "ruin.name": "夏尔之巢·废墟地点名",
        "restore.name": "夏尔之巢·废墟修复对象名（建筑、设施、装置等）"}


def budget(r):
    return int(r["max_bytes"]) - 1


def max_chars(jp, b):
    # every CJK character and full-width mark is 3 bytes in UTF-8, ASCII 1;
    # assume the ASCII parts (numbers, "EX01-01:", line breaks) are kept
    ascii_bytes = sum(1 for ch in jp if ord(ch) < 128)
    return (b - ascii_bytes) // 3


os.makedirs(OUT, exist_ok=True)
for fn in os.listdir(OUT):
    if fn.startswith("batch_"):
        os.remove(os.path.join(OUT, fn))

groups = collections.OrderedDict()
names = [k for k in todo if k.split(":")[0] in ("area.title", "ruin.name", "restore.name")]
hist = [k for k in todo if k.startswith("history.")]
# history: keep title and summary of one record together, in record order
order = []
seen = set()
for k in hist:
    rec = lands[k][1][0][1]
    if rec in seen:
        continue
    seen.add(rec)
    for kk in hist:
        if lands[kk][1][0][1] == rec and kk not in order:
            order.append(kk)
order += [k for k in hist if k not in order]

batches = [("names", names)]
per = 60
for i in range(0, len(order), per):
    batches.append(("history", order[i:i + per]))

COLS = ["id", "kind", "record", "max_cjk_chars", "jp", "zh"]
all_text = []
for n, (label, keys) in enumerate(batches, 1):
    path = os.path.join(OUT, "batch_%02d_%s.csv" % (n, label))
    with io.open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS, lineterminator="\r\n")
        w.writeheader()
        for k in keys:
            r = rows[k]
            kind = k.split(":")[0]
            w.writerow(dict(id=k, kind=KIND[kind], record=lands[k][1][0][1],
                            max_cjk_chars=max_chars(r["jp"], budget(r)), jp=r["jp"], zh=""))
            all_text.append(r["jp"])
    print(path, len(keys))

# glossary: project terms and character names that occur in the text
blob = "\n".join(all_text)
gl = []
for r in csv.DictReader(io.open(os.path.join(REPO, "data/glossary/glossary.csv"), encoding="utf-8", newline="")):
    src = r["source"].strip("【】")
    if len(src) >= 2 and src in blob and r["zh"]:
        gl.append((r["source"], r["zh"], r.get("forbidden", ""), r.get("kind", "")))
for r in csv.DictReader(io.open(os.path.join(REPO, "data/zh-Hans/speakers.csv"), encoding="utf-8", newline="")):
    jp = r["jp"].strip()
    if len(jp) >= 2 and jp in blob and r["zh"] and all(jp != g[0] for g in gl):
        gl.append((jp, r["zh"], "", "character"))
# already-settled translations of these tables, as style anchors
done = [(r["jp"], r["zh"]) for r in rows.values() if r["zh"]]
with io.open(os.path.join(OUT, "glossary.csv"), "w", encoding="utf-8-sig", newline="") as f:
    w = csv.writer(f, lineterminator="\r\n")
    w.writerow(["jp", "zh", "do_not_use", "kind"])
    for g in sorted(gl, key=lambda g: -len(g[0])):
        w.writerow(g)
    for jp, zh in done:
        if all(jp != g[0] for g in gl):
            w.writerow([jp, zh, "", "settled"])
print(len(gl), "glossary terms,", len(done), "settled rows")
