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


def collect(patchdir):
    out = {}
    for root, _, files in os.walk(patchdir):
        for fn in files:
            if fn.endswith(".txt") and root == patchdir:
                continue                      # the install note
            p = os.path.join(root, fn)
            rel = os.path.relpath(p, patchdir).replace(os.sep, "/").lower()
            if rel.endswith(".exe"):
                continue
            out[rel] = p
    return out


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
                repl[p] = open(have[p], "rb").read()
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
