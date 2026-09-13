# -*- coding: utf-8 -*-
"""Assemble everything into a patch folder the user can drop on the game.

  py -3 build_patch.py <export dir> <font out dir> <patch dir>

The patch is laid out exactly like the game folder, so installing it is a
copy and uninstalling it is a delete plus restoring two originals.  Files go
in loose rather than repacked: if the engine honours loose files this is all
that is needed, and if it does not, repack_pak.py folds the same files back
into the archives.
"""
import sys, os, io, shutil, hashlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gamepath
from gustpak import Pak
import import_text
import patch_exe_strings
import env_strings
import progress

GAME = gamepath.resolve(os.environ.get("CIEL_NOSURGE_DX"))
RES = GAME + "/Res_x64"


def sha(path, limit=None):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(1 << 20)
            if not b:
                break
            h.update(b)
    return h.hexdigest()[:16]


def main(exportdir, fontdir, patchdir):
    if os.path.isdir(patchdir):
        shutil.rmtree(patchdir)
    os.makedirs(patchdir)

    # 1. translated data, laid out under the archive paths
    pak = Pak(RES + "/PACK01.PAK")
    script, ui, binmap, speakers = import_text.collect(exportdir)
    files = import_text.build(pak, script, ui, binmap, speakers)
    n = 0
    tick = progress.over(len(files), every=25)
    for p, data in files.items():
        real = pak.get(p).name.strip("\\")
        dst = os.path.join(patchdir, real.replace("\\", os.sep))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        open(dst, "wb").write(data)
        n += 1
        tick(n)
    print("%d translated data files" % n)

    # 2. font atlas
    dst = os.path.join(patchdir, "Res_x64", "font", "FOT-SKIPSTD-B_0.g1t")
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy(os.path.join(fontdir, "FOT-SKIPSTD-B_0.g1t"), dst)
    print("font atlas   %.1f MB" % (os.path.getsize(dst) / 1e6))

    # 3. patched executable: the font table first, because that rebuild starts
    #    from a pristine image, then the hardcoded strings on top of it -- they
    #    are overwritten in place and do not move anything.
    exe_dst = os.path.join(patchdir, "CielnosurgeDX.exe")
    shutil.copy(os.path.join(fontdir, "CielnosurgeDX.exe"), exe_dst)
    exe_csv = os.path.join(exportdir, "exe_text.csv")
    if not os.path.exists(exe_csv):
        exe_csv = patch_exe_strings.DEFAULT_CSV
    rows, todo, skipped = patch_exe_strings.load(exe_csv)
    bad = patch_exe_strings.check(todo)
    if bad:
        raise SystemExit("exe_text.csv has %d translations that do not fit; "
                         "run check_exe_text.py" % len(bad))
    data, done, miss, total = patch_exe_strings.patch(open(exe_dst, "rb").read(), todo)
    if miss:
        raise SystemExit("%d hardcoded strings were not found in the executable -- "
                         "unsupported game version?" % miss)
    open(exe_dst, "wb").write(data)
    print("patched exe  %.1f MB, %d hardcoded strings translated"
          % (os.path.getsize(exe_dst) / 1e6, done))

    # 4. the settings program, whose UI lives in its own Win32 resources
    env_csv = os.path.join(exportdir, "env_text.csv")
    env_src = gamepath.source_file(GAME, env_strings.EXE)
    if os.path.exists(env_csv) and os.path.exists(env_src):
        env_dst = os.path.join(patchdir, env_strings.EXE)
        if env_strings.do_patch(env_src, env_dst, env_csv):
            raise SystemExit("the settings program's translations do not fit")
        print("settings exe %.1f MB" % (os.path.getsize(env_dst) / 1e6))

    readme = os.path.join(patchdir, "安装说明.txt")
    io.open(readme, "w", encoding="utf-8").write(INSTALL % (
        sha(GAME + "/CielnosurgeDX.exe"), n))
    print("patch -> %s" % patchdir)


INSTALL = """\
《Ciel nosurge DX》简体中文补丁 —— 测试版
================================================

原版 CielnosurgeDX.exe 的 SHA256 前 16 位：%s
本补丁包含 %d 个已汉化的数据文件。

安装前请务必备份
----------------
把下面两个文件复制到安全的地方，卸载时要用：

    CielnosurgeDX.exe
    Res_x64\\PACK00_01.PAK      （只有走「重打包」方案时才会被改动）

安装
----
把本文件夹内的所有内容复制到游戏根目录，覆盖同名文件。
游戏根目录形如：
    ...\\steamapps\\common\\CielnosurgeDX\\

先这样试一次。如果进游戏能看到中文，说明引擎接受散文件覆盖，
以后每次更新翻译只要复制文件即可，不用重打包 1.7GB 的封包。

如果字还是日文
--------------
说明引擎只读封包，需要改用重打包方案：

    py -3 tools\\repack_pak.py

它会把同样这些文件写回 PACK01.PAK 与 PACK00_01.PAK。
重打包后的封包体积较大，请预留约 4GB 磁盘空间。

卸载
----
删除复制进去的文件，把备份的 CielnosurgeDX.exe 放回原处即可。
或者在 Steam 里对游戏「验证文件完整性」，会自动还原。

当前进度
--------
已汉化：界面、道具、主线第 1～4 章、部分系统文本（约占全部文本的 20%%）
未汉化的部分仍显示日文，字库同时保留了日文字形，不会出现方块字。
"""


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
