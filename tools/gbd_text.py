# -*- coding: utf-8 -*-
"""Text in the dream-world tables, inc/dream/*.gbd.

  py -3 gbd_text.py export <PACK01.PAK> <out dir>
  py -3 gbd_text.py verify <PACK01.PAK> <dream_text.csv>

These are arrays of fixed-size records -- one file per chapter, each holding the
records of every chapter up to it -- and none of them went through any other
part of the pipeline: the HISTORY recaps, the door subtitles, the ruin names
were all still Japanese in 0.9.7.

What is known about each record is written down in FAMILIES, and nothing else
is touched.  A field is listed only once it is known to be display text; record
names (area01, history060) and event ids (EX01_01, ME01_00H) are what the game
looks records up by and are never listed.

The room a translation has is the byte length of the Japanese it replaces, not
the distance to the next field.  These fields are not zero-padded: past a
string's NUL there are often the leftovers of whatever was written there before
(試練編第一幕：始まりの刻 is followed by イへ).  Whether the game ever reads
past the NUL is not known, so a translation overwrites exactly the bytes the
Japanese used, the NUL after them stays where it was, and the leftovers stay
too.  A translation that does not fit is reported, never cut.

Translations are kept once per wording per field (`id`), and written wherever
that wording sits in that field (`landings`): the same chapter's records repeat
in every later chapter's file.
"""
import collections, csv, hashlib, io, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# member prefix: (short name, record size, record name field,
#                 {translated field: (offset, read limit)},
#                 {blanked field: (offset, read limit)})
# The read limit is where the next known field starts; it bounds how far a
# string is looked for, and says nothing about how much may be written.  The
# record name is the ASCII id each record is known by.
#
# Where the loaders put each field (steam-2025-07):
#   event_history_data 0x610e00: +0x30 in-world time, +0x68 title, +0xa0 event
#                      id and +0xf4 summary are copied into one entry each,
#                      appended to a list in file order; nothing is keyed on
#                      the time
#   ruin_data          0x611500: +0x1c ruin id is the map key; +0x54 name and
#                      +0x8c reading are copied into the value as std::strings
#   ruin_restore_data  0x612c00: +0x3c restore id is the map key; +0x7c name,
#                      +0xcc/+0x10c part ids are copied into the value
#
# A blanked field is emptied in every record: its first byte becomes NUL and
# the rest of what the Japanese used is zeroed.  The ruin readings are kana
# glosses of the place names (ざっかや　るる　まえ); a Chinese name needs no
# gloss, and the reading is a value, not a key.  If any list orders ruins by
# reading, emptying them changes only the order shown.
FAMILIES = {
    "inc/dream/dream_area_data_": ("area", 304, (4, 24), {"title": (28, 80)}, {}),
    "inc/dream/event_history_data_": ("history", 844, (4, 24),
                                      {"time": (48, 56), "title": (104, 56),
                                       "summary": (244, 600)}, {}),
    "inc/dream/ruin_data_": ("ruin", 352, (28, 56), {"name": (84, 56)},
                             {"reading": (140, 80)}),
    "inc/dream/ruin_restore_data_": ("restore", 336, (60, 64), {"name": (124, 80)}, {}),
}
COLS = ["key", "jp", "zh", "max_bytes", "landings", "src", "note"]


class GbdError(Exception):
    pass


def family_of(path):
    p = path.lower().replace("\\", "/")
    for prefix, spec in FAMILIES.items():
        if p.startswith(prefix) and p.endswith(".gbd"):
            return spec
    return None


def cstr(rec, off, limit):
    raw = rec[off:off + limit]
    z = raw.find(b"\0")
    if z < 0:
        raise GbdError("no NUL within %d bytes of +%d" % (limit, off))
    return raw[:z]


def text_key(short, field, jp):
    return "%s.%s:%s" % (short, field, hashlib.sha1(jp.encode("utf-8")).hexdigest()[:8])


def records(data, stride):
    if len(data) % stride:
        raise GbdError("%d bytes is not a whole number of %d-byte records"
                       % (len(data), stride))
    for i in range(len(data) // stride):
        yield i, data[i * stride:(i + 1) * stride]


def fields(path, data):
    """(file offset, field, record name, Japanese) for every listed field."""
    for item in _walk(path, data, 3):
        yield item


def blanks(path, data):
    """(file offset, field, record name, Japanese) for every blanked field."""
    for item in _walk(path, data, 4):
        yield item


def _walk(path, data, which):
    spec = family_of(path)
    if spec is None:
        return
    stride, name_field, flds = spec[1], spec[2], spec[which]
    for i, rec in records(data, stride):
        name = cstr(rec, *name_field).decode("ascii")
        for field, (off, limit) in flds.items():
            raw = cstr(rec, off, limit)
            if not raw:
                continue
            yield i * stride + off, field, name, raw.decode("utf-8")


def members(pak):
    return sorted((e.path for e in pak if family_of(e.path)), key=str.lower)


def collect(pak):
    """key -> (jp, [(member, record name, field, offset)])."""
    out = collections.OrderedDict()
    for p in members(pak):
        short = family_of(p)[0]
        for off, field, name, jp in fields(p, pak.read(p)):
            k = text_key(short, field, jp)
            out.setdefault(k, (jp, []))[1].append((p.lower(), name, field, off))
    return out


def export(pak, outdir):
    from repo_export import src_hash
    rows = []
    for k, (jp, lands) in collect(pak).items():
        rows.append(dict(key=k, jp=jp, zh="", max_bytes=len(jp.encode("utf-8")) + 1,
                         landings=len(lands), src=src_hash(jp), note=""))
    path = os.path.join(outdir, "dream_text.csv")
    with io.open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS, lineterminator="\r\n")
        w.writeheader()
        w.writerows(rows)
    return path, len(rows)


def load(csv_path):
    """key -> zh for the rows that have a translation."""
    out = {}
    with io.open(csv_path, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            k = r.get("key") or r.get("id")
            if r.get("zh", "").strip():
                out[k] = (r["jp"], r["zh"])
    return out


def patch_member(path, data, trans):
    """New bytes for one member, or the original object when nothing applies.

    Raises GbdError listing every translation that does not fit.
    """
    spec = family_of(path)
    if spec is None:
        return data
    short = spec[0]
    d = bytearray(data)
    bad, touched = [], False
    for off, field, name, jp in list(fields(path, data)):
        t = trans.get(text_key(short, field, jp))
        if t is None:
            continue
        if t[0] != jp:
            bad.append("%s %s.%s: the row's Japanese is not the text in the file"
                       % (path, name, field))
            continue
        jb, zb = jp.encode("utf-8"), t[1].encode("utf-8")
        if len(zb) > len(jb):
            bad.append("%s %s.%s: %d bytes of Chinese for %d bytes of Japanese"
                       % (path, name, field, len(zb), len(jb)))
            continue
        if b"\0" in zb:
            bad.append("%s %s.%s: translation contains a NUL" % (path, name, field))
            continue
        d[off:off + len(jb)] = zb + bytes(len(jb) - len(zb))
        touched = True
    for off, field, name, jp in list(blanks(path, data)):
        n = len(jp.encode("utf-8"))
        d[off:off + n] = bytes(n)
        touched = True
    if bad:
        raise GbdError("\n".join(bad))
    return bytes(d) if touched else data


def build(pak, csv_path):
    """{member path lower: new bytes} for every member a translation or a
    blanked field changes."""
    trans = load(csv_path)
    out = {}
    for p in members(pak):
        data = pak.read(p)
        new = patch_member(p, data, trans)
        if new is not data:
            out[p.lower()] = new
    return out


def authorised_spans(path, data, trans):
    """Byte ranges a translation is allowed to change in this member."""
    spec = family_of(path)
    spans = []
    for off, field, name, jp in fields(path, data):
        if text_key(spec[0], field, jp) in trans:
            spans.append((off, off + len(jp.encode("utf-8"))))
    for off, field, name, jp in blanks(path, data):
        spans.append((off, off + len(jp.encode("utf-8"))))
    return spans


def verify(pak, csv_path):
    """Apply, then account for every changed byte.  Returns problems."""
    trans = load(csv_path)
    problems, changed = [], 0
    for p in members(pak):
        data = pak.read(p)
        new = patch_member(p, data, trans)
        if len(new) != len(data):
            problems.append("%s: size changed" % p)
            continue
        spans = authorised_spans(p, data, trans)
        for i, (a, b) in enumerate(zip(data, new)):
            if a != b:
                changed += 1
                if not any(lo <= i < hi for lo, hi in spans):
                    problems.append("%s: byte %#x changed outside a translated field" % (p, i))
                    break
        if new is not data:
            again = list(fields(p, new))
            if len(again) != len(list(fields(p, data))):
                problems.append("%s: field count changed after patching" % p)
    return problems, changed


def main(argv):
    from gustpak import Pak
    if len(argv) != 4 or argv[1] not in ("export", "verify"):
        print(__doc__)
        return 2
    pak = Pak(argv[2])
    if argv[1] == "export":
        path, n = export(pak, argv[3])
        print("%d dream-table strings -> %s" % (n, path))
        return 0
    problems, changed = verify(pak, argv[3])
    for p in problems:
        print("ERROR  " + p)
    print("%d bytes changed, %d problems" % (changed, len(problems)))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
