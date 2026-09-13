# -*- coding: utf-8 -*-
"""Fold the patch files back into the archives, for when loose files are ignored.

  py -3 repack_pak.py <patch dir> <out dir>

Writes new PACK01.PAK (translated data) and PACK00_01.PAK (font atlas).
Both keep every original entry, key and flag; only the changed members carry
new bytes, and the offsets are recomputed.  Rebuilding with no changes at all
reproduces the original archive byte for byte, which is the check that says
the format is understood correctly.
"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gamepath
from gustpak import Pak, rebuild

RES = gamepath.res_dir(os.environ.get("CIEL_NOSURGE_DX"))

# which archive each patch subtree belongs to
ROUTE = [("PACK01.PAK", ("inc/", "ui/")),
         ("PACK00_01.PAK", ("res_x64/",))]


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


def main(patchdir, outdir):
    os.makedirs(outdir, exist_ok=True)
    have = collect(patchdir)
    print("%d patch files" % len(have))
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
        dst = os.path.join(outdir, pakname)
        t = time.time()
        rebuild(src, repl, dst,
                progress=lambda i, n: print("  %s %d/%d" % (pakname, i, n), end="\r", flush=True))
        print("%-16s %d members replaced -> %s (%.1f MB, %.0fs)"
              % (pakname, len(repl), dst, os.path.getsize(dst) / 1e6, time.time() - t))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "repacked")
