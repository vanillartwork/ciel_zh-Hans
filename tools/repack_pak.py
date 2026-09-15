# -*- coding: utf-8 -*-
"""Fold the patch files back into the archives.

  py -3 repack_pak.py <patch dir> <out dir>

Two ways out, chosen per archive:

**in place** -- when every member being replaced is exactly as long as the one
it replaces, nothing in the archive moves: the entry table still holds the
right offset and size, so the new bytes can simply be written over the old
ones. That is the case for PACK00_01, where the only change is the font atlas
and the rebuilt atlas is the same 16,777,260 bytes as the shipped one. A plan
is written instead of a 1.8 GB copy, and install.py applies it -- which also
means the backup is the 16 MB that changed rather than the whole archive.

**rebuilt** -- otherwise the archive is written out afresh with recomputed
offsets, keeping every original key and flag. That is PACK01, 33 MB, where
translated files are all different lengths.

Rebuilding with no changes at all reproduces the original archive byte for
byte, which is the check that says the format is understood correctly.
"""
import sys, os, io, json, time, hashlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gamepath
import progress
from gustpak import Pak, rebuild, _xor

RES = gamepath.res_dir(os.environ.get("CIEL_NOSURGE_DX"))

# which archive each patch subtree belongs to
ROUTE = [("PACK01.PAK", ("inc/", "ui/")),
         ("PACK00_01.PAK", ("res_x64/",))]

PLAN = "inplace.json"


def sha256(b):
    return hashlib.sha256(b).hexdigest()


BUNDLE = "text.zip"


class Staged:
    """The patched members waiting to be folded back in.

    Two layouts.  The translated text arrives as one uncompressed zip, because
    writing it as 2,679 separate files and reading them straight back costs
    around 50 seconds on a machine with on-access virus scanning -- the scanner
    walks every new file the first time it is opened.  (Read them a second time
    and it is a fifth of a second; that is what makes the cost easy to miss.)
    Everything else -- the atlas, the executables -- stays a real file, since
    there are only a handful and install.py copies them out directly.
    """

    def __init__(self, patchdir):
        self.files = {}
        self.zip = None
        self.zipped = {}
        bundle = os.path.join(patchdir, BUNDLE)
        if os.path.isfile(bundle):
            import zipfile
            self.zip = zipfile.ZipFile(bundle)
            for name in self.zip.namelist():
                rel = name.replace("\\", "/").lstrip("/").lower()
                if rel in self.zipped:
                    raise ValueError("%s lists %s twice" % (BUNDLE, name))
                self.zipped[rel] = name
        for root, _, files in os.walk(patchdir):
            for fn in files:
                if root == patchdir and (fn.endswith(".txt") or fn == BUNDLE):
                    continue                  # the install note, and the bundle
                p = os.path.join(root, fn)
                rel = os.path.relpath(p, patchdir).replace(os.sep, "/").lower()
                if rel.endswith(".exe"):
                    continue
                if rel in self.zipped:
                    raise ValueError("%s is both a loose file and in %s -- a "
                                     "half-converted build would silently use "
                                     "one of them" % (rel, BUNDLE))
                self.files[rel] = p

    def __contains__(self, rel):
        return rel in self.zipped or rel in self.files

    def __len__(self):
        return len(self.zipped) + len(self.files)

    def read(self, rel):
        """The patched bytes.  A damaged bundle must stop the build, not look
        like an entry that was never patched."""
        name = self.zipped.get(rel)
        if name is not None:
            try:
                return self.zip.read(name)    # ZipFile.read verifies the CRC
            except Exception as e:
                raise IOError("%s: could not read %s (%s)" % (BUNDLE, name, e))
        return open(self.files[rel], "rb").read()


def collect(patchdir):
    return Staged(patchdir)


def can_patch_in_place(src, repl):
    """True when no member changes length, so nothing in the archive moves."""
    for path, data in repl.items():
        e = src.get(path)
        if e is None or e.size != len(data):
            return False
    return True


def plan_in_place(src, repl, outdir, pakname):
    """Record what to overwrite, and stage the bytes to write."""
    steps = []
    for path, data in sorted(repl.items()):
        e = src.get(path)
        at = src.data_start + e.offset
        src.fh.seek(at)
        before = src.fh.read(e.size)
        stored = _xor(data, e.key)          # what the archive must contain
        name = os.path.basename(path)
        io.open(os.path.join(outdir, name), "wb").write(stored)
        steps.append({
            "archive": pakname,
            "entry": path,
            "file": name,
            "offset": at,
            "size": e.size,
            "sha256_before": sha256(before),
            "sha256_after": sha256(stored),
        })
    return steps


def main(patchdir, outdir):
    os.makedirs(outdir, exist_ok=True)
    have = collect(patchdir)
    print("%d patch files" % len(have))
    plan = []
    for pakname, prefixes in ROUTE:
        src = Pak(gamepath.source_pak(RES, pakname))
        repl = {}
        for e in src:
            p = e.path.lower()
            if not any(p.startswith(x) for x in prefixes):
                continue
            if p in have:
                repl[p] = have.read(p)
        if not repl:
            print("%-16s nothing to change" % pakname)
            continue

        if can_patch_in_place(src, repl):
            steps = plan_in_place(src, repl, outdir, pakname)
            plan += steps
            mb = sum(s["size"] for s in steps) / 1e6
            print("%-16s %d member(s) are the same length -- patching in place, "
                  "%.1f MB instead of rebuilding %.0f MB"
                  % (pakname, len(steps), mb,
                     os.path.getsize(src.path) / 1e6))
            continue

        dst = os.path.join(outdir, pakname)
        t = time.time()
        tick = progress.over(len(src.entries), every=50)
        rebuild(src, repl, dst,
                progress=lambda i, n: (tick(i),
                                       print("  %s %d/%d" % (pakname, i, n),
                                             end="\r", flush=True)))
        print("%-16s %d members replaced -> %s (%.1f MB, %.0fs)"
              % (pakname, len(repl), dst, os.path.getsize(dst) / 1e6,
                 time.time() - t))

    p = os.path.join(outdir, PLAN)
    if plan:
        io.open(p, "w", encoding="utf-8").write(
            json.dumps(plan, ensure_ascii=False, indent=2))
        print("in-place plan -> %s" % p)
    elif os.path.exists(p):
        os.remove(p)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "repacked")
