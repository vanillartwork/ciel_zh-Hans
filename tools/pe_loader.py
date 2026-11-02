# -*- coding: utf-8 -*-
"""Add the Chinese display layer's loader entry to CielnosurgeDX.exe.

  py -3 pe_loader.py <in.exe> <out.exe> [--emit <emit_entry.exe>]
  py -3 pe_loader.py --inspect <exe>

It appends two sections, one executable and one writable, puts the entry block
in the first, adds two unwind records to the existing exception table, and
repoints the call at 0x7B7F05 at the entry.  The entry loads cielzh.dll if it is
there and then tail-jumps to the call's original target, so an executable
patched this way behaves like the original when the DLL is absent.

Three promises, each of which had to be made properly rather than assumed:

  * The input is never written.  Same-file and alias cases are refused up front,
    the working copy is an exclusively created temporary in the output's own
    directory, and it is removed on every failure path.
  * A block emitted for a different layout is never reused.  The section
    addresses are worked out first and handed to the emitter, because a
    rip-relative displacement computed against another base is wrong by an
    amount that looks entirely plausible.
  * Re-applying verifies the OLD contents before touching anything.  Checking
    the new file afterwards proves the new file is right; it says nothing about
    whether what was overwritten belonged to this tool.
"""
import sys, os, io, json, struct, hashlib, subprocess, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))

# --- what this build is ------------------------------------------------------
CALL_SITE_RVA = 0x007B7F05
CALL_ORIG_BYTES = bytes([0xE8, 0x33, 0x8C, 0xC5, 0xFF])
CALL_TARGET_RVA = 0x00410B3D

# The slots the entry calls through: RVA, the DLL it must come from, and the
# name.  The DLL matters too -- a descriptor renamed to something else entirely
# left the names looking fine.
IAT = {
    "gmfn": (0x013E3528, "KERNEL32.dll", "GetModuleFileNameW"),
    "lle":  (0x013E34D0, "KERNEL32.dll", "LoadLibraryExW"),
    "gpa":  (0x013E3268, "KERNEL32.dll", "GetProcAddress"),
    "cf":   (0x013E31A0, "KERNEL32.dll", "CreateFileW"),
    "wf":   (0x013E32F0, "KERNEL32.dll", "WriteFile"),
    "ch":   (0x013E3128, "KERNEL32.dll", "CloseHandle"),
    "gle":  (0x013E3208, "KERNEL32.dll", "GetLastError"),
}

SEC_CODE = b".cielzh"
SEC_DATA = b".cielzhd"
CH_CODE = 0x60000020       # CODE | EXECUTE | READ
CH_DATA = 0xC0000040       # INITIALIZED_DATA | READ | WRITE

HDR_MAGIC = b"CIELZHLD"
HDR_VERSION = 1
HDR_FIELDS = ("code_rva", "data_rva", "code_bytes", "entry_rva", "entry_size",
              "log_rva", "log_size", "unwind_entry_rva", "unwind_log_rva",
              "pdata_index")
HDR_FMT = "<8sI" + "I" * len(HDR_FIELDS)
HDR_SIZE = 0x40


class Refuse(Exception):
    """Something did not match.  The input and any existing output are intact."""


def u16(d, o):
    return struct.unpack_from("<H", d, o)[0]


def u32(d, o):
    return struct.unpack_from("<I", d, o)[0]


def align_up(v, a):
    return (v + a - 1) // a * a


def same_path(a, b):
    """True if these name the same file, following links and case rules."""
    try:
        if os.path.exists(a) and os.path.exists(b):
            return os.path.samefile(a, b)
    except OSError:
        pass
    return (os.path.normcase(os.path.realpath(os.path.abspath(a)))
            == os.path.normcase(os.path.realpath(os.path.abspath(b))))


class Pe:
    """Just enough PE to add sections and find things by RVA."""

    def __init__(self, data):
        self.d = bytearray(data)
        if len(self.d) < 0x40 or self.d[:2] != b"MZ":
            raise Refuse("not a PE image")
        self.lfanew = u32(self.d, 0x3C)
        if (self.lfanew + 24 > len(self.d)
                or self.d[self.lfanew:self.lfanew + 4] != b"PE\0\0"):
            raise Refuse("no PE signature")
        self.nt = self.lfanew
        self.machine = u16(self.d, self.nt + 4)
        self.nsec = u16(self.d, self.nt + 6)
        self.opt_size = u16(self.d, self.nt + 20)
        self.opt = self.nt + 24
        if (self.opt_size < 112 or not self.nsec
                or self.opt + self.opt_size + self.nsec * 40 > len(self.d)):
            raise Refuse("incomplete optional header or section table")
        if u16(self.d, self.opt) != 0x20B:
            raise Refuse("not PE32+")
        if self.machine != 0x8664:
            raise Refuse("machine %#x, expected x64" % self.machine)
        self.sec_align = u32(self.d, self.opt + 32)
        self.file_align = u32(self.d, self.opt + 36)
        self.size_of_image = u32(self.d, self.opt + 56)
        self.ndirs = u32(self.d, self.opt + 108)
        self.dirs = self.opt + 112
        self.sec_table = self.opt + self.opt_size
        if not self.sec_align or not self.file_align:
            raise Refuse("invalid zero section or file alignment")
        if self.ndirs > (self.opt_size - 112) // 8:
            raise Refuse("data directories run past the optional header")
        for s in self.sections():
            if s["rsz"] and (s["raw"] < self.sec_table + self.nsec * 40
                             or s["raw"] + s["rsz"] > len(self.d)):
                raise Refuse("section raw data falls outside the file or overlaps its headers")

    def sections(self):
        out = []
        for i in range(self.nsec):
            o = self.sec_table + i * 40
            name = bytes(self.d[o:o + 8]).rstrip(b"\0")
            vsz, va, rsz, raw = struct.unpack_from("<IIII", self.d, o + 8)
            out.append(dict(i=i, off=o, name=name, vsz=vsz, va=va, rsz=rsz,
                            raw=raw, ch=u32(self.d, o + 36)))
        return out

    def section_by_name(self, name):
        for s in self.sections():
            if s["name"] == name:
                return s
        return None

    def rva_to_off(self, rva, need=1):
        for s in self.sections():
            if s["rsz"] and s["va"] <= rva < s["va"] + max(s["vsz"], s["rsz"]):
                off = s["raw"] + (rva - s["va"])
                if off + need <= s["raw"] + s["rsz"]:
                    return off
        raise Refuse("RVA %#x is not in any section's raw data" % rva)

    def dir_entry(self, i):
        if i >= self.ndirs:
            raise Refuse("no data directory %d" % i)
        return struct.unpack_from("<II", self.d, self.dirs + i * 8)

    def import_name(self, rva):
        start = self.rva_to_off(rva)
        section = next(s for s in self.sections()
                       if s["va"] <= rva < s["va"] + s["rsz"])
        end = self.d.find(b"\0", start, section["raw"] + section["rsz"])
        if end < 0:
            raise Refuse("unterminated import name at %#x" % rva)
        return bytes(self.d[start:end]).decode("ascii", "replace")

    def set_dir_entry(self, i, rva, size):
        struct.pack_into("<II", self.d, self.dirs + i * 8, rva, size)


# --- the import table ---------------------------------------------------------
def iat_slots(pe):
    """RVA of each IAT slot -> (dll name, imported name)."""
    imp_rva, size = pe.dir_entry(1)
    start = pe.rva_to_off(imp_rva, size)
    out = {}
    for o in range(start, start + size - 19, 20):
        ilt, _ts, _fc, nm, iat = struct.unpack_from("<IIIII", pe.d, o)
        if not any((ilt, _ts, _fc, nm, iat)):
            return out
        dll = pe.import_name(nm)
        k = 0
        while True:
            slot = iat + k * 8
            pe.rva_to_off(slot, 8)
            off = pe.rva_to_off((ilt or iat) + k * 8, 8)
            v = struct.unpack_from("<Q", pe.d, off)[0]
            if v == 0:
                break
            if not v >> 63:
                pe.rva_to_off(v, 3)  # hint plus the first byte of the name
                out[slot] = (dll, pe.import_name(v + 2))
            k += 1
    raise Refuse("unterminated import descriptor table")


def check_iat(pe):
    got = iat_slots(pe)
    for key in sorted(IAT):
        rva, dll, name = IAT[key]
        have = got.get(rva)
        if have is None:
            raise Refuse("IAT slot %#x is not an imported function" % rva)
        if have[1] != name:
            raise Refuse("IAT slot %#x imports %r, expected %r"
                         % (rva, have[1], name))
        if have[0].lower() != dll.lower():
            raise Refuse("IAT slot %#x comes from %r, expected %r"
                         % (rva, have[0], dll))


# --- the emitter --------------------------------------------------------------
def default_emit_tool():
    return os.path.normpath(os.path.join(HERE, "..", "native", "build",
                                         "emit_entry.exe"))


JSON_LAYOUT_NAMES = {
    "code_rva": "code_rva",
    "data_rva": "data_rva",
    "orig_target_rva": "orig_target_rva",
    "iat_gmfn": "iat_get_module_file_name_w",
    "iat_lle": "iat_load_library_ex_w",
    "iat_gpa": "iat_get_proc_address",
    "iat_cf": "iat_create_file_w",
    "iat_wf": "iat_write_file",
    "iat_ch": "iat_close_handle",
    "iat_gle": "iat_get_last_error",
}


def emit_block(tool, layout):
    """Runs the emitter for this exact layout and checks what came back.

    `tool` may be a command line rather than a path, which is how the tests
    substitute an emitter that lies about its own output.
    """
    argv = list(tool) if isinstance(tool, (list, tuple)) else [tool]
    if len(argv) == 1 and not os.path.exists(argv[0]):
        raise Refuse("the emitter is not built: %s\n"
                     "  run native/build.ps1 first" % argv[0])
    with tempfile.TemporaryDirectory(prefix="cielzh-emit-") as tmp:
        bin_path = os.path.join(tmp, "entry.bin")
        json_path = os.path.join(tmp, "entry.json")
        args = argv + ["--code-rva", str(layout["code_rva"]),
                       "--data-rva", str(layout["data_rva"]),
                       "--target", str(layout["orig_target_rva"])]
        for k in ("gmfn", "lle", "gpa", "cf", "wf", "ch", "gle"):
            args += ["--iat-" + k, str(layout["iat_" + k])]
        args += ["--out-bin", bin_path, "--out-json", json_path]
        r = subprocess.run(args, capture_output=True, text=True)
        if r.returncode != 0:
            raise Refuse("the emitter failed: %s"
                         % (r.stderr or r.stdout).strip())
        if not os.path.exists(bin_path) or not os.path.exists(json_path):
            raise Refuse("the emitter did not produce both outputs")
        block = open(bin_path, "rb").read()
        try:
            meta = json.load(io.open(json_path, encoding="utf-8"))
        except ValueError as e:
            raise Refuse("the emitter's JSON is not readable: %s" % e)

    if not isinstance(meta, dict):
        raise Refuse("the emitter's JSON is not an object")
    if meta.get("format") != 1:
        raise Refuse("emitter JSON format %r is not 1" % meta.get("format"))
    for key in ("bin", "result", "layout"):
        if not isinstance(meta.get(key), dict):
            raise Refuse("the emitter's JSON has no %r object" % key)
    if type(meta.get("data_block_size")) is not int or not 0 < meta["data_block_size"] <= 0xffffffff:
        raise Refuse("invalid emitter data block size")
    if meta["bin"].get("bytes") != len(block):
        raise Refuse("JSON says %r bytes, the bin has %d"
                     % (meta["bin"].get("bytes"), len(block)))
    got = hashlib.sha256(block).hexdigest()
    if meta["bin"].get("sha256") != got:
        raise Refuse("JSON hash %r does not match the bin's %s"
                     % (meta["bin"].get("sha256"), got))
    if meta["result"].get("code_bytes") != len(block):
        raise Refuse("the result says %r code bytes, the bin has %d"
                     % (meta["result"].get("code_bytes"), len(block)))
    for k, v in layout.items():
        name = JSON_LAYOUT_NAMES[k]
        if meta["layout"].get(name) != v:
            raise Refuse("the emitter was given %s=%d but reports %r"
                         % (name, v, meta["layout"].get(name)))
    r = meta["result"]
    for fn in ("entry", "log"):
        start, size = r.get(fn + "_offset"), r.get(fn + "_size")
        unwind = r.get("unwind_" + fn + "_offset")
        if (type(start) is not int or type(size) is not int
                or not (0 <= start < start + size <= len(block))):
            raise Refuse("%s function is missing or outside the emitted block" % fn)
        # The emitter writes an 8-byte UNWIND_INFO for each function.
        if type(unwind) is not int or unwind % 4 or not 0 <= unwind <= len(block) - 8:
            raise Refuse("%s unwind info is missing or outside the emitted block" % fn)
    return block, meta


# --- the ownership header -----------------------------------------------------
def pack_header(f):
    body = struct.pack(HDR_FMT, HDR_MAGIC, HDR_VERSION,
                       *[f[k] for k in HDR_FIELDS])
    if len(body) > HDR_SIZE:
        raise Refuse("the ownership header outgrew its space")
    return body + b"\0" * (HDR_SIZE - len(body))


def unpack_header(raw):
    if len(raw) < struct.calcsize(HDR_FMT):
        raise Refuse("our section is too small to hold its header")
    v = struct.unpack_from(HDR_FMT, raw, 0)
    if v[0] != HDR_MAGIC:
        raise Refuse("a section named %s is there but carries no header of "
                     "ours; refusing to touch it" % SEC_CODE.decode())
    if v[1] != HDR_VERSION:
        raise Refuse("our section says layout version %d, this tool writes %d"
                     % (v[1], HDR_VERSION))
    return dict(zip(HDR_FIELDS, v[2:]))


def layout_for(code_rva, data_rva):
    out = dict(code_rva=code_rva, data_rva=data_rva,
               orig_target_rva=CALL_TARGET_RVA)
    for k, (rva, _dll, _name) in IAT.items():
        out["iat_" + k] = rva
    return out


# --- checks that run before anything is built ---------------------------------
def structural(pe):
    """Room and shape, independent of whether a patch is already there."""
    check_iat(pe)
    sections = pe.sections()
    existing = pe.section_by_name(SEC_CODE)
    names = [s["name"] for s in sections]
    if (names.count(SEC_CODE) != names.count(SEC_DATA)
            or names.count(SEC_CODE) > 1):
        raise Refuse("missing or duplicate loader sections")

    end = pe.sec_table + pe.nsec * 40
    first_raw = min(s["raw"] for s in pe.sections() if s["raw"])
    need = 0 if existing else 80
    if first_raw - end < need:
        raise Refuse("only %d bytes between the section table and the first "
                     "section's data; two headers need 80" % (first_raw - end))
    if need and any(pe.d[end:end + need]):
        raise Refuse("the space after the section table is not blank")

    ex_rva, ex_size = pe.dir_entry(3)
    if ex_rva == 0 or ex_size == 0 or ex_size % 12:
        raise Refuse("no usable exception directory (RVA %#x size %#x)"
                     % (ex_rva, ex_size))
    host = None
    for s in pe.sections():
        if s["va"] <= ex_rva < s["va"] + max(s["vsz"], s["rsz"]):
            host = s
            break
    if host is None or ex_rva != host["va"]:
        raise Refuse("the exception directory does not start its own section")
    slack_off = host["raw"] + ex_size
    # The table must fit both the mapped section and its bytes on disk.
    capacity = min(host["vsz"] or host["rsz"], host["rsz"])
    if ex_size > capacity:
        raise Refuse("exception directory extends beyond its section")
    slack = capacity - ex_size
    if not existing:
        if slack < 24:
            raise Refuse("only %d bytes spare after the exception table; two "
                         "entries need 24" % slack)
        if any(pe.d[slack_off:slack_off + 24]):
            raise Refuse("the space after the exception table is not blank")
    return dict(existing=existing, pdata=host, ex_rva=ex_rva, ex_size=ex_size,
                slack_off=slack_off)


def verify_existing(pe, pre, tool):
    """Everything about the patch already in the file, before it is replaced.

    The point is that the bytes being overwritten are provably this tool's, at
    this version.  An earlier cut rewrote first and verified the result, which
    accepted a file whose call site had been NOPped, whose entry code had been
    edited, or whose unwind entries had been moved -- the new file verified
    fine, because it had just been written.
    """
    code = pre["existing"]
    data = pe.section_by_name(SEC_DATA)
    if data is None:
        raise Refuse("%s is there but %s is not"
                     % (SEC_CODE.decode(), SEC_DATA.decode()))
    hdr_off = pe.rva_to_off(code["va"], HDR_SIZE)
    hdr = unpack_header(bytes(pe.d[hdr_off:hdr_off + HDR_SIZE]))

    # The header must describe the sections that are actually there.
    if hdr["code_rva"] != code["va"] + HDR_SIZE:
        raise Refuse("the header puts the block at %#x, %s starts at %#x"
                     % (hdr["code_rva"], SEC_CODE.decode(), code["va"]))
    if hdr["data_rva"] != data["va"]:
        raise Refuse("the header records data at %#x, %s is at %#x"
                     % (hdr["data_rva"], SEC_DATA.decode(), data["va"]))
    if HDR_SIZE + hdr["code_bytes"] > max(code["vsz"], code["rsz"]):
        raise Refuse("the header claims %d code bytes, more than %s holds"
                     % (hdr["code_bytes"], SEC_CODE.decode()))

    # Re-emit for the layout the header records and compare.  This is the check
    # that covers "somebody edited the code": one changed byte and it fails.
    layout = layout_for(hdr["code_rva"], hdr["data_rva"])
    block, meta = emit_block(tool, layout)
    r = meta["result"]
    if len(block) != hdr["code_bytes"]:
        raise Refuse("this version emits %d bytes, the file records %d -- the "
                     "existing patch is from another build" %
                     (len(block), hdr["code_bytes"]))
    off = pe.rva_to_off(hdr["code_rva"], len(block))
    if bytes(pe.d[off:off + len(block)]) != block:
        raise Refuse("the code in %s is not what this version emits for that "
                     "layout; it has been modified or comes from another build"
                     % SEC_CODE.decode())

    # The header's own numbers must agree with what the emitter reports.
    for field, want in (("entry_rva", hdr["code_rva"] + r["entry_offset"]),
                        ("entry_size", r["entry_size"]),
                        ("log_rva", hdr["code_rva"] + r["log_offset"]),
                        ("log_size", r["log_size"]),
                        ("unwind_entry_rva",
                         hdr["code_rva"] + r["unwind_entry_offset"]),
                        ("unwind_log_rva",
                         hdr["code_rva"] + r["unwind_log_offset"])):
        if hdr[field] != want:
            raise Refuse("the header's %s is %#x, this version puts it at %#x"
                         % (field, hdr[field], want))

    # The call must be a direct call landing exactly on that entry.
    site = pe.rva_to_off(CALL_SITE_RVA, 5)
    if pe.d[site] != 0xE8:
        raise Refuse("the call at %#x is not a direct call any more (%#02x)"
                     % (CALL_SITE_RVA, pe.d[site]))
    rel = struct.unpack_from("<i", pe.d, site + 1)[0]
    target = CALL_SITE_RVA + 5 + rel
    if target != hdr["entry_rva"]:
        raise Refuse("the call goes to %#x, our entry is at %#x"
                     % (target, hdr["entry_rva"]))

    # Both unwind records, all three fields, exactly where the header says.
    idx = hdr["pdata_index"]
    ex_size = pre["ex_size"]
    if idx + 2 != ex_size // 12:
        raise Refuse("our exception entries should be the last two (%d..%d of "
                     "%d); something was added after them"
                     % (idx, idx + 1, ex_size // 12))
    base = pre["pdata"]["raw"] + idx * 12
    want = sorted([
        (hdr["log_rva"], hdr["log_rva"] + hdr["log_size"],
         hdr["unwind_log_rva"]),
        (hdr["entry_rva"], hdr["entry_rva"] + hdr["entry_size"],
         hdr["unwind_entry_rva"]),
    ])
    have = [struct.unpack_from("<III", pe.d, base + i * 12) for i in (0, 1)]
    if have != want:
        raise Refuse("the exception entries at %d..%d are %s, the header "
                     "describes %s" % (idx, idx + 1, have, want))
    return dict(layout=layout, hdr=hdr, block=block, meta=meta)


def plan_new(pe):
    top = max(s["va"] + max(s["vsz"], s["rsz"]) for s in pe.sections())
    code_sec_rva = align_up(top, pe.sec_align)
    data_sec_rva = code_sec_rva + pe.sec_align
    return layout_for(code_sec_rva + HDR_SIZE, data_sec_rva)


# --- building ----------------------------------------------------------------
def build(pe, pre, layout, block, meta, reuse, old):
    r = meta["result"]
    code_rva = layout["code_rva"]
    entry_rva = code_rva + r["entry_offset"]
    log_rva = code_rva + r["log_offset"]
    uw_entry_rva = code_rva + r["unwind_entry_offset"]
    uw_log_rva = code_rva + r["unwind_log_offset"]
    if entry_rva == code_rva:
        raise Refuse("the entry point is at the very start of the block, where "
                     "the literals live; the emitter's offsets look wrong")

    host = pre["pdata"]
    ex_rva, ex_size = pre["ex_rva"], pre["ex_size"]
    fns = sorted([(log_rva, log_rva + r["log_size"], uw_log_rva),
                  (entry_rva, entry_rva + r["entry_size"], uw_entry_rva)])

    if reuse:
        pdata_index = old["hdr"]["pdata_index"]
        base = host["raw"] + pdata_index * 12
        new_size = ex_size
    else:
        base = pre["slack_off"]
        pdata_index = ex_size // 12
        new_size = ex_size + 24

    # Ours go at the end, so they must start above every entry that is not ours.
    if pdata_index > 0:
        prev = struct.unpack_from("<III", pe.d, base - 12)
        if fns[0][0] <= prev[0]:
            raise Refuse("our functions (%#x) do not sort after the entry "
                         "before them (%#x)" % (fns[0][0], prev[0]))
    for i, f in enumerate(fns):
        struct.pack_into("<III", pe.d, base + i * 12, *f)
    pe.set_dir_entry(3, ex_rva, new_size)

    header = pack_header(dict(
        code_rva=code_rva, data_rva=layout["data_rva"], code_bytes=len(block),
        entry_rva=entry_rva, entry_size=r["entry_size"], log_rva=log_rva,
        log_size=r["log_size"], unwind_entry_rva=uw_entry_rva,
        unwind_log_rva=uw_log_rva, pdata_index=pdata_index))
    payload = header + block
    data_size = meta["data_block_size"]

    if reuse:
        code = pre["existing"]
        if len(payload) > code["rsz"]:
            raise Refuse("the existing %s holds %d bytes, the new block needs "
                         "%d" % (SEC_CODE.decode(), code["rsz"], len(payload)))
        pe.d[code["raw"]:code["raw"] + code["rsz"]] = \
            payload.ljust(code["rsz"], b"\0")
        struct.pack_into("<I", pe.d, code["off"] + 8, len(payload))
        dsec = pe.section_by_name(SEC_DATA)
        if dsec["vsz"] < data_size:
            raise Refuse("the existing %s is %d bytes, the block needs %d"
                         % (SEC_DATA.decode(), dsec["vsz"], data_size))
    else:
        code_sec_rva = code_rva - HDR_SIZE
        code_raw = align_up(len(pe.d), pe.file_align)
        code_rsz = align_up(len(payload), pe.file_align)
        pe.d += b"\0" * (code_raw - len(pe.d))
        pe.d += payload.ljust(code_rsz, b"\0")
        end = pe.sec_table + pe.nsec * 40
        struct.pack_into("<8s6I2HI", pe.d, end, SEC_CODE, len(payload),
                         code_sec_rva, code_rsz, code_raw, 0, 0, 0, 0, CH_CODE)
        struct.pack_into("<8s6I2HI", pe.d, end + 40, SEC_DATA, data_size,
                         layout["data_rva"], 0, 0, 0, 0, 0, 0, CH_DATA)
        struct.pack_into("<H", pe.d, pe.nt + 6, pe.nsec + 2)
        pe.nsec += 2
        top = layout["data_rva"] + align_up(data_size, pe.sec_align)
        struct.pack_into("<I", pe.d, pe.opt + 56, align_up(top, pe.sec_align))

    site = pe.rva_to_off(CALL_SITE_RVA, 5)
    pe.d[site] = 0xE8
    struct.pack_into("<i", pe.d, site + 1, entry_rva - (CALL_SITE_RVA + 5))
    # Nothing here recomputes the checksum, so it is cleared rather than left
    # stale -- the same thing the glyph-table patch does.
    struct.pack_into("<I", pe.d, pe.opt + 64, 0)
    return dict(code_rva=code_rva, entry_rva=entry_rva, log_rva=log_rva,
                pdata_index=pdata_index, payload=len(payload))


# --- reading the result back --------------------------------------------------
def verify(out_bytes, block, meta, layout, expect):
    pe = Pe(out_bytes)
    problems = []
    code = pe.section_by_name(SEC_CODE)
    data = pe.section_by_name(SEC_DATA)
    if not code or not data:
        return ["the new sections are not in the output"]
    if code["ch"] != CH_CODE:
        problems.append("%s has characteristics %#x, expected %#x"
                        % (SEC_CODE.decode(), code["ch"], CH_CODE))
    if data["ch"] != CH_DATA:
        problems.append("%s has characteristics %#x, expected %#x"
                        % (SEC_DATA.decode(), data["ch"], CH_DATA))
    if code["ch"] & 0x80000000:
        problems.append("%s is writable as well as executable"
                        % SEC_CODE.decode())
    if code["va"] % pe.sec_align or data["va"] % pe.sec_align:
        problems.append("a new section is not aligned to %#x" % pe.sec_align)
    if code["raw"] % pe.file_align or code["rsz"] % pe.file_align:
        problems.append("%s raw data is not file-aligned" % SEC_CODE.decode())
    if code["va"] + align_up(code["vsz"], pe.sec_align) > data["va"]:
        problems.append("the two new sections overlap")
    top = data["va"] + align_up(data["vsz"], pe.sec_align)
    if pe.size_of_image < top:
        problems.append("SizeOfImage %#x does not cover the new sections (%#x)"
                        % (pe.size_of_image, top))
    if data["rsz"] != 0:
        problems.append("the writable block should have no file content")
    if data["vsz"] < meta["data_block_size"]:
        problems.append("the writable block is %d bytes, needs %d"
                        % (data["vsz"], meta["data_block_size"]))

    hdr_off = pe.rva_to_off(code["va"], HDR_SIZE)
    hdr = unpack_header(bytes(pe.d[hdr_off:hdr_off + HDR_SIZE]))
    if hdr["code_rva"] != layout["code_rva"]:
        problems.append("the header records code at %#x, planned %#x"
                        % (hdr["code_rva"], layout["code_rva"]))
    blk_off = pe.rva_to_off(hdr["code_rva"], len(block))
    if bytes(pe.d[blk_off:blk_off + len(block)]) != block:
        problems.append("the emitted block is not what was written")

    off = pe.rva_to_off(CALL_SITE_RVA, 5)
    if pe.d[off] != 0xE8:
        problems.append("the call site is no longer a direct call")
    else:
        rel = struct.unpack_from("<i", pe.d, off + 1)[0]
        target = CALL_SITE_RVA + 5 + rel
        if target != expect["entry_rva"]:
            problems.append("the call goes to %#x, the entry is at %#x"
                            % (target, expect["entry_rva"]))
        if target == hdr["code_rva"]:
            problems.append("the call lands on the literal pool, not the entry")
        if target != hdr["code_rva"] + meta["result"]["entry_offset"]:
            problems.append("the call does not land on entry_offset")

    ex_rva, ex_size = pe.dir_entry(3)
    if ex_size % 12:
        problems.append("the exception directory size %#x is not a multiple "
                        "of 12" % ex_size)
    ex_off = pe.rva_to_off(ex_rva, ex_size)
    entries = [struct.unpack_from("<III", pe.d, ex_off + i * 12)
               for i in range(ex_size // 12)]
    if any(entries[i][0] > entries[i + 1][0] for i in range(len(entries) - 1)):
        problems.append("the exception table is not sorted by start address")
    ours = {hdr["unwind_entry_rva"], hdr["unwind_log_rva"]}
    found = [e for e in entries if e[2] in ours]
    if len(found) != 2:
        problems.append("expected two exception entries of ours, found %d"
                        % len(found))
    for e in found:
        if not (code["va"] <= e[2] < code["va"] + code["vsz"]):
            problems.append("an unwind record at %#x is outside our section"
                            % e[2])
        if not (code["va"] <= e[0] < e[1] <= code["va"] + code["vsz"]):
            problems.append("a function range %#x-%#x is outside our section"
                            % (e[0], e[1]))
    for s in pe.sections():
        if s["va"] == ex_rva and ex_size > max(s["vsz"], s["rsz"]):
            problems.append("the exception directory runs past its section")
    return problems


# --- the file transaction -----------------------------------------------------
def apply(in_path, out_path, emit_tool=None, report=print):
    if same_path(in_path, out_path):
        raise Refuse("the input and the output are the same file: %s"
                     % os.path.abspath(in_path))
    tool = emit_tool or default_emit_tool()

    src = open(in_path, "rb").read()
    pe = Pe(src)
    pre = structural(pe)
    old = None
    reuse = False
    if pre["existing"]:
        report("  a loader entry is already there; checking it belongs to us")
        old = verify_existing(pe, pre, tool)
        layout = old["layout"]
        reuse = True
    else:
        site = pe.rva_to_off(CALL_SITE_RVA, 5)
        have = bytes(pe.d[site:site + 5])
        if have != CALL_ORIG_BYTES:
            raise Refuse("the call at %#x is %s, expected %s -- unsupported "
                         "build" % (CALL_SITE_RVA, have.hex(" "),
                                    CALL_ORIG_BYTES.hex(" ")))
        rel = struct.unpack_from("<i", pe.d, site + 1)[0]
        if CALL_SITE_RVA + 5 + rel != CALL_TARGET_RVA:
            raise Refuse("the call at %#x goes to %#x, expected %#x"
                         % (CALL_SITE_RVA, CALL_SITE_RVA + 5 + rel,
                            CALL_TARGET_RVA))
        layout = plan_new(pe)
    report("  %s layout: code %#x, data %#x"
           % ("reusing" if reuse else "new", layout["code_rva"],
              layout["data_rva"]))

    block, meta = (old["block"], old["meta"]) if reuse \
        else emit_block(tool, layout)
    report("  %d bytes, entry at +%#x" % (len(block),
                                          meta["result"]["entry_offset"]))
    expect = build(pe, pre, layout, block, meta, reuse, old)
    out = bytes(pe.d)

    problems = verify(out, block, meta, layout, expect)
    if problems:
        raise Refuse("the patched image did not verify:\n    "
                     + "\n    ".join(problems))

    # One exclusively created temporary in the output's directory, removed on
    # every failure path.  A fixed ".cielzh-tmp" suffix was not safe: given an
    # input named a.exe.cielzh-tmp and an output of a.exe, the working copy
    # landed on the input and the rename then removed it.
    out_dir = os.path.dirname(os.path.abspath(out_path))
    fd, tmp = tempfile.mkstemp(prefix=".cielzh-", suffix=".tmp", dir=out_dir)
    committed = False
    try:
        if same_path(tmp, in_path) or same_path(tmp, out_path):
            raise Refuse("the temporary file collides with the input or output")
        try:
            with os.fdopen(fd, "wb") as f:
                fd = None
                f.write(out)
                f.flush()
                os.fsync(f.fileno())
        except OSError as e:
            raise Refuse("could not write the temporary file: %s" % e)
        try:
            again = open(tmp, "rb").read()
        except OSError as e:
            raise Refuse("could not read the temporary file back: %s" % e)
        if again != out:
            raise Refuse("the file on disk is not what was written")
        problems = verify(again, block, meta, layout, expect)
        if problems:
            raise Refuse("the file on disk did not verify:\n    "
                         + "\n    ".join(problems))
        if same_path(in_path, out_path):
            raise Refuse("the output now names the input")
        try:
            os.replace(tmp, out_path)
        except OSError as e:
            raise Refuse("could not move the result into place: %s" % e)
        committed = True
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        if not committed and os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
    report("  entry at %#x, call at %#x now points there"
           % (expect["entry_rva"], CALL_SITE_RVA))
    return expect


def inspect(path, report=print):
    pe = Pe(open(path, "rb").read())
    code = pe.section_by_name(SEC_CODE)
    if not code:
        report("no %s section: this executable has no loader entry"
               % SEC_CODE.decode())
        return 0
    off = pe.rva_to_off(code["va"], HDR_SIZE)
    hdr = unpack_header(bytes(pe.d[off:off + HDR_SIZE]))
    for k in HDR_FIELDS:
        report("  %-18s %#x" % (k, hdr[k]))
    site = pe.rva_to_off(CALL_SITE_RVA, 5)
    rel = struct.unpack_from("<i", pe.d, site + 1)[0]
    report("  call %#x -> %#x" % (CALL_SITE_RVA, CALL_SITE_RVA + 5 + rel))
    return 0


def main(argv):
    if len(argv) >= 3 and argv[1] == "--inspect":
        return inspect(argv[2])
    if len(argv) < 3:
        print(__doc__)
        return 2
    tool = None
    if "--emit" in argv:
        tool = argv[argv.index("--emit") + 1]
    try:
        apply(argv[1], argv[2], tool)
    except Refuse as e:
        print("refused: %s" % e)
        return 1
    print("wrote %s" % argv[2])
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv))
