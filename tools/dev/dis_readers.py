# -*- coding: utf-8 -*-
"""Disassemble around the logic reads of menu-button text, in the ORIGINAL exe,
and resolve every rip-relative reference to a string where there is one.

  py -3 dis_readers.py <rva> [<rva> ...]
"""
import struct, sys
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_MEM, X86_REG_RIP

EXE = r"C:/Program Files (x86)/Steam/steamapps/common/CielnosurgeDX/Backup/CielnosurgeDX.exe"
LIVE = r"C:/Program Files (x86)/Steam/steamapps/common/CielnosurgeDX/CielnosurgeDX.exe"
BASE = 0x140000000


class PE:
    def __init__(self, path):
        self.d = open(path, "rb").read()
        pe = struct.unpack_from("<I", self.d, 0x3C)[0]
        n = struct.unpack_from("<H", self.d, pe + 6)[0]
        optsz = struct.unpack_from("<H", self.d, pe + 20)[0]
        opt = pe + 24
        self.secs = []
        for i in range(n):
            o = opt + optsz + 40 * i
            name = self.d[o:o + 8].rstrip(b"\0").decode()
            vs, va, rs, raw = struct.unpack_from("<IIII", self.d, o + 8)
            self.secs.append((name, va, max(vs, rs), raw, rs))
        er, es = struct.unpack_from("<II", self.d, opt + 112 + 24)
        o = self.off(er)
        self.funcs = sorted(struct.unpack_from("<III", self.d, o + 12 * i)
                            for i in range(es // 12))

    def off(self, rva):
        for _n, va, sz, raw, rs in self.secs:
            if va <= rva < va + sz and rva - va < rs:
                return raw + rva - va
        return None

    def func(self, rva):
        for b, e, u in self.funcs:
            if b <= rva < e:
                return b, e
        return None

    def cstr(self, rva, n=80):
        o = self.off(rva)
        if o is None:
            return None
        raw = self.d[o:o + n]
        z = raw.find(b"\0")
        if z <= 0:
            return None
        try:
            s = raw[:z].decode("utf-8")
        except UnicodeDecodeError:
            return None
        return s if all(c.isprintable() for c in s) else None


def main(rvas):
    pe = PE(EXE)
    live = PE(LIVE)
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True
    for site in rvas:
        f = pe.func(site)
        if not f:
            print("0x%x: no function" % site)
            continue
        b, e = f
        print("=" * 78)
        print("call site 0x%x in function [0x%x, 0x%x)" % (site, b, e))
        lo = max(b, site - 0x60)
        hi = min(e, site + 0xA0)
        code = pe.d[pe.off(b):pe.off(b) + (e - b)]
        for ins in md.disasm(code, BASE + b):
            rva = ins.address - BASE
            if rva < lo or rva > hi:
                continue
            note = ""
            for op in ins.operands:
                if op.type == X86_OP_MEM and op.mem.base == X86_REG_RIP:
                    tgt = ins.address + ins.size + op.mem.disp - BASE
                    s = pe.cstr(tgt)
                    s2 = live.cstr(tgt)
                    if s:
                        note = "   ; 0x%x %r" % (tgt, s)
                        if s2 != s:
                            note += "  -> live exe: %r" % (s2,)
                    else:
                        note = "   ; 0x%x" % tgt
            mark = "  <== return from the getter" if rva == site else ""
            if ins.mnemonic == "call" and ins.op_str.startswith("0x"):
                t = int(ins.op_str, 16) - BASE
                o = pe.off(t)
                if o is not None and pe.d[o] == 0xE9:
                    t2 = t + 5 + struct.unpack_from("<i", pe.d, o + 1)[0]
                    note += "   ; thunk -> 0x%x" % t2
            print("  %08x  %-8s %-48s%s%s" % (rva, ins.mnemonic, ins.op_str, note, mark))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main([int(a, 16) for a in sys.argv[1:]])
