"""Cut the export into batches sized for another AI to translate.

  py -3 make_batches.py <export dir> <batches dir> [--chars 12000] [--only script/01.csv]

Each batch is a plain-text file you paste as one message, together with
PROMPT.md as the system prompt.  Batches carry only what the translator
needs (uid, speaker, line count, limits) so they stay token-cheap.

Any glossary entry that is already filled in and that occurs in the batch
is injected at the top, so every session uses the same wording.
"""
import sys, os, io, csv

NL = chr(10)

# A dialogue line this long that appears twice is the same content both times
# (system messages such as the affection-up notice repeat 288 times), so it is
# translated once.  Shorter lines are interjections whose wording may and
# should vary with the scene, so they stay per-row.
DIALOG_DEDUP_MIN = 12


def dedupable(rel, r):
    if not rel.startswith("script/") or r.get("kind") != "dialog":
        return True
    return len(r["jp"]) >= DIALOG_DEDUP_MIN


def load(path):
    with io.open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def sources(exportdir, only=None):
    out = []
    sd = os.path.join(exportdir, "script")
    if os.path.isdir(sd):
        for fn in sorted(os.listdir(sd)):
            if fn.endswith(".csv"):
                out.append("script/" + fn)
    for fn in ("ui_text.csv", "item_text.csv", "global_text.csv",
               "glossary_terms.csv", "glossary_speakers.csv"):
        if os.path.exists(os.path.join(exportdir, fn)):
            out.append(fn)
    if only:
        out = [x for x in out if x in only]
    return out


def describe(rel, r):
    uid = r["uid"]
    jp = r["jp"]
    bits = []
    if rel.startswith("script/"):
        bits.append("说话人:" + (r.get("speaker") or "-"))
        bits.append("行数:" + r.get("lines", "1"))
        kind = r.get("kind", "dialog")
        if kind != "dialog":
            bits.append({"memo": "类型:备忘录", "info": "类型:词条解释",
                         "name": "类型:显示名"}.get(kind, "类型:" + kind))
    elif rel == "ui_text.csv":
        bits.append("类型:界面文字")
    elif rel in ("item_text.csv", "global_text.csv"):
        bits.append("类型:数据文本")
        try:
            bits.append("字节上限:%d" % (int(r.get("max_bytes", "0")) - 1))
        except ValueError:
            bits.append("字节上限:?")
        if r.get("full_source_context"):
            bits.append("注意:这是长文的一部分")
    elif rel == "glossary_terms.csv":
        bits.append("类型:术语")
    elif rel == "glossary_speakers.csv":
        bits.append("类型:人名")
    keep = ("keep-tags", "keep-terms", "src-lines", "src-longest-line")
    for seg in r.get("note", "").split("; "):
        if seg.startswith(keep):             # prose notes are already said in Chinese
            bits.append(seg)
    return "@%s  %s%s%s" % (uid, "  ".join(bits), NL, jp)


def main(argv):
    exportdir, outdir = argv[1], argv[2]
    budget = 12000
    only = None
    if "--chars" in argv:
        budget = int(argv[argv.index("--chars") + 1])
    if "--only" in argv:
        only = argv[argv.index("--only") + 1].split(",")
    exclude = []
    if "--exclude" in argv:
        exclude = argv[argv.index("--exclude") + 1].split(",")
    os.makedirs(outdir, exist_ok=True)

    gloss = {}
    for g in ("glossary_terms.csv", "glossary_speakers.csv"):
        p = os.path.join(exportdir, g)
        if os.path.exists(p):
            for r in load(p):
                if r["zh"].strip():
                    gloss[r["jp"]] = r["zh"].strip()

    # Menu labels, item data, help text and glossary entries repeat verbatim
    # across files -- 49% of the non-dialogue rows are duplicates.  Translating
    # each one once keeps the wording consistent and cuts the volume.  Dialogue
    # is left alone: the same line may legitimately read differently per scene.
    seen = {}
    for rel in sources(exportdir, only):
        for r in load(os.path.join(exportdir, rel.replace("/", os.sep))):
            if not dedupable(rel, r):
                continue
            if r["zh"].strip():
                continue
            cap = int(r.get("max_bytes") or 10 ** 9)
            prev = seen.get(r["jp"])
            if prev is None or cap < prev[0]:
                seen[r["jp"]] = (cap, r["uid"])
    keep_uid = {v[1] for v in seen.values()}
    dropped = 0

    index = []
    for rel in sources(exportdir, only):
        rows = [r for r in load(os.path.join(exportdir, rel.replace("/", os.sep)))
                if not r["zh"].strip()]
        if exclude:
            rows = [r for r in rows
                    if not any(x in (r.get("sample_file") or "") for x in exclude)]
        before = len(rows)
        rows = [r for r in rows
                if not dedupable(rel, r) or r["uid"] in keep_uid]
        dropped += before - len(rows)
        if not rows:
            continue
        stem = rel.replace("/", "_").replace(".csv", "")
        state = {"batch": [], "size": 0, "n": 0}

        def flush():
            if not state["batch"]:
                return
            state["n"] += 1
            name = "%s_%03d.txt" % (stem, state["n"])
            body = NL.join(state["batch"])
            terms = [(k, v) for k, v in gloss.items() if k in body]
            head = ["### 批次 %s   来源 %s   共 %d 条"
                    % (name, rel, sum(1 for x in state["batch"] if x.startswith("@")))]
            if terms:
                head += ["", "# 已定译名（本批出现，必须照用）"]
                for k, v in sorted(terms, key=lambda x: -len(x[0])):
                    head.append("%s = %s" % (k, v))
            head += ["", "# 待译原文", ""]
            io.open(os.path.join(outdir, name), "w", encoding="utf-8",
                    newline=NL).write(NL.join(head) + NL + body + NL)
            index.append([name, rel,
                          sum(1 for x in state["batch"] if x.startswith("@")),
                          state["size"]])
            state["batch"], state["size"] = [], 0

        for r in rows:
            if state["size"] and state["size"] + len(r["jp"]) > budget:
                flush()
            state["batch"].append(describe(rel, r))
            state["batch"].append("")
            state["size"] += len(r["jp"])
        flush()

    with io.open(os.path.join(outdir, "_index.csv"), "w",
                 encoding="utf-8-sig", newline="") as f:
        cw = csv.writer(f, lineterminator="\r\n")
        cw.writerow(["batch", "source", "items", "jp_chars"])
        cw.writerows(index)
    if dropped:
        print("deduplicated %s repeated rows "
              "(one translation will be copied to all of them)" % format(dropped, ","))
    print("%d batches, %s untranslated rows, %s JP characters -> %s"
          % (len(index), format(sum(x[2] for x in index), ","),
             format(sum(x[3] for x in index), ","), outdir))


if __name__ == "__main__":
    main(sys.argv)
