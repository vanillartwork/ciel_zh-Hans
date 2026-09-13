# -*- coding: utf-8 -*-
"""Validate export/exe_text.csv before it is patched into the executable.

  py -3 check_exe_text.py [--csv <exe_text.csv>] [--archives] [--quiet]

The executable is the one place where a good translation can still break the
game, because the strings are overwritten in place and some of them double as
names the engine looks things up by.  Every check here exists to catch that
before a build, not to judge the Chinese.

  budget      the translation must fit in the bytes the Japanese occupies
  anchored    it must match the executable as a whole NUL-terminated string,
              never as a fragment of a longer one
  accounted   an untranslated row must carry a note saying why
  markers     <CR> and other <TAG> codes must survive unchanged
  glyphs      every character must exist in the font the patch ships
  archives    (--archives, slow) flags strings that also appear in data the
              game loads at runtime, which may mean the engine matches on
              them; .inc files are generated C++ source and are ignored

Exit status is non-zero if anything failed; warnings alone do not fail.
"""
import sys, os, io, csv, re, glob

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gamepath
from patch_exe_strings import load, whole_string_spans, resolve_csv
from build_charset import pristine_exe, gb2312_chars
import font_atlas

TAG = re.compile(r"<[A-Za-z0-9_]{1,12}>")
# runtime data: the game loads these.  .inc files are generated C++ headers
# shipped by accident, and .txt/.gbd are event scripts, where a word matching
# by chance means nothing.
RUNTIME_EXT = {".bin", ".xml"}


def check_rows(todo, skipped, exe, quiet=False):
    errors, warnings = [], []

    for uid, jp, zh, cap in todo:
        n = len(zh.encode("utf-8"))
        if n > cap:
            errors.append("%s  translation is %d bytes, budget is %d" % (uid, n, cap))
        if not whole_string_spans(exe, jp.encode("utf-8")):
            errors.append("%s  Japanese does not appear as a whole string in the "
                          "executable -- wrong build, or the row is a fragment" % uid)
        if sorted(TAG.findall(jp)) != sorted(TAG.findall(zh)):
            errors.append("%s  control codes differ: %s vs %s"
                          % (uid, TAG.findall(jp), TAG.findall(zh)))
        if jp.count("\n") != zh.count("\n"):
            warnings.append("%s  %d line breaks in Japanese, %d in Chinese"
                            % (uid, jp.count("\n"), zh.count("\n")))

    for uid, note in skipped:
        if not note.strip():
            errors.append("%s  left untranslated with no note saying why" % uid)

    return errors, warnings


def check_glyphs(todo, exe_path):
    """Every character must be drawable by the font the patch ships."""
    have = set(gb2312_chars())
    for g in font_atlas.read_table(exe_path):
        have.add(g.ch)
    missing = {}
    for uid, jp, zh, cap in todo:
        for ch in zh:
            if ch in "\r\n" or ch in have:
                continue
            missing.setdefault(ch, []).append(uid)
    return missing


# A data file's own field separators.  Only a string filling a whole field can
# be something the engine matches on; one sitting inside a sentence is just the
# same word turning up in prose, which says nothing.
FIELD_EDGE = set(b"\x00,\r\n\t")


def whole_field(data, needle):
    """True if `needle` fills an entire field somewhere in `data`."""
    start, n = 0, len(needle)
    while True:
        i = data.find(needle, start)
        if i < 0:
            return False
        start = i + 1
        before = data[i - 1] if i else 0
        after = data[i + n] if i + n < len(data) else 0
        if before in FIELD_EDGE and after in FIELD_EDGE:
            return True


def check_archives(todo, res_dir):
    """Strings that also fill a whole field in data the game loads."""
    from gustpak import Pak

    def fast_xor(data, key):
        if not any(key):
            return data
        n = len(data)
        k = (bytes(key) * (n // 20 + 2))[:n]
        return (int.from_bytes(data, "big") ^ int.from_bytes(k, "big")).to_bytes(n, "big")

    needles = [(uid, jp.encode("utf-8")) for uid, jp, zh, cap in todo]
    hits = {}
    for pak in sorted(glob.glob(os.path.join(res_dir, "PACK*.PAK"))):
        p = Pak(pak)
        for e in p.entries:
            if os.path.splitext(e.name)[1].lower() not in RUNTIME_EXT:
                continue
            p.fh.seek(p.data_start + e.offset)
            d = fast_xor(p.fh.read(e.size), e.key)
            for uid, nb in needles:
                if whole_field(d, nb):
                    hits.setdefault(uid, set()).add(e.path)
        p.close()
    return hits


def main(argv):
    csv_path = None
    if "--csv" in argv:
        csv_path = argv[argv.index("--csv") + 1]
    csv_path = resolve_csv(csv_path)
    quiet = "--quiet" in argv

    rows, todo, skipped = load(csv_path)
    exe_path = pristine_exe()
    exe = open(exe_path, "rb").read()

    errors, warnings = check_rows(todo, skipped, exe, quiet)

    missing = check_glyphs(todo, exe_path)
    for ch, uids in sorted(missing.items()):
        warnings.append("U+%04X %s is not in the font (%s)"
                        % (ord(ch), ch, ", ".join(uids[:3])))

    if "--archives" in argv:
        res = gamepath.res_dir(os.environ.get("CIEL_NOSURGE_DX"))
        hits = check_archives(todo, res)
        by = {r["uid"]: r for r in rows}
        for uid in sorted(hits):
            where = sorted(hits[uid])
            warnings.append("%s  %r also occurs in runtime data: %s"
                            % (uid, by[uid]["jp"][:24], ", ".join(where[:3])))

    print("%d rows: %d translated, %d left in Japanese on purpose"
          % (len(rows), len(todo), len(skipped)))
    for w in warnings:
        print("  warning: %s" % w)
    for e in errors:
        print("  ERROR  : %s" % e)
    print("%d errors, %d warnings" % (len(errors), len(warnings)))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
