# -*- coding: utf-8 -*-
"""Turn the working export tree into the files that are published in the repo.

  py -3 repo_export.py <working export dir> <repo data dir>

Each row carries the Japanese source beside the translation, so that a
translator or proofreader can read both without needing anything else, and so
that a pull request shows what was actually being translated.  See
docs/translation-data.md, and NOTICE.md for what that means for copyright.

Columns published per row:

  id      stable key, `archive/path#row#column`
  jp      the Japanese source, as the game stores it
  zh      the translation
  status  translated | draft | needs-review | todo | skip
  src     first 10 hex digits of SHA-1 over `jp`
  ctl     the control codes, brace pairs and line breaks `jp` contains
  ...     per-kind extras: speaker for dialogue, max_bytes for packed fields

`src` and `ctl` are derived from `jp` and are checked against it, so they are
not a second source of truth -- they are there so that a mismatch between the
repository and a particular installation of the game is something a tool can
point at, rather than something a person has to notice.

Rows with no translation yet are published too, so that the work that is left
is visible in the repository rather than only in someone's local checkout.
"""
import sys, os, io, csv, hashlib, re

KINDS = {
    "script": ["id", "jp", "zh", "status", "speaker", "src", "ctl", "lines", "note"],
    "ui": ["id", "jp", "zh", "status", "attr", "src", "ctl", "note"],
    "packed": ["id", "jp", "zh", "status", "max_bytes", "src", "ctl", "occurrences", "note"],
    "exe": ["id", "jp", "zh", "status", "max_bytes", "src", "ctl", "occurrences", "note"],
    "glossary": ["id", "jp", "zh", "status", "kind", "src", "ctl", "occurrences", "note"],
    "settings": ["id", "jp", "zh", "status", "max_chars", "src", "ctl", "kind", "note"],
}

TAG = re.compile(r"<[A-Za-z0-9_]{1,12}>")


def src_hash(text):
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:10]


def ctl_shape(text):
    """The technical shape of a source string, without the string.

    This is what lets a pull request be checked without anybody -- including
    the CI runner -- holding a copy of the game's script: the tags, the number
    of glossary braces and the number of line breaks all have to survive
    translation, and all three can be compared against this.
    """
    parts = sorted(TAG.findall(text))
    parts.append("br=%d" % min(text.count("{"), text.count("}")))
    parts.append("nl=%d" % text.count("\n"))
    return " ".join(parts)


def status_of(row):
    if not row.get("zh", "").strip():
        # The reason for leaving a string alone is not always the first thing
        # in the note -- "多行  不修改：开发期测试字符串" put two deliberate
        # skips into the "still to do" count and contradicted their own note.
        return "skip" if "不修改" in row.get("note", "") else "todo"
    return "translated"


def read(path):
    with io.open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write(path, cols, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with io.open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in cols})
    return len(rows)


def convert(rows, kind, id_field="key"):
    out = []
    for r in rows:
        rid = r.get(id_field) or r.get("uid")
        jp = r.get("jp", "")
        rec = {
            "id": rid,
            "jp": jp,
            "src": src_hash(jp),
            "ctl": ctl_shape(jp),
            "zh": r.get("zh", ""),
            "status": status_of(r),
            "note": r.get("note", ""),
        }
        for extra in ("speaker", "lines", "attr", "max_bytes", "max_chars",
                      "occurrences", "kind"):
            if extra in r:
                rec[extra] = r[extra]
        # the speaker is published as the Chinese name: it is our own text and
        # it is what a proofreader needs in order to judge register
        out.append(rec)
    return out


def main(exportdir, datadir):
    zh = os.path.join(datadir, "zh-Hans")
    total = 0
    index = []

    scriptdir = os.path.join(exportdir, "script")
    speakers = {}
    for r in read(os.path.join(exportdir, "glossary_speakers.csv")):
        if r["zh"].strip():
            speakers[r["jp"]] = r["zh"]

    for fn in sorted(os.listdir(scriptdir)):
        if not fn.endswith(".csv"):
            continue
        rows = read(os.path.join(scriptdir, fn))
        rec = convert(rows, "script")
        for a, b in zip(rec, rows):
            a["speaker"] = speakers.get(b.get("speaker", ""), b.get("speaker", ""))
        n = write(os.path.join(zh, "script", fn), KINDS["script"], rec)
        total += n
        index.append(("script/" + fn, n))

    simple = [
        ("ui_text.csv", "ui.csv", "ui"),
        ("item_text.csv", "items.csv", "packed"),
        ("global_text.csv", "global.csv", "packed"),
        ("exe_text.csv", "executable.csv", "exe"),
        ("env_text.csv", "settings.csv", "settings"),
    ]
    for srcname, dstname, kind in simple:
        p = os.path.join(exportdir, srcname)
        if not os.path.exists(p):
            continue
        rows = read(p)
        idf = "key" if "key" in (rows[0] if rows else {}) else "uid"
        n = write(os.path.join(zh, dstname), KINDS[kind], convert(rows, kind, idf))
        total += n
        index.append((dstname, n))

    for srcname, dstname in [("glossary_terms.csv", "terms-in-text.csv"),
                             ("glossary_speakers.csv", "speakers.csv")]:
        p = os.path.join(exportdir, srcname)
        if not os.path.exists(p):
            continue
        rows = read(p)
        idf = "key" if "key" in (rows[0] if rows else {}) else "uid"
        n = write(os.path.join(zh, dstname), KINDS["glossary"], convert(rows, "glossary", idf))
        total += n
        index.append((dstname, n))

    with io.open(os.path.join(zh, "_index.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["file", "rows"])
        w.writerows(sorted(index))

    print("%d files, %d rows -> %s" % (len(index), total, zh))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
