# -*- coding: utf-8 -*-
"""Find the player's own copy of the game.

Nothing in this project ships game files, so every tool that needs one has to
be pointed at an installation.  In order of preference:

  1. an explicit path passed on the command line
  2. the CIEL_NOSURGE_DX environment variable
  3. Steam's own library folders, read from the registry and libraryfolders.vdf
  4. the usual default install paths

Call `resolve()` and let it raise: a clear message about which copy of the
game could not be found beats a stack trace from open() three calls later.
"""
import os, re, sys

APP_ID = "1477480"          # Ciel nosurge DX on Steam
FOLDER = "CielnosurgeDX"
EXE = "CielnosurgeDX.exe"
ENV = "CIEL_NOSURGE_DX"
# Steam writes an uninstall entry for every installed game, and its
# InstallLocation is the folder itself -- no guessing at library layouts.
UNINSTALL_KEYS = [
    r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Steam App " + APP_ID,
    r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Steam App " + APP_ID,
]


def _clean(p):
    """Steam stores its own path with forward slashes; Windows wants back."""
    return os.path.normpath(p.replace("/", os.sep)) if p else p


class NotFound(Exception):
    pass


def looks_right(path):
    return bool(path) and os.path.isfile(os.path.join(path, EXE)) \
        and os.path.isdir(os.path.join(path, "Res_x64"))


def registered_location():
    """Where Steam says this game is installed, straight from its own entry."""
    try:
        import winreg
    except ImportError:
        return None
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        for key in UNINSTALL_KEYS:
            try:
                with winreg.OpenKey(hive, key) as k:
                    loc = _clean(winreg.QueryValueEx(k, "InstallLocation")[0])
                    if looks_right(loc):
                        return loc
            except OSError:
                pass
    return None


def steam_roots():
    roots = []
    try:
        import winreg
        for hive, key in ((winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
                          (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam")):
            try:
                with winreg.OpenKey(hive, key) as k:
                    for name in ("SteamPath", "InstallPath"):
                        try:
                            roots.append(_clean(winreg.QueryValueEx(k, name)[0]))
                        except OSError:
                            pass
            except OSError:
                pass
    except ImportError:
        pass
    roots += [r"C:\Program Files (x86)\Steam", r"C:\Program Files\Steam",
              os.path.expanduser("~/.steam/steam"),
              os.path.expanduser("~/Library/Application Support/Steam")]

    libs = []
    for root in roots:
        if not root or not os.path.isdir(root):
            continue
        libs.append(root)
        vdf = os.path.join(root, "steamapps", "libraryfolders.vdf")
        if os.path.isfile(vdf):
            try:
                text = open(vdf, encoding="utf-8", errors="replace").read()
            except OSError:
                continue
            # "path"  "D:\\SteamLibrary"
            libs += [_clean(p.replace("\\\\", "\\"))
                     for p in re.findall(r'"path"\s+"([^"]+)"', text)]
    return libs


def candidates():
    for lib in steam_roots():
        yield os.path.join(lib, "steamapps", "common", FOLDER)
    for base in (r"C:\Program Files (x86)", r"C:\Program Files", r"C:\Games", "D:\\"):
        yield os.path.join(base, FOLDER)


def resolve(explicit=None):
    """The game folder, or NotFound with something useful to say."""
    tried = []
    for path in [explicit, os.environ.get(ENV)]:
        if not path:
            continue
        path = os.path.abspath(os.path.expanduser(path))
        if looks_right(path):
            return path
        tried.append(path)
    found = registered_location()
    if found:
        return found
    for path in candidates():
        if looks_right(path):
            return os.path.abspath(path)
        tried.append(path)

    raise NotFound(
        "Could not find a copy of Ciel nosurge DX.\n"
        "Pass the folder on the command line, or set %s to it, for example:\n"
        "    set %s=D:\\SteamLibrary\\steamapps\\common\\%s\n"
        "The folder is the one containing %s and Res_x64.\n"
        "Looked in:\n  %s" % (ENV, ENV, FOLDER, EXE, "\n  ".join(tried[:10])))


def res_dir(explicit=None):
    return os.path.join(resolve(explicit), "Res_x64")


def source_pak(res, name):
    """An archive the patch has not already been applied to.

    Reading text out of an installation that is already patched would extract
    the Chinese that is in there and take it for the original Japanese, so
    everything downstream would compare translations against themselves.
    install.py puts the originals in Backup/ before it replaces anything, so
    that is where to look first.
    """
    backup = os.path.join(os.path.dirname(os.path.abspath(res)), "Backup", name)
    if os.path.isfile(backup):
        return backup
    return os.path.join(res, name)


if __name__ == "__main__":
    try:
        print(resolve(sys.argv[1] if len(sys.argv) > 1 else None))
    except NotFound as e:
        print(e)
        sys.exit(1)
