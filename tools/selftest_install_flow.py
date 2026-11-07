# -*- coding: utf-8 -*-
"""Drives the real installer entry point against a synthetic game folder.

  py -3 selftest_install_flow.py

No game files.  A few small files stand in for the archives and executables, and
a generated game-versions.csv makes them the "supported originals", so the code
under test is the actual main() with its actual version gate -- not a --force
shortcut around it.

This exists because six problems in the install wiring got through a suite that
only exercised the helper module: a version field main() reads and argparse never
defined, ownership checks running after the executable had been replaced, and a
--no-loader build that failed halfway.  None of them were reachable without
calling main().
"""
import sys, os, io, csv, json, shutil, hashlib, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import newfiles                     # noqa: E402
import install                      # noqa: E402


def sha_bytes(b):
    return hashlib.sha256(b).hexdigest()


def sha_file(p):
    """None when the file is not there, so a missing file fails a check rather
    than ending the run with a traceback."""
    if not os.path.exists(p):
        return None
    return sha_bytes(open(p, "rb").read())


class Fixture:
    """A synthetic game folder plus a build tree the installer will accept."""

    def __init__(self, root, loader=True, version="1.0.0"):
        self.root = root
        self.game = os.path.join(root, "game")
        self.backup = os.path.join(self.game, "Backup")
        self.build = os.path.join(root, "build")
        self.data = os.path.join(root, "data")
        self.stage = os.path.join(self.build, "stage")
        for d in (self.game, os.path.join(self.game, "Res_x64"), self.stage,
                  self.data):
            os.makedirs(d, exist_ok=True)
        self.loader = loader
        self.version = version
        self.originals = {}

        # The originals, and the build that replaces them.
        for name, rel in install.PAYLOAD:
            body = ("original " + rel).encode()
            p = os.path.join(self.game, rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            io.open(p, "wb").write(body)
            self.originals[rel] = sha_bytes(body)
            io.open(os.path.join(self.stage, name), "wb").write(
                ("patched %s by %s" % (rel, version)).encode())
        if loader:
            io.open(os.path.join(self.stage, "cielzh.dll"), "wb").write(
                ("dll %s" % version).encode())
            io.open(os.path.join(self.stage, "cielzh-text.bin"), "wb").write(
                ("table %s" % version).encode())

        self.write_versions()
        self.write_manifest()

    def write_versions(self):
        """The generated game-versions.csv, so the real version gate applies."""
        with io.open(os.path.join(self.data, "game-versions.csv"), "w",
                     encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["version_id", "label", "platform", "file", "bytes",
                        "sha256", "status", "note"])
            for rel, h in self.originals.items():
                w.writerow(["test", "test", "windows-x64", rel, 0, h,
                            "supported", ""])

    def write_manifest(self, loader=None, version=None):
        if loader is not None:
            self.loader = loader
        if version is not None:
            self.version = version
        io.open(os.path.join(self.build, "manifest.json"), "w",
                encoding="utf-8").write(json.dumps({
                    "patch_version": self.version,
                    "loader_enabled": self.loader,
                    "built": "now", "files": []}))

    def restage(self, version, loader=None):
        """A newer build in the same tree."""
        self.version = version
        for name, rel in install.PAYLOAD:
            io.open(os.path.join(self.stage, name), "wb").write(
                ("patched %s by %s" % (rel, version)).encode())
        if loader is None:
            loader = self.loader
        dll = os.path.join(self.stage, "cielzh.dll")
        table = os.path.join(self.stage, "cielzh-text.bin")
        if loader:
            io.open(dll, "wb").write(("dll %s" % version).encode())
            io.open(table, "wb").write(("table %s" % version).encode())
        else:
            for p in (dll, table):
                if os.path.exists(p):
                    os.remove(p)
        self.write_manifest(loader=loader, version=version)

    def run(self, *extra):
        argv = ["--game", self.game, "--from", self.build, "--data", self.data]
        return install.main(list(argv) + list(extra))

    def snapshot(self):
        out = {}
        for base, _dirs, files in os.walk(self.game):
            for f in files:
                p = os.path.join(base, f)
                out[os.path.relpath(p, self.game)] = sha_file(p)
        return out

    @property
    def dll(self):
        return os.path.join(self.game, "cielzh.dll")

    @property
    def table(self):
        return os.path.join(self.game, "cielzh-text.bin")


class RangeFixture(Fixture):
    """A build that patches a byte range in place instead of replacing a whole
    archive -- what the real PACK00_01.PAK build does.

    Without one of these, the flow tests never had a plan at all, so the restore
    plan, the range backups and the offsets were only exercised by the helper
    suite, one layer below the bug.
    """

    ARCHIVE = "PACK00_01.PAK"
    REL = "Res_x64/PACK00_01.PAK"
    SIZE = 16

    def __init__(self, root, offset=100, mark=b"A", entry="font atlas", **kw):
        Fixture.__init__(self, root, **kw)
        self.body = bytes(bytearray(i % 251 for i in range(4096)))
        io.open(os.path.join(self.game, self.REL), "wb").write(self.body)
        self.originals[self.REL] = sha_bytes(self.body)
        self.pristine = sha_bytes(self.body)
        self.write_versions()
        self.set_range(offset, mark, entry)

    def set_range(self, offset, mark, entry="font atlas"):
        """What this build writes, and where.

        `entry` is the label the installer prints for the range, and the two
        builds in a test are given different ones: it is the only thing in the
        output that says which plan a restore actually worked from.
        """
        self.offset = offset
        new = mark * self.SIZE
        self.range_after = new
        io.open(os.path.join(self.stage, "fontrange.bin"), "wb").write(new)
        io.open(os.path.join(self.stage, install.PLAN), "w",
                encoding="utf-8").write(json.dumps([{
                    "archive": self.ARCHIVE, "entry": entry,
                    "file": "fontrange.bin", "offset": offset,
                    "size": self.SIZE,
                    "sha256_before": sha_bytes(
                        self.body[offset:offset + self.SIZE]),
                    "sha256_after": sha_bytes(new)}]))

    def pak(self):
        return io.open(os.path.join(self.game, self.REL), "rb").read()


def main():
    failures = []

    def check(name, cond):
        print("  %-60s %s" % (name, "ok" if cond else "失败"))
        if not cond:
            failures.append(name)

    # tasklist is not going to find a game here; make the answer definite so the
    # running check does not stop every case.
    real_state = newfiles.running_state
    newfiles.running_state = lambda *a, **k: "stopped"

    root = tempfile.mkdtemp(prefix="cielzh-flow-")
    out = io.StringIO()
    real_stdout = sys.stdout
    try:
        def run(fx, *extra):
            sys.stdout = out
            try:
                return fx.run(*extra)
            finally:
                sys.stdout = real_stdout

        def run_text(fx, *extra):
            """The exit code and what it printed, for checks that are about the
            reason and not only about the code."""
            buf = io.StringIO()
            sys.stdout = buf
            try:
                rc = fx.run(*extra)
            finally:
                sys.stdout = real_stdout
            out.write(buf.getvalue())
            return rc, buf.getvalue()

        # --- a build with no manifest -----------------------------------------
        fx = Fixture(os.path.join(root, "nomanifest"))
        os.remove(os.path.join(fx.build, "manifest.json"))
        before = fx.snapshot()
        raised = False
        try:
            run(fx, "--apply")
        except SystemExit:
            raised = True
        check("构建缺少 manifest.json：停止", raised)
        check("  ……游戏目录未改动", fx.snapshot() == before)

        # --- first install ----------------------------------------------------
        fx = Fixture(os.path.join(root, "first"))
        check("首次安装成功", run(fx, "--apply") == 0)
        check("  ……DLL 已安装", os.path.exists(fx.dll))
        check("  ……记录了版本",
              newfiles.load_record(fx.backup)["files"]["cielzh.dll"]
              ["patch_version"] == "1.0.0")
        check("  ……没有残留事务", newfiles.load_tx(fx.backup) is None)
        check("  ……回滚副本已清理",
              not os.path.isdir(newfiles.rollback_dir(fx.backup)))
        check("  ……显示层的替换表也装上并登记了",
              sha_file(fx.table) == sha_bytes(b"table 1.0.0")
              and newfiles.load_record(fx.backup)["files"]["cielzh-text.bin"]
              ["installed_sha256"] == sha_bytes(b"table 1.0.0"))

        # --- same version again ------------------------------------------------
        after_first = fx.snapshot()
        check("同版本重装成功", run(fx, "--apply") == 0)
        check("  ……目录内容不变", fx.snapshot() == after_first)

        # --- upgrade ------------------------------------------------------------
        fx.restage("1.1.0")
        check("升级成功", run(fx, "--apply") == 0)
        check("  ……DLL 是新版",
              io.open(fx.dll, "rb").read() == b"dll 1.1.0")
        check("  ……替换表也是新版", sha_file(fx.table) == sha_bytes(b"table 1.1.0"))
        check("  ……记录了新版本",
              newfiles.load_record(fx.backup)["files"]["cielzh.dll"]
              ["patch_version"] == "1.1.0")

        # --- an unknown DLL must stop before anything is written ---------------
        fx2 = Fixture(os.path.join(root, "unknown"))
        io.open(fx2.dll, "wb").write(b"somebody else's cielzh.dll")
        before = fx2.snapshot()
        check("未知同名 DLL：安装被拒", run(fx2, "--apply") == 1)
        check("  ……整个游戏目录逐字节不变", fx2.snapshot() == before)
        check("  ……EXE 仍是原版",
              sha_file(os.path.join(fx2.game, "CielnosurgeDX.exe"))
              == fx2.originals["CielnosurgeDX.exe"])

        # A DLL on disk that the record does not account for is refused, whether
        # its bytes happen to match what we are about to install or not.  Only a
        # transaction says otherwise, and that case is exercised below.
        fx3 = Fixture(os.path.join(root, "halfway"))
        run(fx3, "--apply")
        fx3.restage("1.1.0")
        shutil.copyfile(os.path.join(fx3.stage, "cielzh.dll"), fx3.dll)
        before = fx3.snapshot()
        check("DLL 已是新版但记录仍是旧版且无事务：拒绝",
              run(fx3, "--apply") == 1)
        check("  ……目录未改动", fx3.snapshot() == before)

        # A whole install interrupted after the DLL step: the transaction and
        # the rollback copies survive, and the next run undoes the lot.  A
        # per-file record used to delete its own copy the moment that one file
        # succeeded, so a later failure could only fall back on Backup/ -- the
        # ORIGINAL -- and produced the original executable beside the new DLL.
        fx3b = Fixture(os.path.join(root, "halfway_real"))
        check("（前置）halfway_real 首次安装成功", run(fx3b, "--apply") == 0)
        old_exe = sha_file(os.path.join(fx3b.game, "CielnosurgeDX.exe"))
        old_dll = sha_file(fx3b.dll)
        fx3b.restage("1.1.0")

        real_save_plan = install.save_plan

        def boom(*_a, **_k):
            raise OSError(5, "injected failure after the DLL step")

        install.save_plan = boom
        try:
            rc = run(fx3b, "--apply")
        finally:
            install.save_plan = real_save_plan
        check("安装在 DLL 之后失败：返回失败", rc == 1)
        check("  ……EXE 回到本次安装前的版本（不是原版）",
              sha_file(os.path.join(fx3b.game, "CielnosurgeDX.exe")) == old_exe)
        check("  ……DLL 也回到安装前的版本", sha_file(fx3b.dll) == old_dll)
        check("  ……记录指回旧版本",
              newfiles.load_record(fx3b.backup)["files"]["cielzh.dll"]
              ["installed_sha256"] == old_dll)
        check("  ……事务与回滚副本都已清理",
              newfiles.load_tx(fx3b.backup) is None
              and not os.path.isdir(newfiles.rollback_dir(fx3b.backup)))
        check("  ……之后可以正常升级",
              run(fx3b, "--apply") == 0
              and sha_file(fx3b.dll) == sha_bytes(b"dll 1.1.0"))

        # --- a transaction left behind by a hard stop -------------------------
        # Simulated by killing the process: the transaction and the copies are on
        # disk, nothing has tidied up.
        fx4 = Fixture(os.path.join(root, "killed"))
        run(fx4, "--apply")
        before_exe = sha_file(os.path.join(fx4.game, "CielnosurgeDX.exe"))
        before_dll = sha_file(fx4.dll)
        fx4.restage("1.2.0")
        real_apply_one = newfiles.apply_one

        def die(*_a, **_k):
            raise KeyboardInterrupt("killed")

        newfiles.apply_one = die
        try:
            sys.stdout = out
            try:
                fx4.run("--apply")
            except KeyboardInterrupt:
                pass
            finally:
                sys.stdout = real_stdout
        finally:
            newfiles.apply_one = real_apply_one
        check("进程被杀：事务与回滚副本留在盘上",
              newfiles.load_tx(fx4.backup) is not None
              and os.path.isdir(newfiles.rollback_dir(fx4.backup)))
        check("  ……试运行只读，不改动任何记录",
              run(fx4) == 0
              and newfiles.load_tx(fx4.backup) is not None
              and sha_file(fx4.dll) == before_dll)
        check("下一次安装先撤销中断的那次，再装新版",
              run(fx4, "--apply") == 0
              and sha_file(fx4.dll) == sha_bytes(b"dll 1.2.0")
              and newfiles.load_tx(fx4.backup) is None)
        check("  ……被撤销的那次没有留下原版 EXE",
              sha_file(os.path.join(fx4.game, "CielnosurgeDX.exe"))
              != fx4.originals["CielnosurgeDX.exe"]
              and before_exe != "")

        # --- killed with the DLL replaced but not yet recorded -----------------
        # The window the transaction did not cover.  apply_one registered its own
        # step, so between os.replace and save_record the file had changed and
        # the transaction on disk said nothing about it: recovery put the
        # executable back, kept the new DLL, kept the old record, and deleted the
        # transaction.  A normal exception cannot stand in for this -- it
        # triggers the in-process rollback, which is a different path.
        real_save_record = newfiles.save_record

        def die_recording(*_a, **_k):
            raise KeyboardInterrupt("killed with the DLL replaced")

        def killed(fx, patch_name, fake, *extra):
            """Runs an install that is cut short the way a kill would cut it."""
            real = getattr(newfiles, patch_name)
            setattr(newfiles, patch_name, fake)
            sys.stdout = out
            try:
                fx.run(*extra)
            except KeyboardInterrupt:
                pass
            finally:
                sys.stdout = real_stdout
                setattr(newfiles, patch_name, real)

        fx4d = Fixture(os.path.join(root, "dll_window"))
        run(fx4d, "--apply")
        was_exe = sha_file(os.path.join(fx4d.game, "CielnosurgeDX.exe"))
        was_dll = sha_file(fx4d.dll)
        fx4d.restage("1.4.0")
        killed(fx4d, "save_record", die_recording, "--apply")
        tx = newfiles.load_tx(fx4d.backup)
        dll_steps = [s for s in (tx or {}).get("steps", [])
                     if s["rel"] == "cielzh.dll"]
        check("DLL 已替换但记录未保存时被杀：DLL 确实已是新版",
              sha_file(fx4d.dll) == sha_bytes(b"dll 1.4.0"))
        check("  ……事务里已经有这一步，且记着替换前的版本",
              len(dll_steps) == 1
              and dll_steps[0]["kind"] == "created"
              and dll_steps[0]["before_sha256"] == was_dll
              and dll_steps[0]["after_sha256"] == sha_bytes(b"dll 1.4.0")
              and dll_steps[0]["rollback"])
        check("  ……所有权记录还没来得及改",
              newfiles.load_record(fx4d.backup)["files"]["cielzh.dll"]
              ["installed_sha256"] == was_dll)
        ok_rb = newfiles.roll_back(fx4d.game, fx4d.backup, tx,
                                   report=lambda _m: None)
        check("  ……撤销后 DLL 回到安装前的版本（既没删除也没留在新版）",
              ok_rb and sha_file(fx4d.dll) == was_dll)
        check("  ……EXE 也回到安装前的版本",
              sha_file(os.path.join(fx4d.game, "CielnosurgeDX.exe")) == was_exe)
        check("  ……记录与盘上一致，恢复资料已清理",
              newfiles.load_record(fx4d.backup)["files"]["cielzh.dll"]
              ["installed_sha256"] == was_dll
              and newfiles.load_tx(fx4d.backup) is None
              and not os.path.isdir(newfiles.rollback_dir(fx4d.backup)))
        check("  ……之后可以正常升级到新版",
              run(fx4d, "--apply") == 0
              and sha_file(fx4d.dll) == sha_bytes(b"dll 1.4.0"))

        # --- killed with the DLL deleted but not yet recorded ------------------
        # The same window on the other side: --no-loader removes the file, and
        # between os.remove and save_record the transaction has to already know
        # both that it is going and what it held.
        fx4e = Fixture(os.path.join(root, "remove_window"))
        run(fx4e, "--apply")
        had_dll = sha_file(fx4e.dll)
        fx4e.restage("1.4.1", loader=False)
        killed(fx4e, "save_record", die_recording, "--apply")
        tx = newfiles.load_tx(fx4e.backup)
        gone = [s for s in (tx or {}).get("steps", [])
                if s["kind"] == "created_remove" and s["rel"] == "cielzh.dll"]
        check("DLL 已删除但记录未保存时被杀：文件确实不在了",
              not os.path.exists(fx4e.dll))
        check("  ……事务记着这一步和它的副本",
              len(gone) == 1 and gone[0]["before_sha256"] == had_dll
              and gone[0]["rollback"])
        check("  ……撤销把它放回来",
              newfiles.roll_back(fx4e.game, fx4e.backup, tx,
                                 report=lambda _m: None)
              and sha_file(fx4e.dll) == had_dll
              and newfiles.load_record(fx4e.backup)["files"]["cielzh.dll"]
              ["installed_sha256"] == had_dll)

        # --- killed after the commit point ------------------------------------
        # phase="done" means the install happened.  Undoing it deleted the DLL it
        # had just installed, because the copies were already cleaned up and "no
        # copy" was read as "we created this file".  All three points after the
        # commit have to come out the same way.
        def kill_cleanup(stage):
            def fake(backup, report=None):
                rdir = newfiles.rollback_dir(backup)
                names = sorted(os.listdir(rdir)) if os.path.isdir(rdir) else []
                if stage == "mid" and names:
                    os.remove(os.path.join(rdir, names[0]))
                elif stage == "after":
                    shutil.rmtree(rdir, ignore_errors=True)
                raise KeyboardInterrupt("killed after the commit point")
            return fake

        def outside_backup(snap):
            return {k: v for k, v in snap.items()
                    if k.split(os.sep)[0] != "Backup"}

        for stage, label in (("before", "刚写下 done"),
                             ("mid", "副本删了一半"),
                             ("after", "副本已删、事务未删")):
            fxk = Fixture(os.path.join(root, "committed_" + stage))
            killed(fxk, "cleanup", kill_cleanup(stage), "--apply")
            landed = outside_backup(fxk.snapshot())
            check("提交后被杀（%s）：事务上写着 done" % label,
                  newfiles.committed(newfiles.load_tx(fxk.backup)))
            check("  ……下一次运行只收尾，不回滚", run(fxk, "--apply") == 0)
            check("  ……装好的文件一字节未动（DLL 没有被删掉）",
                  outside_backup(fxk.snapshot()) == landed
                  and sha_file(fxk.dll) == sha_bytes(b"dll 1.0.0"))
            check("  ……恢复资料已清理干净",
                  newfiles.load_tx(fxk.backup) is None
                  and not os.path.isdir(newfiles.rollback_dir(fxk.backup)))

        # --- recovery data that is missing or damaged --------------------------
        # A rollback used to skip a missing copy, and write a damaged one over the
        # target, and report success either way -- then delete the evidence.
        # The folder is not named after the damage: "missing" in the output was
        # first matched by the fixture's own path, which made the check below
        # pass with the fix reverted.
        for damage, word, said_it in (
                ("gone", "丢失",
                 "the copy of the version installed before it is missing"),
                ("bad", "损坏",
                 "the copy of the version installed before it is damaged")):
            fxr = Fixture(os.path.join(root, "rollback_" + damage))
            run(fxr, "--apply")
            fxr.restage("1.5.0")
            killed(fxr, "save_record", die_recording, "--apply")
            rdir = newfiles.rollback_dir(fxr.backup)
            copies = [f for f in os.listdir(rdir) if f.endswith("cielzh.dll")]
            check("回滚副本%s：（前置）升级的 DLL 只留了一份副本" % word,
                  len(copies) == 1)
            victim = os.path.join(rdir, copies[0])
            if damage == "gone":
                os.remove(victim)
            else:
                io.open(victim, "wb").write(b"not the dll that was there")
            rc, said = run_text(fxr, "--apply")
            # The return code alone is not enough: with the check removed the
            # rollback "succeeds", and the run still fails -- one step later, at
            # the ownership check, for a different reason.  What has to be true
            # is that it stopped on this copy, and said so.
            check("  ……撤销被拒绝，理由就是这份副本",
                  rc == 1 and said_it in said and "cielzh.dll" in said)
            check("  ……DLL 既没被删除，也没被副本的内容覆盖",
                  sha_file(fxr.dll) == sha_bytes(b"dll 1.5.0"))
            check("  ……事务与其余副本都留在盘上",
                  newfiles.load_tx(fxr.backup) is not None
                  and os.path.isdir(rdir))
            check("  ……再运行一次还是同样的拒绝", run(fxr, "--apply") == 1)

        # --- the record must not claim a file that did not come back ----------
        # Interrupted after the DLL was installed AND recorded, so the record
        # names the new version.  If its copy is then unusable, the rollback has
        # to leave the record naming the new version -- which is what is on disk.
        # Moving it back for a step that failed made the next run refuse for the
        # wrong reason, on a file that had never been put back.
        fxq = Fixture(os.path.join(root, "record_claim"))
        run(fxq, "--apply")
        fxq.restage("1.6.0")
        real_save_plan2 = install.save_plan

        def die_late(*_a, **_k):
            raise KeyboardInterrupt("killed after the DLL was recorded")

        install.save_plan = die_late
        try:
            sys.stdout = out
            try:
                fxq.run("--apply")
            except KeyboardInterrupt:
                pass
            finally:
                sys.stdout = real_stdout
        finally:
            install.save_plan = real_save_plan2
        new_dll = sha_bytes(b"dll 1.6.0")
        check("记录已写、事务未收尾时被杀：记录指向新版",
              sha_file(fxq.dll) == new_dll
              and newfiles.load_record(fxq.backup)["files"]["cielzh.dll"]
              ["installed_sha256"] == new_dll)
        rdir = newfiles.rollback_dir(fxq.backup)
        for f in os.listdir(rdir):
            if f.endswith("cielzh.dll"):
                os.remove(os.path.join(rdir, f))
        check("  ……副本不可用时撤销被拒绝", run(fxq, "--apply") == 1)
        check("  ……记录仍指向盘上那一版，而不是宣布已恢复",
              sha_file(fxq.dll) == new_dll
              and newfiles.load_record(fxq.backup)["files"]["cielzh.dll"]
              ["installed_sha256"] == new_dll)

        # --- the undo is interrupted while writing the file back ---------------
        # A continuous chain: the install is cut short, then the undo is cut
        # short in the middle of putting the DLL back.  copyfile straight onto
        # the target left a partial DLL there, and the next attempt found a file
        # that was neither version.
        fx6 = Fixture(os.path.join(root, "undo_cut"))
        run(fx6, "--apply")
        was_dll6 = sha_file(fx6.dll)
        fx6.restage("1.7.0")
        killed(fx6, "save_record", die_recording, "--apply")
        tx6 = newfiles.load_tx(fx6.backup)
        calls = [0]
        real_copyfileobj = shutil.copyfileobj

        def half_then_die(src, dst, *a, **k):
            calls[0] += 1
            dst.write(src.read(4))
            dst.flush()
            raise KeyboardInterrupt("killed while putting the file back")

        shutil.copyfileobj = half_then_die
        try:
            newfiles.roll_back(fx6.game, fx6.backup, tx6,
                               report=lambda _m: None)
        except KeyboardInterrupt:
            pass
        finally:
            shutil.copyfileobj = real_copyfileobj
        check("撤销过程中被杀：确实是在写回 DLL 时被打断", calls[0] == 1)
        check("  ……DLL 没有变成半截（仍是撤销前的内容）",
              sha_file(fx6.dll) == sha_bytes(b"dll 1.7.0"))
        check("  ……事务与副本都还在",
              newfiles.load_tx(fx6.backup) is not None
              and os.path.isdir(newfiles.rollback_dir(fx6.backup)))
        check("  ……重试撤销即可完成",
              newfiles.roll_back(fx6.game, fx6.backup,
                                 newfiles.load_tx(fx6.backup),
                                 report=lambda _m: None)
              and sha_file(fx6.dll) == was_dll6
              and newfiles.load_tx(fx6.backup) is None)
        # Named outright rather than by pattern: a check for "nothing that looks
        # like a temp file" would not notice one under a name nobody guessed.
        check("  ……游戏目录里没有多出任何文件",
              sorted(os.listdir(fx6.game))
              == sorted(["Backup", "Res_x64", "cielzh.dll", "cielzh-text.bin",
                         "CielnosurgeDX.exe", "CielnosurgeDX_Env.exe"]))

        # --- a file whose name looks like ours is still not ours ---------------
        # The undo used to spool to dst + a fixed suffix and remove whatever was
        # already at that name first.  O_EXCL guards the creation, not that
        # removal, so a file of that name we had never written was deleted.
        fx6b = Fixture(os.path.join(root, "lookalike"))
        run(fx6b, "--apply")
        was_dll6b = sha_file(fx6b.dll)
        fx6b.restage("1.7.1")
        killed(fx6b, "save_record", die_recording, "--apply")
        decoys = {}
        for suffix in (".cielzh-undo", ".cielzh-new", ".part"):
            p = fx6b.dll + suffix
            io.open(p, "wb").write(b"somebody else's file" + suffix.encode())
            decoys[p] = sha_file(p)
        tx6b = newfiles.load_tx(fx6b.backup)
        check("同名旁路文件：撤销照样完成",
              newfiles.roll_back(fx6b.game, fx6b.backup, tx6b,
                                 report=lambda _m: None)
              and sha_file(fx6b.dll) == was_dll6b)
        check("  ……但它们一个都没被删除或改动",
              all(sha_file(p) == h for p, h in decoys.items()))
        # Again with the same transaction, which is what happens when a rollback
        # finished but could not clear its own recovery data.  Every step is now
        # back as it was, and that branch used to delete anything beside the
        # target whose name looked like one of ours.
        for p in decoys:
            io.open(p, "wb").write(b"put back by somebody else")
            decoys[p] = sha_file(p)
        check("已经恢复好之后再跑一次：仍然成功",
              newfiles.roll_back(fx6b.game, fx6b.backup, tx6b,
                                 report=lambda _m: None)
              and sha_file(fx6b.dll) == was_dll6b)
        check("  ……同名旁路文件依然没被动过",
              all(sha_file(p) == h for p, h in decoys.items()))

        # --- a target that is neither version must stop the undo ---------------
        # What an older build's interrupted undo would have left behind.  It used
        # to be reported as "left untouched", counted as a success, and the
        # recovery data deleted.
        fx7 = Fixture(os.path.join(root, "torn"))
        run(fx7, "--apply")
        fx7.restage("1.8.0")
        killed(fx7, "save_record", die_recording, "--apply")
        io.open(fx7.dll, "wb").write(b"dll 1.")          # neither version
        torn = sha_file(fx7.dll)
        rc, said = run_text(fx7, "--apply")
        check("DLL 既非旧版也非新版：撤销失败而不是「保留不动」",
              rc == 1 and "cielzh.dll" in said and "neither" in said)
        check("  ……那半截文件一字不动", sha_file(fx7.dll) == torn)
        check("  ……事务与副本都保留下来",
              newfiles.load_tx(fx7.backup) is not None
              and os.path.isdir(newfiles.rollback_dir(fx7.backup)))
        check("  ……把它移开之后即可继续",
              (os.remove(fx7.dll) or run(fx7, "--apply")) == 0
              and sha_file(fx7.dll) == sha_bytes(b"dll 1.8.0"))

        # --- a build that patches a different range than the one installed -----
        # No injection: installing writes only its own ranges and then replaces
        # the restore plan, so the previous build's bytes stayed in the archive
        # with nothing left pointing at them, and --restore reported success with
        # the old translation still there.  Migrating between layouts is not
        # supported, so this has to be refused rather than half done.
        fx8 = RangeFixture(os.path.join(root, "range_layout"), offset=100,
                           mark=b"A")
        check("区间计划：首次安装成功", run(fx8, "--apply") == 0)
        check("  ……区间已写入，其余字节未动",
              fx8.pak()[100:116] == b"A" * 16
              and fx8.pak()[:100] == fx8.body[:100]
              and fx8.pak()[116:] == fx8.body[116:])
        after_v1 = fx8.pak()
        fx8.restage("2.0.0")
        fx8.set_range(200, b"B")
        rc, said = run_text(fx8, "--apply")
        check("改写区间与已安装版本不同：拒绝覆盖安装",
              rc == 1 and "offset 100" in said and "--restore" in said)
        check("  ……封包一字节未动", fx8.pak() == after_v1)
        check("  ……还原计划仍是已安装那一版",
              install.load_applied_plan(fx8.backup)[0]["offset"] == 100)
        check("  ……--force 也不行（这不是游戏版本的问题）",
              run(fx8, "--apply", "--force") == 1
              and fx8.pak() == after_v1)
        check("先还原再安装：封包先回到原版",
              run(fx8, "--restore") == 0
              and sha_bytes(fx8.pak()) == fx8.pristine)
        check("  ……新版随后可以安装",
              run(fx8, "--apply") == 0
              and fx8.pak()[200:216] == b"B" * 16
              and fx8.pak()[100:116] == fx8.body[100:116])
        check("  ……再卸载后整个封包等于原版",
              run(fx8, "--restore") == 0
              and sha_bytes(fx8.pak()) == fx8.pristine)
        # a start of the game leaves these; an original game has no use for them
        run(fx8, "--apply")
        for name in install.RUN_RECORDS:
            io.open(os.path.join(fx8.game, name), "w").write("cielzh loader=rc=00000000")
        check("卸载时一并清掉启动记录，--verify 不再报告旧补丁的状态",
              run(fx8, "--restore") == 0
              and not any(os.path.exists(os.path.join(fx8.game, n))
                          for n in install.RUN_RECORDS)
              and install.display_status(fx8.game) == "display layer: not installed")

        # --- the layout check belongs after the rollback, not before it --------
        # An interrupted upgrade leaves the range holding the new bytes and the
        # plan still naming the old ones.  Deciding the layout from that stale
        # pair let a third build through: it installed, --restore reported
        # success, and the first build's bytes stayed in the archive.
        fx8d = RangeFixture(os.path.join(root, "range_pending"), offset=100,
                            mark=b"A", entry="atlas v1")
        run(fx8d, "--apply")
        fx8d.restage("2.3.0")
        fx8d.set_range(100, b"B", entry="atlas v2")
        real_save_plan3 = install.save_plan

        def save_plan_killed(*_a, **_k):
            raise KeyboardInterrupt("killed before the plan was written")

        install.save_plan = save_plan_killed
        try:
            sys.stdout = out
            try:
                fx8d.run("--apply")
            except KeyboardInterrupt:
                pass
            finally:
                sys.stdout = real_stdout
        finally:
            install.save_plan = real_save_plan3
        check("升级在写计划前被杀：区间是新版，计划还是旧版",
              fx8d.pak()[100:116] == b"B" * 16
              and install.load_applied_plan(fx8d.backup)[0]["sha256_after"]
              == sha_bytes(b"A" * 16)
              and newfiles.load_tx(fx8d.backup) is not None)
        fx8d.restage("3.0.0")
        fx8d.set_range(200, b"C", entry="atlas v3")
        rc, said = run_text(fx8d, "--apply")
        check("  ……换装另一段区间的版本：撤销之后被拒绝",
              rc == 1 and "offset 100" in said and "--restore" in said)
        check("  ……撤销确实做完了（区间回到 A，200 未被写入）",
              fx8d.pak()[100:116] == b"A" * 16
              and fx8d.pak()[200:216] == fx8d.body[200:216]
              and newfiles.load_tx(fx8d.backup) is None)
        check("  ……先卸载再装，封包最终等于原版",
              run(fx8d, "--restore") == 0
              and run(fx8d, "--apply") == 0
              and run(fx8d, "--restore") == 0
              and sha_bytes(fx8d.pak()) == fx8d.pristine)

        # Deferring that check must not turn into refusing what the rollback
        # makes installable: the same interruption, then a build with the same
        # layout, has to go through.
        fx8e = RangeFixture(os.path.join(root, "range_pending_ok"), offset=100,
                            mark=b"A", entry="atlas v1")
        run(fx8e, "--apply")
        fx8e.restage("2.3.0")
        fx8e.set_range(100, b"B", entry="atlas v2")
        install.save_plan = save_plan_killed
        try:
            sys.stdout = out
            try:
                fx8e.run("--apply")
            except KeyboardInterrupt:
                pass
            finally:
                sys.stdout = real_stdout
        finally:
            install.save_plan = real_save_plan3
        check("同样的中断，但新版改写同一段区间：撤销后照常安装",
              run(fx8e, "--apply") == 0
              and fx8e.pak()[100:116] == b"B" * 16)
        check("  ……之后卸载得到原版",
              run(fx8e, "--restore") == 0
              and sha_bytes(fx8e.pak()) == fx8e.pristine)

        # --- a range somebody else changed is not "already restored" ----------
        # "not the old output" was read as "back to the original", so an edited
        # range went through as though it were pristine.
        fx8f = RangeFixture(os.path.join(root, "range_edited"), offset=100,
                            mark=b"A", entry="atlas v1")
        run(fx8f, "--apply")
        edited = bytearray(fx8f.pak())
        edited[100] = ord("X")
        io.open(os.path.join(fx8f.game, fx8f.REL), "wb").write(bytes(edited))
        fx8f.restage("3.1.0")
        fx8f.set_range(200, b"C", entry="atlas v3")
        rc, said = run_text(fx8f, "--apply")
        check("旧区间被人改过：既不算旧补丁也不算原版，拒绝安装",
              rc == 1 and "offset 100" in said and "neither" in said)
        check("  ……封包一字节未动", fx8f.pak() == bytes(edited))
        check("  ……--force 也不行", run(fx8f, "--apply", "--force") == 1
              and fx8f.pak() == bytes(edited))
        check("  ……按提示先卸载，被改动的区间也回到原版",
              run(fx8f, "--restore") == 0
              and sha_bytes(fx8f.pak()) == fx8f.pristine)
        check("  ……然后可以安装新版",
              run(fx8f, "--apply") == 0
              and fx8f.pak()[200:216] == b"C" * 16)

        # before == after means that step wrote what was already there.
        here = io.open(os.path.join(fx8f.game, fx8f.REL), "rb").read()[300:316]
        same = sha_bytes(here)
        check("before 与 after 相同：按「已是原版」处理",
              install.range_state(fx8f.game, {
                  "archive": RangeFixture.ARCHIVE, "offset": 300, "size": 16,
                  "sha256_before": same, "sha256_after": same}) == "original")
        check("  ……读取不足或文件缺失：算无法解释",
              install.range_state(fx8f.game, {
                  "archive": RangeFixture.ARCHIVE, "offset": 4090, "size": 16,
                  "sha256_before": same, "sha256_after": same}) == "unknown"
              and install.range_state(fx8f.game, {
                  "archive": "NOSUCH.PAK", "offset": 0, "size": 16,
                  "sha256_before": same, "sha256_after": same}) == "unknown")

        # --- same layout, new bytes, failing at the commit point ---------------
        # An upgrade that is allowed: the same range, written differently.  What
        # is checked here is that Backup/ stays internally consistent -- the
        # restore plan describes the bytes actually in the archive, because it is
        # part of the transaction.
        fx8c = RangeFixture(os.path.join(root, "range_same"), offset=100,
                            mark=b"A")
        run(fx8c, "--apply")
        after_a = fx8c.pak()
        fx8c.restage("2.2.0")
        fx8c.set_range(100, b"B")
        real_txn_finish = newfiles.Txn.finish

        def boom_finish(self, report=None):
            raise OSError(5, "injected failure at the commit point")

        newfiles.Txn.finish = boom_finish
        try:
            rc = run(fx8c, "--apply")
        finally:
            newfiles.Txn.finish = real_txn_finish
        check("同布局升级在提交点失败：返回失败，封包回到升级前",
              rc == 1 and fx8c.pak() == after_a)
        applied = install.load_applied_plan(fx8c.backup)
        check("  ……还原计划描述的是盘上那一版的字节",
              len(applied) == 1 and applied[0]["offset"] == 100
              and applied[0]["sha256_after"] == sha_bytes(b"A" * 16))
        check("  ……--verify 认为已安装的就是计划里那一版",
              run(fx8c, "--verify") == 0)
        check("  ……--restore 之后封包等于原版",
              run(fx8c, "--restore") == 0
              and sha_bytes(fx8c.pak()) == fx8c.pristine)
        check("  ……之后可以安装同布局的新版",
              run(fx8c, "--apply") == 0
              and fx8c.pak()[100:116] == b"B" * 16)

        # --- --restore has to undo first, then read the plan it restored -------
        # Killed between writing the restore plan and finishing the transaction,
        # so the plan on disk is the new build's while the transaction is still
        # open.  --restore undoes that install and then uses the plan it put
        # back, not the one it read on the way in.
        fx8b = RangeFixture(os.path.join(root, "range_restore"), offset=100,
                            mark=b"A")
        fx8b.set_range(100, b"A", entry="atlas as installed")
        run(fx8b, "--apply")
        fx8b.restage("2.1.0")
        fx8b.set_range(100, b"B", entry="atlas from the attempt")

        def finish_killed(self, report=None):
            raise KeyboardInterrupt("killed at the commit point")

        newfiles.Txn.finish = finish_killed
        try:
            sys.stdout = out
            try:
                fx8b.run("--apply")
            except KeyboardInterrupt:
                pass
            finally:
                sys.stdout = real_stdout
        finally:
            newfiles.Txn.finish = real_txn_finish
        check("提交前被杀：事务还在，且还原计划已经是新版",
              newfiles.load_tx(fx8b.backup) is not None
              and install.load_applied_plan(fx8b.backup)[0]["sha256_after"]
              == sha_bytes(b"B" * 16))
        rc, said = run_text(fx8b, "--restore")
        check("  ……--restore 先撤销，再还原到原版",
              rc == 0 and sha_bytes(fx8b.pak()) == fx8b.pristine)
        # Both plans cover the same range here, so the bytes come out the same
        # either way; the label is what says which plan it actually worked from.
        check("  ……依据的是撤销后的那份计划（不是进来时读到的那份）",
              "atlas as installed" in said
              and "atlas from the attempt" not in said)
        check("  ……撤销后的计划回到已安装那一版",
              install.load_applied_plan(fx8b.backup)[0]["sha256_after"]
              == sha_bytes(b"A" * 16))

        # --- a stale folder that will not go away -----------------------------
        # Removing those folders is tidying: the engine ignores them.  It happens
        # after the commit point, so a failure is reported and does not undo an
        # install that worked.  Inside the transaction it was an unrecorded
        # change -- deleted on the way in, not put back on the way out.
        fx10 = Fixture(os.path.join(root, "stale"))
        stale_dir = os.path.join(fx10.game, install.STALE[0])
        os.makedirs(stale_dir, exist_ok=True)
        io.open(os.path.join(stale_dir, "leftover.txt"), "wb").write(b"old")
        real_rmtree = shutil.rmtree

        def rmtree_refuses(path, *a, **k):
            if os.path.basename(path) == install.STALE[0]:
                raise OSError(13, "injected: in use")
            return real_rmtree(path, *a, **k)

        shutil.rmtree = rmtree_refuses
        try:
            rc = run(fx10, "--apply")
        finally:
            shutil.rmtree = real_rmtree
        check("旧目录删不掉：安装仍然成功", rc == 0)
        check("  ……装好的文件都在，事务已收尾",
              sha_file(fx10.dll) == sha_bytes(b"dll 1.0.0")
              and sha_file(os.path.join(fx10.game, "CielnosurgeDX.exe"))
              != fx10.originals["CielnosurgeDX.exe"]
              and newfiles.load_tx(fx10.backup) is None)

        # --- inplace.json when there was none before --------------------------
        fx9 = RangeFixture(os.path.join(root, "range_first"), offset=64,
                           mark=b"C")
        newfiles.Txn.finish = boom_finish
        try:
            rc = run(fx9, "--apply")
        finally:
            newfiles.Txn.finish = real_txn_finish
        check("首次安装在提交点失败：封包回到原版", rc == 1
              and sha_bytes(fx9.pak()) == fx9.pristine)
        check("  ……本来不存在的还原计划被删掉，而不是留下一份",
              not os.path.exists(os.path.join(fx9.backup, install.PLAN)))

        # --- --force must not bypass an ownership refusal ----------------------
        fx4b = Fixture(os.path.join(root, "forced"))
        io.open(fx4b.dll, "wb").write(b"unknown cielzh.dll")
        before = fx4b.snapshot()
        check("--force 不能绕过所有权拒绝", run(fx4b, "--apply", "--force") == 1)
        check("  ……游戏目录逐字节不变", fx4b.snapshot() == before)
        check("  ……没有写下所有权记录",
              "cielzh.dll" not in newfiles.load_record(fx4b.backup)["files"])

        # --- --no-loader must not delete a DLL somebody changed ---------------
        fx4c = Fixture(os.path.join(root, "changed_dll"))
        run(fx4c, "--apply")
        io.open(fx4c.dll, "wb").write(b"replaced by something else")
        before = fx4c.snapshot()
        fx4c.restage("1.3.0", loader=False)
        check("--no-loader 不删除被改动过的 DLL",
              run(fx4c, "--apply") == 1)
        check("  ……那个文件还在，内容未变", fx4c.snapshot() == before)

        # --- --no-loader --------------------------------------------------------
        fx5 = Fixture(os.path.join(root, "noloader"), loader=False)
        check("--no-loader 构建可以安装", run(fx5, "--apply") == 0)
        check("  ……没有安装 DLL", not os.path.exists(fx5.dll))
        check("  ……记录里也没有它",
              "cielzh.dll" not in newfiles.load_record(fx5.backup)["files"])

        fx6 = Fixture(os.path.join(root, "downgrade"))
        run(fx6, "--apply")
        check("先装带 DLL 的版本，再装 --no-loader：DLL 被移除",
              os.path.exists(fx6.dll)
              and (fx6.restage("1.2.0", loader=False) or True)
              and run(fx6, "--apply") == 0
              and not os.path.exists(fx6.dll))
        check("  ……记录里也清掉了",
              "cielzh.dll" not in newfiles.load_record(fx6.backup)["files"])
        check("  ……替换表同样移除并清掉记录",
              not os.path.exists(fx6.table)
              and "cielzh-text.bin" not in newfiles.load_record(fx6.backup)["files"])

        # The table follows the same ownership rules as the DLL.
        fx6t = Fixture(os.path.join(root, "table_changed"))
        run(fx6t, "--apply")
        io.open(fx6t.table, "wb").write(b"somebody else's table")
        before = fx6t.snapshot()
        fx6t.restage("1.2.1")
        check("替换表被改动过：拒绝安装，目录逐字节不变",
              run(fx6t, "--apply") == 1 and fx6t.snapshot() == before)

        # --- restore ------------------------------------------------------------
        fx7 = Fixture(os.path.join(root, "restore"))
        run(fx7, "--apply")
        check("还原成功", run(fx7, "--restore") == 0)
        for rel, h in fx7.originals.items():
            if not os.path.exists(os.path.join(fx7.game, rel)):
                continue
            check("  ……%s 回到原版" % rel,
                  sha_file(os.path.join(fx7.game, rel)) == h)
        check("  ……DLL 已删除", not os.path.exists(fx7.dll))
        check("  ……替换表已删除", not os.path.exists(fx7.table))

        # --- the running check covers restore too -------------------------------
        fx8 = Fixture(os.path.join(root, "running"))
        run(fx8, "--apply")
        before = fx8.snapshot()
        newfiles.running_state = lambda *a, **k: "running"
        check("游戏在运行：安装被拒", run(fx8, "--apply") == 1)
        check("游戏在运行：还原也被拒", run(fx8, "--restore") == 1)
        newfiles.running_state = lambda *a, **k: "unknown"
        check("无法确认是否在运行：安装被拒（不当作已退出）",
              run(fx8, "--apply") == 1)
        check("  ……--force 可以继续", run(fx8, "--apply", "--force") == 0)
        newfiles.running_state = lambda *a, **k: "stopped"
        check("  ……以上过程中目录未被破坏",
              sha_file(fx8.dll) == sha_bytes(b"dll 1.0.0"))

        # --- running_state itself ----------------------------------------------
        # The cases above replace running_state wholesale, so they say nothing
        # about what it decides.  Here the query is made to fail.
        newfiles.running_state = real_state
        import subprocess as _sp
        real_run = _sp.run

        class R:
            def __init__(self, rc, out):
                self.returncode = rc
                self.stdout = out

        _sp.run = lambda *a, **k: (_ for _ in ()).throw(OSError("no tasklist"))
        try:
            check("tasklist 无法执行：状态为 unknown，不是 stopped",
                  newfiles.running_state() == "unknown")
            _sp.run = lambda *a, **k: R(1, b"")
            check("tasklist 返回非零：状态为 unknown",
                  newfiles.running_state() == "unknown")
            _sp.run = lambda *a, **k: R(0, None)
            check("tasklist 输出读不到：状态为 unknown",
                  newfiles.running_state() == "unknown")
            _sp.run = lambda *a, **k: R(0, b"INFO: no tasks")
            check("tasklist 说没有该进程：状态为 stopped",
                  newfiles.running_state() == "stopped")
            # what a Chinese Windows prints, in GBK, which is not valid UTF-8
            _sp.run = lambda *a, **k: R(0, "信息: 没有运行的任务匹配指定标准。".encode("gbk"))
            check("中文系统的 GBK 输出：不依赖解码，状态为 stopped",
                  newfiles.running_state() == "stopped")
            _sp.run = lambda *a, **k: R(0, b"CielnosurgeDX.exe  1234 Console")
            check("tasklist 列出该进程：状态为 running",
                  newfiles.running_state() == "running")
        finally:
            _sp.run = real_run

    finally:
        sys.stdout = real_stdout
        newfiles.running_state = real_state
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
