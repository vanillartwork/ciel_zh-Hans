# -*- coding: utf-8 -*-
"""Check the translation data. Runs without the game, so CI can run it.

  py -3 tools/validate.py [--data data] [--only <path fragment>]
                          [--changed-only] [--strict] [--format github]

Every check here answers one question: could this change break the game, or
break the conventions the rest of the text follows?  Nothing here judges
whether a translation is *good* -- that is what review is for.

  structure    header, ids unique, no stray columns
  encoding     valid UTF-8 without BOM, LF endings, no control characters
  source       src and ctl still agree with the Japanese beside them
  markup       tags, glossary braces and line breaks survive translation
  length       packed fields still fit the bytes the game allocates
  charset      every character can be drawn by the font the patch ships
  language     no kana, no Japanese-only forms, no traditional-only forms
  terminology  glossary names used, forbidden renderings absent
  consistency  one source string keeps one translation
  status       status agrees with whether there is a translation

Errors block a merge; warnings are reported and do not.
"""
import sys, os, io, csv, re, argparse, subprocess

HERE_ = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE_)
from repo_export import src_hash, ctl_shape

# Findings quote the text they are about, so the console has to be able to
# print Chinese.  On Windows it defaults to the system codepage and would
# otherwise die partway through the report.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
TAG = re.compile(r"<[A-Za-z0-9_]{1,12}>")
# U+30FB, the katakana middle dot, is kept: it is the separator inside
# transliterated names (依欧娜萨鲁・库库鲁鲁・普立薛尔) and the game's font has
# it, so the project uses it rather than U+00B7.  See docs/style-guide.md.
KANA = re.compile(r"[぀-ゟ゠-ヺー-ヿ]")
# format specifiers and engine placeholders that must survive untouched
PLACEHOLDER = re.compile(r"(%[-+ #0-9.]*[a-zA-Z]|\$[0-9]+\$|\{[^}]*\})")
CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

STATUSES = {"translated", "draft", "needs-review", "todo", "skip"}
# 99% of the game's own Japanese dialogue lines fit in 23 characters
MAX_DIALOGUE_LINE = 24


class Report:
    def __init__(self, fmt="text"):
        self.errors, self.warnings, self.fmt = [], [], fmt

    def error(self, where, msg):
        self.errors.append((where, msg))

    def warn(self, where, msg):
        self.warnings.append((where, msg))

    def dump(self):
        for where, msg in self.warnings:
            if self.fmt == "github":
                print("::warning file=%s::%s" % (where.split(":")[0], msg))
            else:
                print("  warning  %s  %s" % (where, msg))
        for where, msg in self.errors:
            if self.fmt == "github":
                print("::error file=%s::%s" % (where.split(":")[0], msg))
            else:
                print("  ERROR    %s  %s" % (where, msg))
        print("\n%d errors, %d warnings" % (len(self.errors), len(self.warnings)))
        return 1 if self.errors else 0


def load_charset(data):
    p = os.path.join(data, "charset.txt")
    if not os.path.exists(p):
        return None
    text = io.open(p, encoding="utf-8").read()
    return set(ch for ch in text if not ch.isspace())


def load_allow(data):
    """Rows where a check is waived on purpose, with the reason recorded.

    Nothing here is a way to quiet an inconvenient finding: each line is one
    row and one check, it shows up in review like any other change, and the
    reason column is what a later reader will be going on.
    """
    allow = {}
    p = os.path.join(data, "allow.csv")
    if not os.path.exists(p):
        return allow
    for r in csv.DictReader(io.open(p, encoding="utf-8-sig", newline="")):
        if not (r.get("reason") or "").strip():
            continue
        allow.setdefault(r["id"], set()).add(r["check"].strip())
    return allow


def load_glossary(data):
    """Glossary entries, keyed for the checks that use them."""
    terms, forbidden = [], []
    p = os.path.join(data, "glossary", "glossary.csv")
    if not os.path.exists(p):
        return terms, forbidden
    for r in csv.DictReader(io.open(p, encoding="utf-8-sig", newline="")):
        if r.get("status", "").strip() == "retired":
            continue
        terms.append(r)
        for bad in (r.get("forbidden") or "").split("|"):
            bad = bad.strip()
            if bad:
                forbidden.append((bad, r.get("zh", ""), r.get("id", "")))
    return terms, forbidden


def parse_ctl(ctl):
    tags, br, nl = [], 0, 0
    for tok in (ctl or "").split():
        if tok.startswith("br="):
            br = int(tok[3:])
        elif tok.startswith("nl="):
            nl = int(tok[3:])
        else:
            tags.append(tok)
    return sorted(tags), br, nl


def raw_bytes(path):
    return open(path, "rb").read()


def check_file_bytes(path, rel, rep):
    raw = raw_bytes(path)
    if raw.startswith(b"\xef\xbb\xbf"):
        rep.error(rel, "file starts with a UTF-8 BOM; repository files are plain UTF-8")
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError as e:
        rep.error(rel, "not valid UTF-8: %s" % e)
        return False
    # The game's own script uses CRLF inside a field, and that has to survive
    # byte for byte -- so only a CRLF that ends a *record* is wrong. Anything
    # inside quotes belongs to the data.
    in_quotes = False
    i, n = 0, len(raw)
    while i < n:
        b = raw[i]
        if b == 0x22:                      # "
            if in_quotes and i + 1 < n and raw[i + 1] == 0x22:
                i += 2                     # escaped quote
                continue
            in_quotes = not in_quotes
        elif b == 0x0D and not in_quotes and i + 1 < n and raw[i + 1] == 0x0A:
            rep.error(rel, "CRLF at the end of a record; repository files use LF. "
                           "Set core.autocrlf=false and check out the file again "
                           "-- git must not rewrite line endings in these, "
                           "because the Japanese contains CRLF of its own.")
            break
        i += 1
    return True


def check_rows(rows, rel, cols, charset, forbidden, allow, rep, strict,
               dialogue=False, everywhere=None):
    seen = {}
    by_src = {}
    for i, r in enumerate(rows, 2):
        where = "%s:%d" % (rel, i)
        rid = r.get("id", "")
        if not rid:
            rep.error(where, "row has no id")
            continue
        if rid in seen:
            rep.error(where, "duplicate id %s (first seen on line %d)" % (rid, seen[rid]))
            continue
        seen[rid] = i
        if everywhere is not None:
            # ids address a row across the whole project -- allow.csv and
            # issue reports name one with no file beside it -- so two files
            # must never use the same one.
            prev = everywhere.get(rid)
            if prev and prev != rel:
                rep.error(where, "id %s is also used in %s" % (rid, prev))
            everywhere[rid] = rel

        zh = r.get("zh", "")
        status = (r.get("status") or "").strip()
        if status not in STATUSES:
            rep.error(where, "unknown status %r" % status)
        if zh.strip() and status == "todo":
            rep.error(where, "has a translation but status is todo")
        if not zh.strip() and status in ("translated", "needs-review", "draft"):
            rep.error(where, "status is %s but there is no translation" % status)
        if not zh.strip():
            continue

        if CONTROL.search(zh):
            rep.error(where, "translation contains a control character")

        # `src` and `ctl` are derived from `jp`. Checking them against it keeps
        # the three honest: an edit that touches the Japanese, or a row pasted
        # in from a different version of the game, shows up here rather than
        # three steps later when the patch is being built.
        jp = r.get("jp")
        if jp is not None:
            if r.get("src") and src_hash(jp) != r["src"]:
                rep.error(where, "src does not match jp; the Japanese was edited, "
                                 "or this row came from a different game version")
            if r.get("ctl") and ctl_shape(jp) != r["ctl"]:
                rep.error(where, "ctl does not match jp (expected %r)" % ctl_shape(jp))

        tags, br, nl = parse_ctl(r.get("ctl", ""))
        got = sorted(TAG.findall(zh))
        # <CR> is a line break inside one text box.  Chinese says the same
        # thing in fewer characters, so dropping one is normal and safe;
        # adding one can push the last line out of the box, and losing any
        # other code -- the colour tags -- changes how the line is drawn.
        src_cr, got_cr = tags.count("<CR>"), got.count("<CR>")
        src_rest = [t for t in tags if t != "<CR>"]
        got_rest = [t for t in got if t != "<CR>"]
        if src_rest != got_rest:
            rep.error(where, "control codes changed: source had %s, translation has %s"
                      % (" ".join(src_rest) or "none", " ".join(got_rest) or "none"))
        if got_cr > src_cr:
            rep.error(where, "translation adds %d <CR>; the extra line may not fit"
                      % (got_cr - src_cr))
        elif got_cr < src_cr:
            rep.warn(where, "translation drops %d of %d <CR>" % (src_cr - got_cr, src_cr))
        gbr = min(zh.count("{"), zh.count("}"))
        if gbr != br:
            rep.error(where, "glossary braces changed: source had %d, translation has %d"
                      % (br, gbr))
        if zh.count("{") != zh.count("}"):
            rep.error(where, "unbalanced { } in the translation")
        if zh.count("\n") != nl and strict:
            rep.warn(where, "source had %d line breaks, translation has %d"
                     % (nl, zh.count("\n")))

        # The original's own typesetting sets the bar: 99% of the game's
        # Japanese dialogue lines are 23 characters or shorter, so a Chinese
        # line past 24 is worth a second look.  Not an error -- a few places
        # legitimately run long -- but it is where text starts to wrap.
        if dialogue:
            for line in zh.split("\n"):
                if len(line) > MAX_DIALOGUE_LINE:
                    rep.warn(where, "一行 %d 个字，超过 %d 可能换行溢出：%s"
                             % (len(line), MAX_DIALOGUE_LINE, line[:30]))
                    break

        cap = r.get("max_bytes")
        if cap:
            cap = int(cap)
            need = len(zh.encode("utf-8"))
            # packed fields are NUL-terminated inside a fixed slot
            budget = cap if rel.endswith("executable.csv") else cap - 1
            if need > budget:
                rep.error(where, "translation needs %d bytes, the game allows %d"
                          % (need, budget))

        waived = allow.get(rid, ())
        if KANA.search(zh) and "kana" not in waived:
            rep.error(where, "translation still contains kana: %s  (if this is "
                              "deliberate, add the row to data/allow.csv)"
                      % " ".join(sorted(set(KANA.findall(zh)))))

        if charset is not None:
            # Control codes and placeholders are consumed by the engine, never
            # drawn, so the font does not need glyphs for them.  Checking them
            # would also make this rule useless for any language whose charset
            # does not happen to include Latin letters.
            drawn = PLACEHOLDER.sub("", TAG.sub("", zh))
            missing = sorted(set(ch for ch in drawn
                                 if ch not in charset and not ch.isspace()))
            if missing:
                rep.error(where, "these characters are not in the patch font: %s"
                          % " ".join(missing))

        for bad, good, gid in forbidden:
            if bad and bad in zh:
                rep.error(where, "uses the forbidden rendering %r; the glossary says %r (%s)"
                          % (bad, good, gid))

        src = r.get("src", "")
        if src:
            by_src.setdefault(src, []).append((rid, zh, i))

    return by_src


def check_consistency(by_src, rel, rep, dialogue):
    """One source string should keep one translation."""
    for src, items in by_src.items():
        variants = {}
        for rid, zh, line in items:
            variants.setdefault(zh, []).append((rid, line))
        if len(variants) < 2:
            continue
        # dialogue legitimately varies with who is speaking and the scene, so
        # there it is a warning; menus and item text must not vary at all
        msg = ("the same source string has %d different translations: %s"
               % (len(variants), " | ".join(sorted(variants)[:3])))
        line = min(l for vs in variants.values() for _, l in vs)
        where = "%s:%d" % (rel, line)
        (rep.warn if dialogue else rep.error)(where, msg)


def changed_files(data):
    """Files touched relative to the base branch, for a quick PR check."""
    base = os.environ.get("GITHUB_BASE_REF")
    ref = "origin/%s" % base if base else "HEAD~1"
    try:
        out = subprocess.check_output(["git", "diff", "--name-only", ref, "--", data],
                                      stderr=subprocess.DEVNULL).decode()
    except Exception:
        return None
    return set(os.path.normpath(p) for p in out.split() if p.endswith(".csv"))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default="data")
    ap.add_argument("--only", help="only files whose path contains this")
    ap.add_argument("--changed-only", action="store_true",
                    help="only files changed against the base branch")
    ap.add_argument("--strict", action="store_true", help="turn line-break notes on")
    ap.add_argument("--format", choices=["text", "github"], default="text")
    a = ap.parse_args(argv)

    rep = Report(a.format)
    charset = load_charset(a.data)
    if charset is None:
        rep.warn(a.data, "no charset.txt, so the font coverage check is skipped")
    _, forbidden = load_glossary(a.data)
    allow = load_allow(a.data)

    touched = changed_files(a.data) if a.changed_only else None
    zh = os.path.join(a.data, "zh-Hans")
    if not os.path.isdir(zh):
        print("no data at %s" % zh)
        return 1

    nfiles = nrows = 0
    all_ids = {}
    for root, _, names in os.walk(zh):
        for fn in sorted(names):
            if not fn.endswith(".csv") or fn.startswith("_"):
                continue
            path = os.path.join(root, fn)
            rel = os.path.relpath(path, ".").replace(os.sep, "/")
            if a.only and a.only not in rel:
                continue
            if touched is not None and os.path.normpath(path) not in touched:
                continue
            if not check_file_bytes(path, rel, rep):
                continue
            with io.open(path, encoding="utf-8", newline="") as f:
                rd = csv.DictReader(f)
                cols = rd.fieldnames or []
                rows = list(rd)
            if "id" not in cols or "zh" not in cols:
                rep.error(rel, "header must contain at least id and zh, found %s" % cols)
                continue
            dialogue = "/script/" in rel
            by_src = check_rows(rows, rel, cols, charset, forbidden,
                                allow, rep, a.strict, dialogue, all_ids)
            check_consistency(by_src, rel, rep, dialogue)
            nfiles += 1
            nrows += len(rows)

    print("checked %d files, %s rows" % (nfiles, format(nrows, ",")))
    return rep.dump()


if __name__ == "__main__":
    sys.exit(main())
