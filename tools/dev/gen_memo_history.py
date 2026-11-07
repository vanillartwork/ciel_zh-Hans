# -*- coding: utf-8 -*-
"""Rebuild data/zh-Hans/_memo_history.csv from the release tags.

  py -3 tools/dev/gen_memo_history.py <git checkout> [tag ...]

Lists every memo translation a release shipped that differs from today's, so
that old_memos.py can map what those releases wrote into saves.  Which rows are
memos comes from the build's export (build/work/script.zip, kind=memo); run a build
first.  Without tags, every v* tag of the checkout is read.
"""
import csv, glob, io, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import workscript      # noqa: E402
OUT = os.path.join(ROOT, "data", "zh-Hans", "_memo_history.csv")


def git(repo, *args):
    return subprocess.run(["git", "-C", repo] + list(args), capture_output=True,
                          check=True).stdout


def main(argv):
    repo = argv[1]
    tags = argv[2:] or [t for t in git(repo, "tag").decode().split() if t.startswith("v")]
    memo = {}
    for _name, data in workscript.read_all(os.path.join(ROOT, "build", "work")):
        for r in workscript.rows(data):
            if r.get("kind") == "memo":
                memo[r["key"]] = r["jp"]
    if not memo:
        print("no memo rows in build/work; run a build first")
        return 1
    now = {}
    for p in glob.glob(os.path.join(ROOT, "data", "zh-Hans", "script", "*.csv")):
        with io.open(p, encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                if r["id"] in memo:
                    now[r["id"]] = r["zh"]
    rows, seen = [], set()
    for tag in sorted(tags):
        names = git(repo, "ls-tree", "--name-only", tag, "data/zh-Hans/script/").decode().split()
        for name in names:
            if not name.endswith(".csv"):
                continue
            text = git(repo, "show", "%s:%s" % (tag, name)).decode("utf-8-sig")
            for r in csv.DictReader(io.StringIO(text, newline="")):
                rid, zh = r.get("id"), r.get("zh", "")
                if rid in memo and zh and zh != now.get(rid) and (rid, zh) not in seen:
                    seen.add((rid, zh))
                    rows.append(dict(id=rid, jp=memo[rid], zh=zh, release=tag))
    with io.open(OUT, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["id", "jp", "zh", "release"], lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    print("%d earlier memo translations from %s -> %s" % (len(rows), ", ".join(sorted(tags)), OUT))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
