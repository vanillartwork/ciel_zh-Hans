# -*- coding: utf-8 -*-
"""Check translated batches of the dream tables and fold them into dream.csv.

  py -3 tools/dev/import_dream_batches.py <batch.csv> [...] [--apply]

The batches are the kit made for outside translation (one CSV per batch, columns
id, kind, record, max_cjk_chars, jp, zh).  Without --apply this only reports;
with it, rows that pass every check are written into data/zh-Hans/dream.csv
and rows that fail are listed for re-translation.  A row passes when

  * its id is a dream.csv row and its jp is that row's Japanese, unchanged
  * zh is not empty and fits: UTF-8 bytes <= max_bytes - 1 of the row
  * zh keeps the Japanese's number of line breaks and of <CR> tags
  * zh holds no kana, no other tag, no NUL, no glossary do_not_use spelling
  * an ASCII prefix such as "01-00:" or "EX01-01:" survives unchanged

Reading the Chinese for quality is still a person's job; this keeps the
mechanical failures out of the data so that review is about wording.
"""
import csv, io, os, re, sys, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
DREAM = os.path.join(ROOT, "data", "zh-Hans", "dream.csv")
GLOSSARY = os.path.join(ROOT, "data", "glossary", "glossary.csv")
# same as validate.py: the katakana middle dot ・ is used in Chinese names
KANA = re.compile(r"[぀-ゟ゠-ヺー-ヿ]")
PREFIX = re.compile(r"^(EX)?\d\d-\d\d:")


def read(path, enc="utf-8-sig"):
    with io.open(path, encoding=enc, newline="") as f:
        return list(csv.DictReader(f))


def forbidden_terms():
    out = []
    for r in read(GLOSSARY):
        for bad in (r.get("forbidden") or "").split("|"):
            if bad.strip():
                out.append((bad.strip(), r["zh"]))
    return out


def check(row, repo, bad_terms):
    problems = []
    r = repo.get(row["id"])
    if r is None:
        return ["unknown id"]
    if row["jp"].replace("\r\n", "\n") != r["jp"]:
        problems.append("jp was changed")
    zh = (row.get("zh") or "").replace("\r\n", "\n")
    if not zh.strip():
        return problems + ["no translation"]
    cap = int(r["max_bytes"]) - 1
    if len(zh.encode("utf-8")) > cap:
        problems.append("%d bytes, limit %d" % (len(zh.encode("utf-8")), cap))
    if zh.count("\n") != r["jp"].count("\n"):
        problems.append("%d line breaks, Japanese has %d" % (zh.count("\n"), r["jp"].count("\n")))
    # <CR> is the game's own line break inside a text box; validate.py only
    # warns about a lost one, so it is checked here, where it can be refused
    if zh.count("<CR>") != r["jp"].count("<CR>"):
        problems.append("%d <CR>, Japanese has %d" % (zh.count("<CR>"), r["jp"].count("<CR>")))
    if KANA.search(zh):
        problems.append("kana left: %s" % "".join(sorted(set(KANA.findall(zh)))))
    if "<" in zh.replace("<CR>", "") or "\0" in zh:
        problems.append("tag or NUL")
    m = PREFIX.match(r["jp"])
    if m and not zh.startswith(m.group()):
        problems.append("prefix %s not kept" % m.group())
    for bad, good in bad_terms:
        if bad in zh:
            problems.append("uses %s, glossary says %s" % (bad, good))
    return problems


def main(argv):
    apply = "--apply" in argv
    paths = [a for a in argv[1:] if not a.startswith("--")]
    rows = read(DREAM, "utf-8")
    cols = list(rows[0].keys())
    repo = {r["id"]: r for r in rows}
    bad_terms = forbidden_terms()
    ok, failed = {}, []
    for p in paths:
        for row in read(p):
            probs = check(row, repo, bad_terms)
            if probs:
                failed.append((os.path.basename(p), row["id"], row.get("jp", "")[:20], probs))
            else:
                ok[row["id"]] = row["zh"].replace("\r\n", "\n")
    for name, rid, jp, probs in failed:
        print("REJECT  %s  %s  %s  %s" % (name, rid, jp.replace("\n", "|"), "; ".join(probs)))
    print("%d rows pass, %d rejected" % (len(ok), len(failed)))
    if apply and ok:
        stamp = datetime.date.today().isoformat()
        for r in rows:
            if r["id"] in ok:
                r["zh"], r["status"] = ok[r["id"]], "translated"
                r["note"] = "外部翻译，%s 验收" % stamp
        with io.open(DREAM, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols, lineterminator="\n")
            w.writeheader()
            w.writerows(rows)
        print("written to %s" % DREAM)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
