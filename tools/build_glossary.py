# -*- coding: utf-8 -*-
"""Assemble the published glossary from the working project's own sources.

  py -3 build_glossary.py <working export dir> <tools dir> <repo data dir>

The glossary is the one place where the game's Japanese is published in full,
and deliberately so: it is a few hundred proper nouns, it is what a new
contributor needs before writing a single line, and it is what validate.py
checks translations against.  It is reference material about the work, not a
copy of the work.

Three things feed it:

  official_glossary.csv  names as Koei Tecmo published them in Chinese, which
                         settle any argument about how a name is written
  glossary_terms.csv     terms the game itself marks with {braces}
  fix_names.py           the wrong spellings that have actually turned up in
                         this project's own drafts -- those become the
                         `forbidden` column, so the same mistake cannot be
                         merged twice
"""
import sys, os, io, csv, re, importlib.util

COLS = ["id", "source", "zh", "kind", "category", "variants", "forbidden",
        "context", "note", "authority", "status"]


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def slug(jp, used):
    """A short stable id: readable where it can be, unique always."""
    base = re.sub(r"[^A-Za-z0-9]+", "-", jp).strip("-").lower()
    if not base or len(base) < 2:
        import hashlib
        base = hashlib.sha1(jp.encode("utf-8")).hexdigest()[:8]
    cand, n = base, 2
    while cand in used:
        cand, n = "%s-%d" % (base, n), n + 1
    used.add(cand)
    return cand


def read(path):
    if not os.path.exists(path):
        return []
    return list(csv.DictReader(io.open(path, encoding="utf-8-sig", newline="")))


def main(exportdir, toolsdir, datadir):
    fix = load_module(os.path.join(toolsdir, "fix_names.py"), "fix_names")
    # official -> the wrong spellings that have been seen for it
    forbidden = {}
    for bad, good in fix.VARIANTS.items():
        forbidden.setdefault(good, []).append(bad)

    rows, used, seen = [], set(), set()

    for r in read(os.path.join(exportdir, "official_glossary.csv")):
        jp, zh = r["jp"], r.get("zh_cn", "")
        if not zh or jp in seen:
            continue
        seen.add(jp)
        rows.append({
            "id": slug(jp, used), "source": jp, "zh": zh,
            "kind": r.get("kind", ""), "category": "official",
            "variants": r.get("zh_tw_as_published", ""),
            "forbidden": "|".join(sorted(forbidden.get(zh, []))),
            "context": "", "note": "",
            "authority": "光荣特库摩台湾官方公开资料", "status": "fixed",
        })

    for r in read(os.path.join(exportdir, "glossary_speakers.csv")):
        jp, zh = r["jp"], r.get("zh", "")
        if not zh or jp in seen:
            continue
        seen.add(jp)
        rows.append({
            "id": slug(jp, used), "source": jp, "zh": zh,
            "kind": "character", "category": "speaker",
            "variants": "", "forbidden": "|".join(sorted(forbidden.get(zh, []))),
            "context": "说话人名牌，%s 次" % r.get("occurrences", "?"),
            "note": r.get("chara_id", ""),
            "authority": "官方" if "官方" in r.get("note", "") else "本项目",
            "status": "fixed" if "官方" in r.get("note", "") else "agreed",
        })

    for r in read(os.path.join(exportdir, "glossary_terms.csv")):
        jp, zh = r["jp"], r.get("zh", "")
        if not zh or jp in seen:
            continue
        seen.add(jp)
        rows.append({
            "id": slug(jp, used), "source": jp, "zh": zh,
            "kind": r.get("kind", "term"), "category": "in-text-marker",
            "variants": "", "forbidden": "|".join(sorted(forbidden.get(zh, []))),
            "context": "游戏用 {} 标出的术语，%s 次" % r.get("occurrences", "?"),
            "note": "", "authority": "官方" if "官方" in r.get("note", "") else "本项目",
            "status": "fixed" if "官方" in r.get("note", "") else "agreed",
        })

    # anything fix_names.py knows about that nothing above covers
    for bad, good in sorted(fix.VARIANTS.items()):
        if any(r["zh"] == good for r in rows):
            continue
        rows.append({
            "id": slug(good, used), "source": "", "zh": good,
            "kind": "name", "category": "project-decision", "variants": "",
            "forbidden": bad, "context": "", "note": "由 fix_names.py 历史记录导入",
            "authority": "本项目", "status": "agreed",
        })

    out = os.path.join(datadir, "glossary", "glossary.csv")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with io.open(out, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS, lineterminator="\n")
        w.writeheader()
        w.writerows(sorted(rows, key=lambda r: (r["category"], r["id"])))
    nf = sum(1 for r in rows if r["forbidden"])
    print("%d glossary entries (%d with forbidden renderings) -> %s"
          % (len(rows), nf, out))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
