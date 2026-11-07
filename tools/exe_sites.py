# -*- coding: utf-8 -*-
"""Translate executable strings at reviewed addresses only.

  py -3 exe_sites.py --check [--data data]

patch_exe_strings.py rewrites every whole-string match of a Japanese string.
That is the right tool for text that only ever appears as display text, and
the wrong one for everything else: a reverse-engineering note can show that
the string at one address is only ever formatted onto the screen, and say
nothing about another copy of the same bytes elsewhere in .rdata that the game
compares against.  イオン shipped broken in 0.9.4 for exactly that reason.

So the strings handled here are split in two:

  data/zh-Hans/exe_sited.csv          what each string says in Chinese, once
                                      per wording (id, jp, zh, max_bytes, ...)
  data/exe-sites/<version>.csv        where it may be written, one row per
                                      address, for one exact executable

A translation gives no permission to write anything.  A manifest row does, and
only for its own address: the build writes the bytes at that RVA after checking
that they are still the Japanese the row was reviewed against, and leaves every
other copy of the same text alone.  Ids named by a manifest are also taken out
of patch_exe_strings.py's global pass, so neither path can reach the other's
strings.

Manifest columns:

  id        translation id, exe_sited.csv or executable.csv
  rva       where the string starts
  bytes     its length in UTF-8, without the NUL -- the room the Chinese has
  sha256    first 16 hex digits of the SHA-256 of those bytes
  use       display    shown after formatting or set on a widget
            persisted  also written into the save file (see PERSISTED below)
  evidence  who reads it and why that makes it display text

Every row is checked against the unmodified input before anything is written,
and all rows are written in one pass, so a build either applies the whole
reviewed set or none of it.

Format strings: an in-place translation keeps its printf conversions in the
same order with the same flags, and is never longer in bytes.  Together those
mean the formatted result can never be longer than the original's for the same
arguments, so whatever buffer the game formats into still holds it.  A string
the game passes *as* a format with no arguments (the chapter names, the task
names) obeys the same rule with an empty conversion list, which is what keeps
a stray % out of it.
"""
import argparse, csv, hashlib, io, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SITES_DIR = os.path.join(ROOT, "data", "exe-sites")
SITED_CSV = os.path.join(ROOT, "data", "zh-Hans", "exe_sited.csv")
EXE_CSV = os.path.join(ROOT, "data", "zh-Hans", "executable.csv")
VERSIONS = os.path.join(ROOT, "data", "game-versions.csv")
EXE_NAME = "CielnosurgeDX.exe"
COLS = ["id", "rva", "bytes", "sha256", "use", "evidence"]
USES = ("display", "persisted")

# printf conversions as the MSVC runtime reads them, plus a literal %%
SPEC = re.compile(r"%(?:%|[-+ #0]*(?:\*|\d+)?(?:\.(?:\*|\d+))?"
                  r"(?:hh|h|ll|l|I64|I32|I|z|j|t|L|w)?[diouxXeEfFgGaAcspnSZC])")
# The save summary is split on these by the load screen: each line on "\n",
# label from value on the full-width colon, and the slot line
# "%s %s %s" on spaces.  A persisted translation keeps each of them exactly.
PERSISTED = ("\n", "：", " ")


class SiteError(Exception):
    def __init__(self, problems):
        Exception.__init__(self, "\n".join(problems))
        self.problems = problems


def text_id(jp):
    return "exe:" + hashlib.sha1(jp.encode("utf-8")).hexdigest()[:8]


def short_hash(b):
    return hashlib.sha256(b).hexdigest()[:16]


def specs(s):
    """The conversions in order, or None if a % is not part of one."""
    out, pos = [], 0
    for m in SPEC.finditer(s):
        if "%" in s[pos:m.start()]:
            return None
        out.append(m.group())
        pos = m.end()
    return None if "%" in s[pos:] else out


def read_csv(path):
    with io.open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def load_texts(paths=(SITED_CSV, EXE_CSV)):
    """id -> (jp, zh) from every file that may hold a sited translation."""
    out = {}
    for p in paths:
        if not os.path.exists(p):
            continue
        for r in read_csv(p):
            rid = r.get("id") or r.get("uid")
            if rid in out:
                raise SiteError(["%s: id %s is defined twice" % (p, rid)])
            # never strip: the save summary starts with a line break the load
            # screen counts lines by
            zh = r.get("zh", "")
            out[rid] = (r["jp"], zh if zh.strip() else "")
    return out


def load_sites(path):
    rows = read_csv(path)
    problems = []
    for i, r in enumerate(rows, 2):
        if list(r) != COLS:
            raise SiteError(["%s: columns must be %s" % (path, ",".join(COLS))])
        try:
            r["rva"] = int(r["rva"], 16)
            r["bytes"] = int(r["bytes"])
        except ValueError:
            problems.append("%s:%d: rva and bytes must be numbers" % (path, i))
        if r["use"] not in USES:
            problems.append("%s:%d: use %r is not one of %s" % (path, i, r["use"], USES))
        if not r["evidence"].strip():
            problems.append("%s:%d: no evidence for %s" % (path, i, r["id"]))
    if problems:
        raise SiteError(problems)
    return rows


def manifest_for(digest, versions=VERSIONS, sites_dir=SITES_DIR):
    """The manifest of the version whose unpatched executable has `digest`."""
    for r in read_csv(versions):
        if r["file"] == EXE_NAME and r["sha256"].lower() == digest.lower():
            p = os.path.join(sites_dir, r["version_id"] + ".csv")
            return p if os.path.exists(p) else None
    return None


def check_translation(site, jp, zh):
    """Problems with putting `zh` where `jp` was, data only."""
    out = []
    where = "%s at %#x" % (site["id"], site["rva"])
    jb = jp.encode("utf-8")
    if len(jb) != site["bytes"]:
        out.append("%s: the Japanese is %d bytes, the manifest says %d"
                   % (where, len(jb), site["bytes"]))
    if short_hash(jb) != site["sha256"]:
        out.append("%s: the Japanese does not match the manifest's sha256" % where)
    if text_id(jp) != site["id"]:
        out.append("%s: id does not belong to this Japanese" % where)
    if not zh:
        return out
    zb = zh.encode("utf-8")
    if len(zb) > len(jb):
        out.append("%s: %r needs %d bytes, %d available" % (where, zh, len(zb), len(jb)))
    if "\0" in zh:
        out.append("%s: translation contains a NUL" % where)
    sj, sz = specs(jp), specs(zh)
    if sj is None:
        out.append("%s: the Japanese has a %% that is not a conversion" % where)
    elif sz != sj:
        out.append("%s: conversions %s, translation has %s" % (where, sj, sz))
    if site["use"] == "persisted":
        for ch in PERSISTED:
            if jp.count(ch) != zh.count(ch):
                out.append("%s: persisted text has %d of %r, translation %d"
                           % (where, jp.count(ch), ch, zh.count(ch)))
    return out


def plan(data, sites, texts, locate):
    """Check every site against the unmodified `data`; the writes, or SiteError.

    `locate(rva, n)` returns (file offset, section name) for n bytes at rva.
    """
    problems, writes = [], []
    for s in sites:
        t = texts.get(s["id"])
        if t is None:
            problems.append("%s at %#x: no translation row" % (s["id"], s["rva"]))
            continue
        jp, zh = t
        problems += check_translation(s, jp, zh)
        jb = jp.encode("utf-8")
        try:
            off, sec = locate(s["rva"], len(jb) + 1)
        except Exception as e:
            problems.append("%s at %#x: %s" % (s["id"], s["rva"], e))
            continue
        if sec != ".rdata":
            problems.append("%s at %#x: in %s, not .rdata" % (s["id"], s["rva"], sec))
        if (bytes(data[off:off + len(jb)]) != jb or data[off + len(jb)] != 0
                or (off and data[off - 1] != 0)):
            problems.append("%s at %#x: the bytes there are not the reviewed "
                            "Japanese string" % (s["id"], s["rva"]))
            continue
        if zh:
            writes.append((off, jb, zh.encode("utf-8"), s["id"]))
    spans = sorted((off, off + len(jb) + 1, rid) for off, jb, _z, rid in writes)
    for (a0, a1, ra), (b0, b1, rb) in zip(spans, spans[1:]):
        if b0 < a1:
            problems.append("%s and %s overlap at file offset %#x" % (ra, rb, b0))
    if problems:
        raise SiteError(problems)
    return writes


def apply(data, writes):
    """`data` with every planned write made; refuses if a site has moved on."""
    d = bytearray(data)
    for off, jb, zb, rid in writes:
        if bytes(d[off:off + len(jb)]) != jb:
            raise SiteError(["%s: the reviewed bytes at file offset %#x were "
                             "changed before the sited pass" % (rid, off)])
        d[off:off + len(jb)] = zb + bytes(len(jb) - len(zb))
    return bytes(d)


def pe_locator(data):
    import pe_loader
    pe = pe_loader.Pe(data)

    def locate(rva, n):
        off = pe.rva_to_off(rva, n)
        for s in pe.sections():
            if s["raw"] <= off < s["raw"] + s["rsz"]:
                return off, s["name"].decode("ascii", "replace")
        raise SiteError(["RVA %#x has no section" % rva])
    return locate


def check_repo(data_dir=None):
    """What can be checked without the game: every manifest against the data."""
    zh_dir = os.path.join(data_dir, "zh-Hans") if data_dir else None
    texts = load_texts((os.path.join(zh_dir, "exe_sited.csv"),
                        os.path.join(zh_dir, "executable.csv"))
                       if zh_dir else (SITED_CSV, EXE_CSV))
    sites_dir = os.path.join(data_dir, "exe-sites") if data_dir else SITES_DIR
    problems, n = [], 0
    for fn in sorted(os.listdir(sites_dir)) if os.path.isdir(sites_dir) else ():
        if not fn.endswith(".csv"):
            continue
        sites = load_sites(os.path.join(sites_dir, fn))
        seen = set()
        for s in sites:
            if s["rva"] in seen:
                problems.append("%s: rva %#x listed twice" % (fn, s["rva"]))
            seen.add(s["rva"])
            t = texts.get(s["id"])
            if t is None:
                problems.append("%s: %s has no translation row" % (fn, s["id"]))
                continue
            problems += ["%s: %s" % (fn, p) for p in check_translation(s, *t)]
            n += 1
    return n, problems


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", required=True,
                    help="check the manifests against the translation data")
    ap.add_argument("--data", default=None)
    a = ap.parse_args(argv)
    try:
        n, problems = check_repo(a.data)
    except SiteError as e:
        problems, n = e.problems, 0
    for p in problems:
        print("ERROR  " + p)
    print("%d sited strings checked, %d problems" % (n, len(problems)))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.path.insert(0, HERE)
    sys.exit(main())
