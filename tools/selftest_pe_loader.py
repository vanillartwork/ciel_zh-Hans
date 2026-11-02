# -*- coding: utf-8 -*-
"""Checks on the loader-entry patcher.

  py -3 selftest_pe_loader.py

Uses a generated PE and the emitter built by native/build.ps1. Pass --exe PATH
to run the same checks on a local unpatched input. Both modes write only into
a temporary directory and never launch the executable.

The cases that matter here are the ones no amount of reading the source settles:
that applying it twice stays one patch, that a file somebody else has edited is
refused BEFORE anything is overwritten, that a failure part-way leaves no
wreckage, and that the input cannot be destroyed by a path coincidence.

Every refusal must be a Refuse.  Accepting any exception as "it refused" hides
the difference between a decision and a crash -- which is how an earlier version
of this file passed while the check it named was not running at all.
"""
import sys, os, io, struct, shutil, hashlib, tempfile, argparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from synthetic_pe import make_image
import pe_loader                    # noqa: E402
from pe_loader import Pe, Refuse    # noqa: E402

FAKE_EMITTER = r"""
import sys, os, json, hashlib
# An emitter that lies about its own output, to exercise the JSON contract.
mode = os.environ.get("CIELZH_FAKE_MODE", "length")
args = sys.argv[1:]
def val(name):
    return int(args[args.index(name) + 1])
out_bin = args[args.index("--out-bin") + 1]
out_json = args[args.index("--out-json") + 1]
block = bytes(range(256)) * 2
open(out_bin, "wb").write(block)
n = len(block)
h = hashlib.sha256(block).hexdigest()
if mode == "length":
    n += 1
elif mode == "hash":
    h = "0" * 64
meta = {
    "format": 9 if mode == "format" else 1,
    "layout": {
        "code_rva": val("--code-rva") + (0x1000 if mode == "layout" else 0),
        "data_rva": val("--data-rva"),
        "orig_target_rva": val("--target"),
        "iat_get_module_file_name_w": val("--iat-gmfn"),
        "iat_load_library_ex_w": val("--iat-lle"),
        "iat_get_proc_address": val("--iat-gpa"),
        "iat_create_file_w": val("--iat-cf"),
        "iat_write_file": val("--iat-wf"),
        "iat_close_handle": val("--iat-ch"),
        "iat_get_last_error": val("--iat-gle"),
    },
    "bin": {"bytes": n, "sha256": h},
    "data_block_size": 0x700,
    "abi_major": 1,
    "result": {"code_bytes": len(block), "entry_offset": 16, "entry_size": 16,
               "log_offset": 0, "log_size": 16, "unwind_entry_offset": 480,
               "unwind_log_offset": 488, "entry_body": 20,
               "entry_epilogue": 24, "entry_tail": 28, "log_body": 4,
               "log_epilogue": 8, "log_tail": 12},
}
if mode == "no_layout":
    del meta["layout"]
elif mode == "unwind":
    meta["result"]["unwind_entry_offset"] = len(block)
elif mode == "range":
    meta["result"]["entry_size"] = len(block)
open(out_json, "w", encoding="utf-8").write(json.dumps(meta))
"""


def sha(b):
    return hashlib.sha256(b).hexdigest()


def sha_file(p):
    return sha(open(p, "rb").read())


def quiet(*_a, **_k):
    pass


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", help="optional local PE to test instead of the fixture")
    parser.add_argument("--emit", default=pe_loader.default_emit_tool())
    args = parser.parse_args(argv)
    failures = []

    def check(name, cond):
        print("  %-60s %s" % (name, "ok" if cond else "失败"))
        if not cond:
            failures.append(name)

    def refuses(fn):
        """True only for a Refuse.  Any other exception is a failure, loudly."""
        try:
            fn()
        except Refuse:
            return True
        except Exception as e:          # noqa: BLE001
            print("      不是 Refuse，而是 %s: %s" % (type(e).__name__, e))
            return False
        return False

    tool = args.emit
    if not os.path.exists(tool):
        print("发射工具未构建：%s\n  先运行 native/build.ps1" % tool)
        return 1

    if args.exe:
        with open(args.exe, "rb") as f:
            src = f.read()
    else:
        src = make_image()
    tmp = tempfile.mkdtemp(prefix="cielzh-pe-")
    try:
        inp = os.path.join(tmp, "in.exe")
        with open(inp, "wb") as f:
            f.write(src)
        inp_hash = sha_file(inp)
        out1 = os.path.join(tmp, "out1.exe")

        first = pe_loader.apply(inp, out1, tool, report=quiet)
        b1 = open(out1, "rb").read()
        check("输入映像可以打上加载入口", os.path.exists(out1))
        check("输入文件未被改动", sha_file(inp) == inp_hash)

        pe1 = Pe(b1)
        code = pe1.section_by_name(pe_loader.SEC_CODE)
        data = pe1.section_by_name(pe_loader.SEC_DATA)
        check("两个新节都在", code is not None and data is not None)
        check("代码节可执行且不可写",
              code["ch"] == pe_loader.CH_CODE
              and not (code["ch"] & 0x80000000))
        check("数据节可写且无文件内容",
              data["ch"] == pe_loader.CH_DATA and data["rsz"] == 0)
        pe0 = Pe(src)
        ex, size = pe0.dir_entry(3)
        pos = pe0.rva_to_off(ex, size)
        check("保留原展开表，只追加两条记录", pe1.dir_entry(3) == (ex, size + 24)
              and b1[pos:pos + size] == src[pos:pos + size])
        call = pe1.rva_to_off(pe_loader.CALL_SITE_RVA, 5)
        dest = pe_loader.CALL_SITE_RVA + 5 + struct.unpack_from("<i", b1, call+1)[0]
        check("实际调用落在入口指令而非块首", b1[call] == 0xe8
              and dest == first["entry_rva"] and dest > first["code_rva"])
        if not args.exe:
            font_in = os.path.join(tmp, "font-in.exe")
            font_out = os.path.join(tmp, "font-out.exe")
            with open(font_in, "wb") as f:
                f.write(make_image(with_fontex=True))
            other = pe_loader.apply(font_in, font_out, tool, report=quiet)
            check("有 .fontex 的输入使用不同的入口布局",
                  other["code_rva"] == first["code_rva"] + pe0.sec_align
                  and sha_file(font_in) == sha(make_image(with_fontex=True)))

        # --- path conflicts ------------------------------------------------
        check("输入与输出是同一文件：拒绝",
              refuses(lambda: pe_loader.apply(inp, inp, tool, report=quiet)))
        check("  ……输入未被改动", sha_file(inp) == inp_hash)

        alias = os.path.join(tmp, "alias") + os.sep + ".." + os.sep + "in.exe"
        check("输出是输入的别名路径：拒绝",
              refuses(lambda: pe_loader.apply(inp, alias, tool, report=quiet)))
        check("  ……输入未被改动", sha_file(inp) == inp_hash)

        # The case that used to destroy the input: a name the old fixed suffix
        # would have collided with.
        trap_in = os.path.join(tmp, "a.exe.cielzh-tmp")
        shutil.copyfile(inp, trap_in)
        trap_hash = sha_file(trap_in)
        trap_out = os.path.join(tmp, "a.exe")
        # Two separate questions, because the defences are layered: a fixed
        # temporary name is caught by the collision check, so the input survives
        # either way -- but only the correct code also finishes the job.  Rolled
        # into one assertion, a regression showed up as an uncaught Refuse
        # instead of a failed check.
        trap_refused = False
        try:
            pe_loader.apply(trap_in, trap_out, tool, report=quiet)
        except Refuse:
            trap_refused = True
        check("输入名为 a.exe.cielzh-tmp、输出为 a.exe：输入仍在且未变",
              os.path.exists(trap_in) and sha_file(trap_in) == trap_hash)
        check("  ……并且正常完成（不是靠拒绝才保住输入）",
              not trap_refused and os.path.exists(trap_out))
        check("  ……没有留下临时文件",
              not [f for f in os.listdir(tmp) if f.startswith(".cielzh-")])

        # An unrelated file sitting where a fixed temporary name would land.
        # The collision check does not cover this one: only creating the
        # temporary exclusively under a name nobody can predict does.
        decoy = os.path.join(tmp, "decoy.exe.cielzh-tmp")
        open(decoy, "wb").write(b"somebody else's file")
        decoy_hash = sha_file(decoy)
        try:
            pe_loader.apply(inp, os.path.join(tmp, "decoy.exe"), tool,
                            report=quiet)
        except Refuse:
            pass
        check("输出目录里同名的无关文件不被覆盖",
              os.path.exists(decoy) and sha_file(decoy) == decoy_hash)

        # --- applying it again ----------------------------------------------
        out2 = os.path.join(tmp, "out2.exe")
        second = pe_loader.apply(out1, out2, tool, report=quiet)
        b2 = open(out2, "rb").read()
        pe2 = Pe(b2)
        check("重复应用：节数不增加", pe2.nsec == pe1.nsec)
        check("重复应用：文件大小不变", len(b2) == len(b1))
        check("重复应用：异常目录大小不增加",
              pe1.dir_entry(3) == pe2.dir_entry(3))
        check("重复应用：入口地址不变",
              second["entry_rva"] == first["entry_rva"])
        check("重复应用：结果与首次逐字节相同", b2 == b1)
        out3 = os.path.join(tmp, "out3.exe")
        pe_loader.apply(out2, out3, tool, report=quiet)
        check("第三次应用仍然稳定", open(out3, "rb").read() == b1)

        # --- a patched file somebody else has edited -------------------------
        # Each of these was accepted before the ownership check moved ahead of
        # the rewrite.
        def tampered(mutate, name):
            bad = bytearray(b1)
            mutate(bad)
            p = os.path.join(tmp, "t_%s.exe" % name)
            open(p, "wb").write(bytes(bad))
            before = sha_file(p)
            o = os.path.join(tmp, "t_%s_out.exe" % name)
            ok = refuses(lambda: pe_loader.apply(p, o, tool, report=quiet))
            return ok and sha_file(p) == before and not os.path.exists(o)

        p1 = Pe(b1)
        hdr_off = p1.rva_to_off(code["va"], pe_loader.HDR_SIZE)
        hdr = pe_loader.unpack_header(bytes(b1[hdr_off:hdr_off + 0x40]))
        site_off = p1.rva_to_off(pe_loader.CALL_SITE_RVA, 5)
        entry_off = p1.rva_to_off(hdr["entry_rva"], 1)
        ex_rva, ex_size = p1.dir_entry(3)
        ex_off = p1.rva_to_off(ex_rva, ex_size)
        last = ex_off + ex_size - 12

        check("已打补丁但调用点被改成 NOP：拒绝，输入不变",
              tampered(lambda d: d.__setitem__(slice(site_off, site_off + 5),
                                               b"\x90" * 5), "nop"))
        check("已打补丁但 Entry 首字节被改：拒绝，输入不变",
              tampered(lambda d: d.__setitem__(entry_off,
                                               d[entry_off] ^ 0xFF), "code"))
        check("展开条目 BeginAddress 被改（unwind 不变）：拒绝，输入不变",
              tampered(lambda d: struct.pack_into("<I", d, last, 0x1000),
                       "begin"))
        check("所有权头的 data_rva 被改：拒绝，输入不变",
              tampered(lambda d: struct.pack_into(
                  "<I", d, hdr_off + 12 + 4, hdr["data_rva"] + 0x1000),
                  "datarva"))
        check("所有权头 magic 被改：拒绝，输入不变",
              tampered(lambda d: d.__setitem__(slice(hdr_off, hdr_off + 8),
                                               b"NOTOURS!"), "magic"))
        check("我们的展开条目后面被插了东西：拒绝，输入不变",
              tampered(lambda d: struct.pack_into(
                  "<II", d, p1.dirs + 3 * 8, ex_rva, ex_size + 12), "after"))

        # --- an unsupported build -------------------------------------------
        def unsupported(mutate, name):
            bad = bytearray(src)
            mutate(bad)
            p = os.path.join(tmp, "u_%s.exe" % name)
            open(p, "wb").write(bytes(bad))
            before = sha_file(p)
            o = os.path.join(tmp, "u_%s_out.exe" % name)
            ok = refuses(lambda: pe_loader.apply(p, o, tool, report=quiet))
            return ok and sha_file(p) == before and not os.path.exists(o)

        p0 = Pe(src)
        site0 = p0.rva_to_off(pe_loader.CALL_SITE_RVA, 5)
        raw_end = max(s["raw"] + s["rsz"] for s in p0.sections() if s["rsz"])
        check("截断的节数据：拒绝，不留下输出",
              unsupported(lambda d: d.__delitem__(slice(raw_end - 1, None)), "truncated"))
        imp_rva, _ = p0.dir_entry(1)
        check("导入目录缺少结束项：拒绝",
              unsupported(lambda d: struct.pack_into("<II", d, p0.dirs + 8,
                                                     imp_rva, 20), "importend"))
        if not args.exe:
            psec = p0.section_by_name(b".pdata")
            bad = bytearray(src)
            # The first record fits on disk. The proposed two additions fit
            # only in virtual space; do not write them past the raw section.
            struct.pack_into("<I", bad, psec["off"] + 16, 12)
            check("展开表只有虚拟余量：发射前拒绝",
                  refuses(lambda: pe_loader.structural(Pe(bad))))
        # Find the name table entry for one slot and rename the import.
        gmfn_rva = pe_loader.IAT["gmfn"][0]
        check("调用点字节不符：拒绝，输入不变",
              unsupported(lambda d: d.__setitem__(slice(site0, site0 + 5),
                                                  b"\x90" * 5), "call"))

        def rename_import(d):
            # Walk to the hint/name entry for the gmfn slot and change a letter.
            pe = Pe(bytes(d))
            imp_rva, _ = pe.dir_entry(1)
            o = pe.rva_to_off(imp_rva, 20)
            while True:
                ilt, _t, _f, nm, iat = struct.unpack_from("<IIIII", pe.d, o)
                if nm == 0:
                    break
                table = pe.rva_to_off(ilt or iat, 8)
                k = 0
                while True:
                    v = struct.unpack_from("<Q", pe.d, table + k * 8)[0]
                    if v == 0:
                        break
                    if not (v >> 63) and iat + k * 8 == gmfn_rva:
                        h = pe.rva_to_off(v & 0x7FFFFFFF, 3) + 2
                        d[h] = ord("X")
                        return
                    k += 1
                o += 20
            raise AssertionError("did not find the slot to rename")

        check("IAT 槽导入的函数名不符：拒绝，输入不变",
              unsupported(rename_import, "iatname"))

        def rename_dll(d):
            pe = Pe(bytes(d))
            imp_rva, _ = pe.dir_entry(1)
            o = pe.rva_to_off(imp_rva, 20)
            while True:
                ilt, _t, _f, nm, iat = struct.unpack_from("<IIIII", pe.d, o)
                if nm == 0:
                    break
                q = pe.rva_to_off(nm, 1)
                e = q
                while pe.d[e]:
                    e += 1
                if bytes(pe.d[q:e]).lower() == b"kernel32.dll":
                    d[q] = ord("Z")     # same length, different DLL
                    return
                o += 20
            raise AssertionError("did not find KERNEL32.dll")

        check("IAT 槽所属 DLL 名不符：拒绝，输入不变",
              unsupported(rename_dll, "iatdll"))

        # --- the JSON contract, through production code ----------------------
        fake = os.path.join(tmp, "fake_emit.py")
        io.open(fake, "w", encoding="utf-8").write(FAKE_EMITTER)
        layout = pe_loader.plan_new(Pe(src))
        for mode, label in (("length", "长度"), ("hash", "哈希"),
                            ("layout", "回显的布局"), ("format", "格式版本"),
                            ("no_layout", "缺失布局"), ("unwind", "展开偏移"),
                            ("range", "函数范围")):
            os.environ["CIELZH_FAKE_MODE"] = mode
            check("发射器谎报%s：emit_block 拒绝" % label,
                  refuses(lambda: pe_loader.emit_block(
                      [sys.executable, fake], layout)))
        os.environ.pop("CIELZH_FAKE_MODE", None)

        # --- write failures --------------------------------------------------
        keep = os.path.join(tmp, "existing_out.exe")
        open(keep, "wb").write(b"a previous build's output")
        marker = sha_file(keep)
        real_replace = os.replace
        real_fsync = os.fsync

        def boom_replace(a, b):
            raise OSError(5, "injected replace failure")

        def boom_fsync(fd):
            raise OSError(5, "injected fsync failure")

        for name, patch, attr in (("替换", boom_replace, "replace"),
                                  ("落盘", boom_fsync, "fsync")):
            setattr(os, attr, patch)
            try:
                ok = refuses(lambda: pe_loader.apply(inp, keep, tool,
                                                     report=quiet))
            finally:
                setattr(os, attr, real_replace if attr == "replace"
                        else real_fsync)
            leftovers = [f for f in os.listdir(tmp) if f.startswith(".cielzh-")]
            check("%s失败：报 Refuse" % name, ok)
            check("  ……既有输出未被覆盖", sha_file(keep) == marker)
            check("  ……输入未被改动", sha_file(inp) == inp_hash)
            check("  ……没有留下临时文件", not leftovers)

        # --- the emitted block is layout-specific ---------------------------
        blk_a, _ = pe_loader.emit_block(tool, layout)
        shifted = dict(layout)
        shifted["code_rva"] = layout["code_rva"] + 0x1000
        blk_b, _ = pe_loader.emit_block(tool, shifted)
        check("布局不同则机器码不同（不能复用别的布局产物）", blk_a != blk_b)
        check("同一布局重复发射得到相同字节",
              pe_loader.emit_block(tool, layout)[0] == blk_a)

    finally:
        shutil.rmtree(tmp, ignore_errors=True)

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
