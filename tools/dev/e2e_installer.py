# -*- coding: utf-8 -*-
"""End-to-end test of the built installer's own payload against a clean copy
of the game, running exactly the commands the NSIS script runs.

  py -3 tools/dev/e2e_installer.py <setup.exe> <work dir> <version>

Never touches the real game folder (read only, for its Backup/ originals) or
the registry.
"""
import csv, hashlib, io, json, os, shutil, subprocess, sys

GAME = r"C:\Program Files (x86)\Steam\steamapps\common\CielnosurgeDX"
SEVENZIP = r"C:\Program Files\7-Zip\7z.exe"


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def main(setup, work, want):
    fails = []

    def check(name, cond):
        print("  %-56s %s" % (name, "ok" if cond else "失败"))
        if not cond:
            fails.append(name)

    if os.path.exists(work):
        shutil.rmtree(work)
    inst = os.path.join(work, "inst")
    game = os.path.join(work, "game")
    os.makedirs(inst)
    os.makedirs(os.path.join(game, "Res_x64"))

    # --- 1. the installer's own payload --------------------------------------
    r = subprocess.run([SEVENZIP, "x", "-y", "-o" + inst, setup], capture_output=True)
    check("7-Zip 解开安装包", r.returncode == 0)
    py = os.path.join(inst, "python.exe")
    for rel in ("python.exe", "pythonw.exe", r"tools\build.py", r"tools\install.py",
                r"tools\preflight.py", r"tools\build_text_table.py",
                r"tools\gamepath.py", r"data\zh-Hans\display.csv",
                r"native\build\cielzh.dll", r"native\build\emit_entry.exe", "VERSION"):
        check("安装包里有 " + rel, os.path.exists(os.path.join(inst, rel)))
    version = open(os.path.join(inst, "VERSION"), encoding="utf-8-sig").read().strip()
    check("VERSION 是 %s" % want, version == want)
    repo_dll = (r"C:\Curriculum\EN.601.420 Parallel Programming & Performance Engineering"
                r"\CielNosurgeDX_L10N\github\native\build\cielzh.dll")
    # the trimmed payload: numpy's own unit tests and our self-tests stay out,
    # and the runtime that is left still imports what the build needs
    site = os.path.join(inst, "Lib", "site-packages")
    tests = [r for r, d, f in os.walk(os.path.join(site, "numpy")) if os.path.basename(r) == "tests"]
    check("安装包里没有 numpy 自带的 tests 目录", not tests)
    check("安装包里保留了 numpy.testing", os.path.isdir(os.path.join(site, "numpy", "testing")))
    check("安装包里没有开发自检与 tools/dev",
          not any(n.startswith("selftest_") or n == "test_roundtrip.py"
                  for n in os.listdir(os.path.join(inst, "tools")))
          and not os.path.exists(os.path.join(inst, "tools", "dev")))
    r = subprocess.run([py, "-c",
                        "import numpy, PIL.Image, PIL.ImageFont; print(numpy.__version__)"],
                       capture_output=True)
    check("安装包里的 Python 能导入 numpy 与 Pillow", r.returncode == 0)
    nfiles = sum(len(f) for _r, _d, f in os.walk(inst))
    print("     payload: %d files" % nfiles)
    check("安装包里的 DLL 就是刚构建的那一个",
          sha(os.path.join(inst, r"native\build\cielzh.dll")) == sha(repo_dll))

    # --- 2. a clean game from the originals ----------------------------------
    copies = {
        "CielnosurgeDX.exe": os.path.join(GAME, "Backup", "CielnosurgeDX.exe"),
        "CielnosurgeDX_Env.exe": os.path.join(GAME, "Backup", "CielnosurgeDX_Env.exe"),
        "CielnosurgeDX_Launcher.exe": os.path.join(GAME, "CielnosurgeDX_Launcher.exe"),
        "steam_api64.dll": os.path.join(GAME, "steam_api64.dll"),
        r"Res_x64\PACK01.PAK": os.path.join(GAME, "Backup", "PACK01.PAK"),
        r"Res_x64\PACK00_01.PAK": os.path.join(GAME, "Backup", "PACK00_01.PAK"),
    }
    for rel, src in copies.items():
        shutil.copyfile(src, os.path.join(game, rel))
    known = {r["file"].replace("/", "\\"): r["sha256"].strip().lower()
             for r in csv.DictReader(io.open(os.path.join(inst, r"data\game-versions.csv"),
                                             encoding="utf-8-sig", newline=""))}
    pristine = {}
    for rel in known:
        p = os.path.join(game, rel)
        pristine[rel] = sha(p)
        check("干净副本 %s 是受支持的原版" % rel, pristine[rel] == known[rel])

    # --- 3. the NSIS sequence --------------------------------------------------
    log = os.path.join(inst, "install.log")
    prog = os.path.join(inst, "progress.txt")
    done = os.path.join(inst, "done.txt")
    env = dict(os.environ)
    env.pop("CIEL_NOSURGE_DX", None)        # as on a player's machine

    def run(name, args, lo, hi):
        if os.path.exists(done):
            os.remove(done)
        cmd = [py] + args + ["--log", log, "--progress", prog,
                             "--progress-range", str(lo), str(hi), "--done", done]
        p = subprocess.run(cmd, cwd=inst, env=env, capture_output=True)
        code = None
        if os.path.exists(done):
            raw = open(done, "rb").read()
            for enc in ("utf-16", "utf-8-sig"):
                try:
                    code = int(raw.decode(enc).strip())
                    break
                except (UnicodeDecodeError, ValueError):
                    pass
        check("%s：退出码 0（done 文件 %r，进程 %d）" % (name, code, p.returncode),
              code == 0 and p.returncode == 0)
        if code != 0:
            print(p.stdout.decode("utf-8", "replace")[-1500:])
            print(p.stderr.decode("utf-8", "replace")[-1500:])
        return code == 0

    ok = run("预检", [r"tools\preflight.py", "--game", game, "--data", os.path.join(inst, "data")], 10, 14)
    out = os.path.join(inst, "build")
    for phase, lo, hi in (("check", 14, 18), ("extract", 18, 46), ("font", 46, 60),
                          ("inject", 60, 80), ("repack", 80, 92)):
        if ok:
            ok = run("构建阶段 " + phase,
                     [r"tools\build.py", "--game", game, "--out", out, "--version", version,
                      "--phase", phase], lo, hi)
    if ok:
        ok = run("安装", [r"tools\install.py", "--game", game, "--from", out,
                          "--data", os.path.join(inst, "data"), "--apply"], 92, 99)

    # --- 4. what landed --------------------------------------------------------
    if ok:
        work = os.path.join(out, "work")
        check("构建目录里剧本是 script.zip，没有散文件 script/",
              os.path.isfile(os.path.join(work, "script.zip"))
              and not os.path.isdir(os.path.join(work, "script")))
        m = json.load(io.open(os.path.join(out, "manifest.json"), encoding="utf-8"))
        check("manifest 版本 %s，含显示层" % want, m["patch_version"] == want and m["loader_enabled"])
        by = {f["path"]: f["sha256"] for f in m["files"]}
        for rel, key in (("CielnosurgeDX.exe", "CielnosurgeDX.exe"),
                         ("CielnosurgeDX_Env.exe", "CielnosurgeDX_Env.exe"),
                         (r"Res_x64\PACK01.PAK", "PACK01.PAK"),
                         ("cielzh.dll", "cielzh.dll"), ("cielzh-text.bin", "cielzh-text.bin")):
            check("装上的 %s 与 manifest 一致" % rel, sha(os.path.join(game, rel)) == by.get(key))
        check("装上的 DLL 与安装包里的一致",
              sha(os.path.join(game, "cielzh.dll")) == sha(os.path.join(inst, r"native\build\cielzh.dll")))
        rec = json.load(io.open(os.path.join(game, "Backup", "created.json"), encoding="utf-8"))
        check("归属记录登记了 DLL 与替换表，版本 %s" % want,
              set(rec["files"]) == {"cielzh.dll", "cielzh-text.bin"}
              and all(v["patch_version"] == want for v in rec["files"].values()))
        check("没有遗留事务", not os.path.exists(os.path.join(game, "Backup", "install_tx.json")))
        v = subprocess.run([py, r"tools\install.py", "--game", game, "--from", out,
                            "--data", os.path.join(inst, "data"), "--verify"],
                           cwd=inst, env=env, capture_output=True).stdout.decode("utf-8", "replace")
        check("--verify 六项都与本次构建相符", v.count("matches this build") == 6)

    # --- 5. uninstall, as the NSIS uninstaller runs it -------------------------
    if ok:
        p = subprocess.run([py, r"tools\install.py", "--game", game, "--restore"],
                           cwd=inst, env=env, capture_output=True)
        check("卸载（--restore）退出码 0", p.returncode == 0)
        for rel in known:
            check("卸载后 %s 逐字节回到原版" % rel, sha(os.path.join(game, rel)) == pristine[rel])
        check("卸载后 DLL 与替换表都已删除",
              not os.path.exists(os.path.join(game, "cielzh.dll"))
              and not os.path.exists(os.path.join(game, "cielzh-text.bin")))

    print()
    print("%d 项未通过" % len(fails) if fails else "端到端全部通过")
    return 1 if fails else 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv[1], sys.argv[2], sys.argv[3]))
