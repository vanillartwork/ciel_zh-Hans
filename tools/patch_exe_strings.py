# -*- coding: utf-8 -*-
"""Translate the Japanese strings that are compiled into the executable.

  py -3 patch_exe_strings.py <in exe> <out exe> [--dry] [--csv <exe_text.csv>]

These live in .rdata as NUL-terminated UTF-8 and are reached by RIP-relative
leas scattered through the code, so moving them would mean finding and
repointing every reference.  Overwriting in place avoids all of that, at the
cost of a hard rule: the Chinese must not be longer in UTF-8 than the Japanese
it replaces.  The leftover bytes are filled with NULs, which simply shortens
the string.

Translations come from data/zh-Hans/executable.csv by way of a build, so
they go through the same review and validation path as the rest of the
project.  A row with an empty
`zh` is left in Japanese on purpose; `note` says why.

A match only counts when the bytes form a whole string -- NUL on both sides --
so a short entry can never be rewritten inside a longer one, and a table entry
like "食器洗い" never eats into "食器洗い。空の食べ物を流しへ入れる".
"""
import sys, os, io, csv

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
# The repository stores translations without the Japanese, so the working file
# this tool needs is the one a build produces out of the player's own game.
DEFAULT_CSV = os.path.join(ROOT, "build", "work", "exe_text.csv")


def resolve_csv(path=None):
    if path:
        return path
    if os.path.exists(DEFAULT_CSV):
        return DEFAULT_CSV
    raise SystemExit(
        "No exe_text.csv to work from.\n"
        "It is produced from your own copy of the game, because the repository\n"
        "does not carry the game's Japanese text. Run a build first:\n"
        "    py -3 tools/build.py --no-repack\n"
        "or point at one with --csv <path>.")


def load(csv_path):
    """Rows to patch, plus the ones deliberately left alone."""
    rows = list(csv.DictReader(io.open(csv_path, encoding="utf-8-sig", newline="")))
    todo, skipped = [], []
    for r in rows:
        if r["zh"].strip():
            todo.append((r["uid"], r["jp"], r["zh"], int(r["max_bytes"])))
        else:
            skipped.append((r["uid"], r["note"]))
    return rows, todo, skipped


def check(todo):
    """Every translation must fit in the bytes the original occupies."""
    bad = []
    for uid, jp, zh, cap in todo:
        n = len(zh.encode("utf-8"))
        if n > cap:
            bad.append((uid, jp, zh, cap, n))
    return bad


def whole_string_spans(data, needle):
    """Offsets where `needle` sits as a complete NUL-terminated string."""
    out, start, n = [], 0, len(needle)
    while True:
        i = data.find(needle, start)
        if i < 0:
            return out
        start = i + 1
        if i == 0 or data[i - 1] != 0:
            continue
        if i + n >= len(data) or data[i + n] != 0:
            continue
        out.append(i)


def patch(data, todo, verbose=True):
    d = bytearray(data)
    # longest first, so a short entry never shadows a longer one
    order = sorted(todo, key=lambda t: -len(t[1]))
    done = miss = total = 0
    missing = []
    for uid, jp, zh, cap in order:
        jb, zb = jp.encode("utf-8"), zh.encode("utf-8")
        spans = whole_string_spans(d, jb)
        if not spans:
            miss += 1
            missing.append(uid)
            continue
        for off in spans:
            d[off:off + len(jb)] = zb + bytes(len(jb) - len(zb))
            total += 1
        done += 1
    if verbose and missing:
        print("  %d strings not found in this executable: %s"
              % (miss, ", ".join(missing[:12]) + (" ..." if miss > 12 else "")))
    return bytes(d), done, miss, total


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    dry = "--dry" in argv
    csv_path = None
    if "--csv" in argv:
        csv_path = argv[argv.index("--csv") + 1]
        args = [a for a in args if a != csv_path]
    csv_path = resolve_csv(csv_path)
    src, dst = args[0], args[1]

    rows, todo, skipped = load(csv_path)
    bad = check(todo)
    if bad:
        for uid, jp, zh, cap, n in bad:
            print("TOO LONG  %s  %r -> %r  (%d > %d bytes)" % (uid, jp, zh, n, cap))
        return 1
    unexplained = [uid for uid, note in skipped if not note.strip()]
    if unexplained:
        print("%d untranslated rows have no note saying why: %s"
              % (len(unexplained), ", ".join(unexplained[:10])))
        return 1

    src_bytes = open(src, "rb").read()
    out, done, miss, total = patch(src_bytes, todo)
    print("%d of %d strings translated, %d occurrences rewritten; %d rows left "
          "in Japanese on purpose%s"
          % (done, len(todo), total, len(skipped), "  (dry run)" if dry else ""))
    if len(out) != len(src_bytes):
        print("size changed -- refusing to write")
        return 1
    if miss:
        print("%d strings were not found; is this the supported build?" % miss)
    if not dry:
        open(dst, "wb").write(out)
        print("exe -> %s" % dst)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
