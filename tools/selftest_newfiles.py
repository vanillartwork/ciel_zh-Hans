# -*- coding: utf-8 -*-
"""Checks on the ownership record and the commit journal.

  py -3 selftest_newfiles.py

No game files: a temporary folder stands in for the game and for Backup/, and
the "DLL" is a few bytes.  What is being tested is the bookkeeping, and the
bookkeeping is the part that decides whether uninstall deletes somebody else's
file.

Every refusal has to be a Stop.  Treating any exception as a refusal hides the
difference between a decision and a crash.
"""
import sys, os, io, json, shutil, hashlib, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import newfiles                     # noqa: E402
from newfiles import Stop           # noqa: E402


def quiet(*_a, **_k):
    pass


def main():
    failures = []

    def check(name, cond):
        print("  %-58s %s" % (name, "ok" if cond else "失败"))
        if not cond:
            failures.append(name)

    def stops(fn):
        try:
            fn()
        except Stop:
            return True
        except Exception as e:          # noqa: BLE001
            print("      不是 Stop，而是 %s: %s" % (type(e).__name__, e))
            return False
        return False

    # This suite is about one file's bookkeeping.  The real list has two (the
    # DLL and its text table); the pair is driven through install.main() in
    # selftest_install_flow.py, and the end of this suite checks that a build
    # missing either is refused.
    real_created = newfiles.CREATED
    newfiles.CREATED = [("cielzh.dll", "cielzh.dll")]
    root = tempfile.mkdtemp(prefix="cielzh-nf-")
    try:
        game = os.path.join(root, "game")
        backup = os.path.join(game, "Backup")
        stage = os.path.join(root, "stage")
        for d in (game, backup, stage):
            os.makedirs(d, exist_ok=True)

        def staged(body):
            p = os.path.join(stage, "cielzh.dll")
            io.open(p, "wb").write(body)
            return {"cielzh.dll": p}

        v1 = staged(b"dll version one")
        dll = os.path.join(game, "cielzh.dll")

        # --- first install ---------------------------------------------------
        rec, actions = newfiles.plan(game, backup, v1, "0.9.9", report=quiet)
        check("首次安装：计划为 create",
              len(actions) == 1 and actions[0]["mode"] == "create")
        txn = newfiles.Txn(game, backup, "0.9.9")
        newfiles.register(txn, actions)
        txn.begin()
        newfiles.apply_one(game, backup, rec, actions[0], "0.9.9", txn,
                           report=quiet)
        txn.finish()
        check("首次安装：文件已就位", os.path.exists(dll))
        r = newfiles.load_record(backup)
        check("首次安装：记录了哈希与版本",
              r["files"]["cielzh.dll"]["installed_sha256"]
              == hashlib.sha256(b"dll version one").hexdigest()
              and r["files"]["cielzh.dll"]["patch_version"] == "0.9.9"
              and r["files"]["cielzh.dll"]["existed_before"] is False)

        # --- same version again ---------------------------------------------
        rec, actions = newfiles.plan(game, backup, v1, "0.9.9", report=quiet)
        check("同版本重装：识别为已是本版",
              actions[0]["mode"] == "current")
        txn = newfiles.Txn(game, backup, "0.9.9")
        changed = newfiles.apply_one(game, backup, rec, actions[0], "0.9.9",
                                     txn, report=quiet)
        check("  ……不重复写入", changed is False)

        # --- upgrade ---------------------------------------------------------
        v2 = staged(b"dll version two, longer")
        rec, actions = newfiles.plan(game, backup, v2, "1.0.0", report=quiet)
        check("跨版本升级：计划为 replace", actions[0]["mode"] == "replace")
        txn = newfiles.Txn(game, backup, "1.0.0")
        newfiles.register(txn, actions)
        txn.begin()
        newfiles.apply_one(game, backup, rec, actions[0], "1.0.0", txn,
                           report=quiet)
        txn.finish()
        r = newfiles.load_record(backup)
        check("升级后：内容与记录都更新",
              io.open(dll, "rb").read() == b"dll version two, longer"
              and r["files"]["cielzh.dll"]["patch_version"] == "1.0.0")

        # --- a copy we did not install ---------------------------------------
        io.open(dll, "wb").write(b"edited by somebody else")
        check("文件被改动过：拒绝安装",
              stops(lambda: newfiles.plan(game, backup, v2, "1.0.0",
                                          report=quiet)))
        check("  ……文件未被覆盖",
              io.open(dll, "rb").read() == b"edited by somebody else")
        check("卸载：不删除不属于我们的副本",
              newfiles.remove_all(game, backup, report=quiet) == (0, 1)
              and os.path.exists(dll))

        # --- an unknown file with our name, no record ------------------------
        shutil.rmtree(backup)
        os.makedirs(backup)
        io.open(dll, "wb").write(b"a stranger's cielzh.dll")
        check("同名文件但无安装记录：拒绝",
              stops(lambda: newfiles.plan(game, backup, v2, "1.0.0",
                                          report=quiet)))
        check("  ……文件未被覆盖",
              io.open(dll, "rb").read() == b"a stranger's cielzh.dll")
        removed, left = newfiles.remove_all(game, backup, report=quiet)
        check("卸载：无记录则完全不碰",
              removed == 0 and left == 1
              and io.open(dll, "rb").read() == b"a stranger's cielzh.dll")

        # --- uninstall of a file that is ours --------------------------------
        os.remove(dll)
        rec, actions = newfiles.plan(game, backup, v2, "1.0.0", report=quiet)
        txn = newfiles.Txn(game, backup, "1.0.0")
        newfiles.register(txn, actions)
        txn.begin()
        newfiles.apply_one(game, backup, rec, actions[0], "1.0.0", txn,
                           report=quiet)
        txn.finish()
        removed, left = newfiles.remove_all(game, backup, report=quiet)
        check("卸载：属于我们的副本被删除",
              removed == 1 and left == 0 and not os.path.exists(dll))
        check("  ……记录中也移除了该条",
              "cielzh.dll" not in newfiles.load_record(backup)["files"])

        # --- a record of a file that is already gone --------------------------
        # "forget" changes no file, only the record -- and that has to be
        # undoable too, or an install that fails after it leaves the record
        # saying a file was never ours.
        v3 = staged(b"dll version three")
        rec, actions = newfiles.plan(game, backup, v3, "1.1.0", report=quiet)
        txn = newfiles.Txn(game, backup, "1.1.0")
        newfiles.register(txn, actions)
        txn.begin()
        newfiles.apply_one(game, backup, rec, actions[0], "1.1.0", txn,
                           report=quiet)
        txn.finish()
        os.remove(dll)                       # the player deleted it
        rec, actions = newfiles.plan(game, backup, {}, "1.2.0",
                                     loader_enabled=False, report=quiet)
        check("记录在、文件已不在：计划为 forget", actions[0]["mode"] == "forget")
        txn = newfiles.Txn(game, backup, "1.2.0")
        newfiles.register(txn, actions)
        check("  ……登记为 record_only，并记下原来的记录",
              txn.data["steps"][0]["kind"] == "record_only"
              and txn.data["steps"][0]["before_record"]["installed_sha256"]
              == hashlib.sha256(b"dll version three").hexdigest())
        txn.begin()
        newfiles.apply_one(game, backup, rec, actions[0], "1.2.0", txn,
                           report=quiet)
        check("  ……记录里已经没有它",
              "cielzh.dll" not in newfiles.load_record(backup)["files"])
        check("撤销 forget：记录回到原样",
              newfiles.roll_back(game, backup, txn.data, report=quiet)
              and newfiles.load_record(backup)["files"]["cielzh.dll"]
              ["installed_sha256"]
              == hashlib.sha256(b"dll version three").hexdigest())

        # --- a committed transaction is never undone --------------------------
        txn = newfiles.Txn(game, backup, "1.2.0")
        txn.data["phase"] = "done"
        check("已提交的事务不会被回滚",
              stops(lambda: newfiles.roll_back(game, backup, txn.data,
                                               report=quiet)))
        check("  ……committed() 认得这个状态",
              newfiles.committed(txn.data)
              and not newfiles.committed({"phase": "committing"})
              and not newfiles.committed(None))

        # --- every step is registered before the install starts ---------------
        txn = newfiles.Txn(game, backup, "1.2.0")
        txn.begin()
        check("开始之后再登记步骤：拒绝",
              stops(lambda: txn.add("created", "cielzh.dll", None, "x")))

        # The install-wide transaction has its own cases in
        # selftest_install_flow.py, where a real install can be interrupted.

        # --- the build must actually contain the DLL --------------------------
        check("构建产物缺少 DLL：拒绝",
              stops(lambda: newfiles.plan(game, backup, {}, "1.0.0",
                                          report=quiet)))

        # The real list: a loader build with the DLL but no table is refused,
        # rather than installed as a display layer with nothing to display.
        newfiles.CREATED = real_created
        shutil.rmtree(backup)
        os.makedirs(backup)
        if os.path.exists(dll):
            os.remove(dll)
        check("真实配置：只有 DLL、缺替换表的构建被拒绝",
              stops(lambda: newfiles.plan(game, backup, staged(b"dll"), "1.0.0",
                                          report=quiet)))

    finally:
        newfiles.CREATED = real_created
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
