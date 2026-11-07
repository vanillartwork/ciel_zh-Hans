# -*- coding: utf-8 -*-
"""The extracted event scripts, handed from one build phase to the next.

  py -3 tools/workscript.py unpack build/work     zip -> loose script/*.csv
  py -3 tools/workscript.py pack   build/work     loose script/*.csv -> zip

The extract phase writes one CSV per script group, about 130 of them; the merge
rewrites every one; the font phase and the injector read them all again.  On a
machine with on-access virus scanning every freshly written file is scanned the
first time it is opened -- about 55 ms each here, twice per build -- so the
build now keeps them in one uncompressed archive, script.zip, beside the other
exported tables.  The members are the same bytes the loose files were.

Rules, because two places to keep the same data is how stale data gets read:

  * a build has exactly one source: script.zip or script/, never both.  Both
    present stops the build; nothing falls back from one to the other.
  * a damaged archive, a duplicate member or a member that cannot be read
    stops the build.
  * the archive is never updated in place.  A new one is written beside it,
    read back and checked, then moved over the old one.

Member order is the order NTFS lists the loose files in (sorted by their
upper-case names), so code that walked the folder sees the members in the
order it saw the files.

Maintenance tools that read the export can use read_all() and work with either
form.  Tools that write into the loose files need the loose form: unpack first.
"""
import csv, io, os, shutil, sys, zipfile

BUNDLE = "script.zip"
LOOSE = "script"
# fixed, so that the same members always make the same archive
STAMP = (1980, 1, 1, 0, 0, 0)


class WorkScriptError(Exception):
    pass


def bundle_path(exportdir):
    return os.path.join(exportdir, BUNDLE)


def loose_path(exportdir):
    return os.path.join(exportdir, LOOSE)


def source(exportdir):
    """"zip", "loose" or None; WorkScriptError when both are there."""
    z = os.path.isfile(bundle_path(exportdir))
    d = os.path.isdir(loose_path(exportdir))
    if z and d:
        raise WorkScriptError(
            "%s has both %s and %s/; a build reads exactly one of them.  Delete "
            "the one that is stale (normally %s/, left by an older build) or "
            "rebuild from the extract phase." % (exportdir, BUNDLE, LOOSE, LOOSE))
    return "zip" if z else "loose" if d else None


def order(names):
    """The order NTFS lists these file names in."""
    return sorted(names, key=str.upper)


def read_all(exportdir):
    """[(member name, bytes)] in listing order, from whichever source exists."""
    src = source(exportdir)
    if src is None:
        return []
    if src == "loose":
        d = loose_path(exportdir)
        out = []
        for fn in order(os.listdir(d)):
            if fn.endswith(".csv"):
                with open(os.path.join(d, fn), "rb") as f:
                    out.append((fn, f.read()))
        return out
    path = bundle_path(exportdir)
    try:
        with zipfile.ZipFile(path) as z:
            infos = z.infolist()
            names = [i.filename for i in infos]
            if len(set(names)) != len(names):
                raise WorkScriptError("%s holds a member twice" % path)
            bad = [n for n in names if "/" in n or "\\" in n or not n.endswith(".csv")]
            if bad:
                raise WorkScriptError("%s holds unexpected members: %s" % (path, bad[:3]))
            out = [(n, z.read(n)) for n in names]   # read() checks each CRC
    except (zipfile.BadZipFile, OSError, EOFError) as e:
        raise WorkScriptError("%s cannot be read: %s" % (path, e))
    if [n for n, _ in out] != order(n for n, _ in out):
        raise WorkScriptError("%s is not in listing order" % path)
    return out


def rows(data):
    """The records of one member, read the way the loose files were."""
    return list(csv.DictReader(io.StringIO(data.decode("utf-8-sig"), newline="")))


def serialize(header, rows_):
    """Bytes of a CSV written exactly as export_text.w writes one."""
    buf = io.StringIO(newline="")
    cw = csv.writer(buf, lineterminator="\r\n")
    cw.writerow(header)
    cw.writerows(rows_)
    return buf.getvalue().encode("utf-8-sig")


def serialize_dicts(fieldnames, rows_):
    """Bytes of a CSV written exactly as merge_repo writes one back."""
    buf = io.StringIO(newline="")
    w = csv.DictWriter(buf, fieldnames=fieldnames, lineterminator="\r\n")
    w.writeheader()
    w.writerows(rows_)
    return buf.getvalue().encode("utf-8-sig")


def write_all(exportdir, members, replace_loose=False):
    """Write [(name, bytes)] as the archive, whole.

    `replace_loose` is for the extract phase only: it regenerates everything,
    so a script/ folder left by an older build is removed rather than refused.
    Every other writer stops if script/ is there.
    """
    members = list(members)
    names = [n for n, _ in members]
    if len(set(names)) != len(names):
        raise WorkScriptError("two members named alike: %s" % sorted(
            n for n in set(names) if names.count(n) > 1)[:3])
    loose = loose_path(exportdir)
    if os.path.isdir(loose):
        if not replace_loose:
            raise WorkScriptError("%s/ exists; this build writes %s and will not "
                                  "leave two sources behind" % (loose, BUNDLE))
        shutil.rmtree(loose)
    os.makedirs(exportdir, exist_ok=True)
    final = bundle_path(exportdir)
    tmp = final + ".part"
    by_name = dict(members)
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_STORED) as z:
        for n in order(names):
            info = zipfile.ZipInfo(n, date_time=STAMP)
            info.compress_type = zipfile.ZIP_STORED
            z.writestr(info, by_name[n])
    # read back before it replaces anything
    with zipfile.ZipFile(tmp) as z:
        back = {i.filename: z.read(i.filename) for i in z.infolist()}
    if back != by_name:
        os.remove(tmp)
        raise WorkScriptError("%s did not read back as written" % tmp)
    os.replace(tmp, final)


def unpack(exportdir):
    members = read_all(exportdir)
    if source(exportdir) != "zip":
        raise WorkScriptError("no %s to unpack in %s" % (BUNDLE, exportdir))
    d = loose_path(exportdir)
    os.makedirs(d)
    for n, b in members:
        with open(os.path.join(d, n), "wb") as f:
            f.write(b)
    os.remove(bundle_path(exportdir))
    return len(members)


def pack(exportdir):
    if source(exportdir) != "loose":
        raise WorkScriptError("no %s/ to pack in %s" % (LOOSE, exportdir))
    members = read_all(exportdir)
    write_all(exportdir, members, replace_loose=True)
    return len(members)


def main(argv):
    if len(argv) != 3 or argv[1] not in ("unpack", "pack"):
        print(__doc__)
        return 2
    try:
        n = (unpack if argv[1] == "unpack" else pack)(argv[2])
    except WorkScriptError as e:
        print("error: %s" % e)
        return 1
    print("%d scripts %sed in %s" % (n, argv[1], argv[2]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
