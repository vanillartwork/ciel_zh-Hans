# -*- coding: utf-8 -*-
"""Put each display-layer safeguard back the wrong way and see what notices.

  py -3 tools/dev/inject_display.py      (needs Visual Studio with the C++ tools)

Compiles only the self-test (not the whole build.ps1, which throws on the first
failure and would skip the restore), and always restores the source.
"""
import io, os, shutil, subprocess, sys

import tempfile
ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "native").replace(os.sep, "/")
SRC = ROOT + "/cielzh/display.cpp"
OUT = os.path.join(tempfile.gettempdir(), "cielzh-inject-display")

CASES = {
    # every caller counts as the widget system: logic would read our Chinese
    "allui": ("    for (const UiReader& r : kUiReaders)\n"
              "        if (rva >= r.begin && rva < r.end)\n"
              "            return true;\n"
              "    return false;",
              "    return true;   // FAULT"),
    # nobody counts as the widget system: the screen would draw Japanese back
    "noui": ("    for (const UiReader& r : kUiReaders)\n"
             "        if (rva >= r.begin && rva < r.end)\n"
             "            return true;\n"
             "    return false;",
             "    (void)rva;\n    return false;   // FAULT"),
    # replace even when there is nowhere to remember the Japanese
    "noguard": ("    if (!g) {\n"
                "        Unlock();\n"
                "        delete[] orig;\n"
                "        g_full.fetch_add(1, std::memory_order_relaxed);\n"
                "        return text;\n"
                "    }",
                "    if (!g) {\n"
                "        Unlock();\n"
                "        delete[] orig;\n"
                "        g_full.fetch_add(1, std::memory_order_relaxed);\n"
                "        return out;   // FAULT\n"
                "    }"),
    # a widget writing back what it read loses its Japanese
    "writeback": ("            if (!(g->disp_hash == h && g->disp_len == len))\n"
                  "                DropLocked(g);",
                  "            DropLocked(g);   // FAULT"),
    # names replaced with any entry, including words kept whole-only
    "spanflags": ("            if (const Entry* n = Find(text + j, k - j, kMatchName)) {",
                  "            if (const Entry* n = Find(text + j, k - j, kMatchWhole | kMatchName)) {   // FAULT"),
    # the table checksum is not checked
    "nochecksum": ("    if (TextHash(reinterpret_cast<const char*>(d), static_cast<size_t>(body))\n"
                   "        != Le64(d + body))",
                   "    if (false)   // FAULT"),
    # tags allowed in replacements
    "tags": ("        if (std::memchr(pool_at + off, 0, len) || std::memchr(pool_at + off, '<', len))",
             "        if (std::memchr(pool_at + off, 0, len))   // FAULT"),
    # a get keeps handing back the Japanese after the widget moved on
    # recording cannot be turned off: every player pays for the recorder
    "recording": ("    if (!g_init || !g_recording.load(std::memory_order_relaxed))",
                  "    if (!g_init)   // FAULT", "trace.cpp"),
    "stale": ("        if (g->disp_hash == h && g->disp_len == len && g->orig) {",
              "        if (g->orig) {   // FAULT"),
}


def vcvars():
    vswhere = os.path.expandvars(
        r"%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe")
    root = subprocess.run([vswhere, "-latest", "-products", "*", "-requires",
                           "Microsoft.VisualStudio.Component.VC.Tools.x86.x64",
                           "-property", "installationPath"],
                          capture_output=True, text=True).stdout.strip()
    return os.path.join(root, r"VC\Auxiliary\Build\vcvars64.bat")


def build_and_run(vc):
    os.makedirs(OUT, exist_ok=True)
    lib = [ROOT + "/cielzh/" + f for f in os.listdir(ROOT + "/cielzh")
           if f.endswith(".cpp") and f != "dllmain.cpp"]
    srcs = " ".join('"%s"' % p.replace("/", "\\") for p in [ROOT + "/test/selftest.cpp"] + lib)
    cmd = ('call "%s" >nul 2>&1 && cd /d "%s" && cl /nologo /MT /EHsc /std:c++17 '
           '/utf-8 /O2 /DNDEBUG %s /link /OUT:st.exe >nul' % (vc, OUT, srcs))
    r = subprocess.run('cmd /s /c "' + cmd + '"', capture_output=True)
    if r.returncode:
        return None, r.stdout.decode("mbcs", "replace")[-600:]
    r = subprocess.run([OUT + "/st.exe"], capture_output=True)
    return r.stdout.decode("utf-8", "replace"), ""


def main():
    vc = vcvars()
    files = {f: io.open(ROOT + "/cielzh/" + f, encoding="utf-8").read()
             for f in ("display.cpp", "trace.cpp")}
    missed = []
    try:
        for name, case in CASES.items():
            old, new = case[0], case[1]
            fname = case[2] if len(case) > 2 else "display.cpp"
            orig = files[fname]
            path = ROOT + "/cielzh/" + fname
            if old not in orig:
                print("%-11s anchor missing" % name)
                missed.append(name)
                continue
            io.open(path, "w", encoding="utf-8", newline="").write(orig.replace(old, new, 1))
            out, err = build_and_run(vc)
            io.open(path, "w", encoding="utf-8", newline="").write(orig)
            if out is None:
                print("%-11s did not compile: %s" % (name, err))
                missed.append(name)
                continue
            fails = [l.strip() for l in out.splitlines() if l.rstrip().endswith("FAILED")]
            print("%-11s %d failed" % (name, len(fails)))
            for f in fails[:4]:
                print("      " + f)
            if not fails:
                missed.append(name)
    finally:
        for f, text in files.items():
            io.open(ROOT + "/cielzh/" + f, "w", encoding="utf-8", newline="").write(text)
    print("\nrestored; not caught: %s" % (", ".join(missed) or "none"))
    return 1 if missed else 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
