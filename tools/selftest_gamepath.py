# -*- coding: utf-8 -*-
"""The game folder build.py is given is the one every step of the build reads.

  py -3 selftest_gamepath.py

No game files: two empty folders that look like the game stand in for "the one
the installer was pointed at" and "the one Steam has registered".
"""
import os, re, sys, tempfile, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gamepath                     # noqa: E402


def main():
    failures = []

    def check(name, cond):
        print("  %-54s %s" % (name, "ok" if cond else "失败"))
        if not cond:
            failures.append(name)

    root = tempfile.mkdtemp(prefix="cielzh-gp-")
    saved = os.environ.get(gamepath.ENV)
    try:
        chosen, other = os.path.join(root, "chosen"), os.path.join(root, "other")
        for d in (chosen, other):
            os.makedirs(os.path.join(d, "Res_x64"))
            open(os.path.join(d, gamepath.EXE), "wb").close()

        # Something else is what a module would find on its own.
        os.environ[gamepath.ENV] = other
        check("（前置）不固定时，各模块自己会找到另一份",
              gamepath.resolve(os.environ.get(gamepath.ENV)) == os.path.abspath(other))

        gamepath.pin(chosen)
        import build_charset, build_font   # noqa: E401 -- they look it up themselves
        check("固定之后，build_charset 找到的是指定的那份",
              build_charset.game_dir() == os.path.abspath(chosen))
        check("固定之后，build_font 找到的是指定的那份",
              build_font.game_dir() == os.path.abspath(chosen))

        # build.py must pin before it imports anything that looks the game up.
        src = open(os.path.join(HERE, "build.py"), encoding="utf-8").read()
        pin_at = src.find("gamepath.pin(game)")
        imports = [m.start() for m in re.finditer(
            r"^\s+(?:import|from) (?:build_patch|build_font|build_charset|"
            r"export_text|export_exe_text|env_strings|merge_repo)\b", src, re.M)]
        check("build.py 在导入任何自行查找游戏的模块之前固定目录",
              pin_at > 0 and imports and all(pin_at < i for i in imports))
    finally:
        if saved is None:
            os.environ.pop(gamepath.ENV, None)
        else:
            os.environ[gamepath.ENV] = saved
        shutil.rmtree(root, ignore_errors=True)

    print()
    if failures:
        print("%d 项未通过" % len(failures))
        return 1
    print("全部自检通过")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
