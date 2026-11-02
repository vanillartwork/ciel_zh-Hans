"""Small PE32+ file for the loader tests. No game files or compiler required.

Large gaps between the required RVAs are zero-filled virtual space. Only the
headers, stand-in functions, imports and exception table take space on disk.
The tests patch and inspect this file; they never execute it.
"""
import struct

# Pin the supported input layout independently of the patcher's expectations.
CALL_SITE_RVA, CALL_TARGET_RVA = 0x7b7f05, 0x410b3d
IMPORTS = (
    (0x13e3528, "GetModuleFileNameW"), (0x13e34d0, "LoadLibraryExW"),
    (0x13e3268, "GetProcAddress"), (0x13e31a0, "CreateFileW"),
    (0x13e32f0, "WriteFile"), (0x13e3128, "CloseHandle"),
    (0x13e3208, "GetLastError"),
)


def make_image(with_fontex=False):
    target = CALL_TARGET_RVA & ~0xfff
    site = CALL_SITE_RVA & ~0xfff
    idata = min(slot for slot, _ in IMPORTS) & ~0xfff
    pdata = idata - 0x1000
    sections = [
        # name, RVA, virtual size, raw size, characteristics
        (b".bss", 0x1000, target - 0x1000, 0, 0xc0000080),
        (b".stub", target, site - target, 0x1000, 0x60000020),
        (b".text", site, pdata - site, 0x1000, 0x60000020),
        (b".pdata", pdata, 0x200, 0x200, 0x40000040),
        (b".idata", idata, 0x1000, 0x1000, 0xc0000040),
    ]
    if with_fontex:
        sections.append((b".fontex", idata + 0x1000, 0x200, 0x200, 0x40000040))

    nt, headers = 0x80, 0x400
    buf = bytearray(headers + sum(s[3] for s in sections))

    def put(fmt, at, *values):
        struct.pack_into("<" + fmt, buf, at, *values)

    buf[:2] = b"MZ"
    put("I", 0x3c, nt)
    buf[nt:nt + 4] = b"PE\0\0"
    put("HHIIIHH", nt + 4, 0x8664, len(sections), 0, 0, 0, 0xf0, 0x22)
    opt = nt + 24
    put("H", opt, 0x20b)
    put("II", opt + 16, CALL_TARGET_RVA, target)
    put("QII", opt + 24, 0x140000000, 0x1000, 0x200)
    put("HH", opt + 40, 6, 0)
    put("HH", opt + 48, 6, 0)
    put("II", opt + 56, sections[-1][1] + 0x1000, headers)
    put("HH", opt + 68, 3, 0x100)
    put("QQQQII", opt + 72, 0x100000, 0x1000, 0x100000, 0x1000, 0, 16)
    raw, offsets = headers, {}
    for i, (name, va, vsz, size, flags) in enumerate(sections):
        put("8sIIIIIIHHI", opt + 0xf0 + 40*i, name, vsz, va, size,
            raw if size else 0, 0, 0, 0, 0, flags)
        offsets[va] = raw
        raw += size

    # A direct call, a one-byte return target, and one existing unwind record.
    put("Bi", offsets[site] + CALL_SITE_RVA - site, 0xe8,
        CALL_TARGET_RVA - CALL_SITE_RVA - 5)
    put("B", offsets[target] + CALL_TARGET_RVA - target, 0xc3)
    put("I", offsets[target], 1)   # UNWIND_INFO: version 1, no prologue
    put("III", offsets[pdata], CALL_TARGET_RVA, CALL_TARGET_RVA + 1, target)
    put("II", opt + 112 + 3*8, pdata, 12)

    # Separate single-import descriptors put each thunk at its required RVA.
    imp = offsets[idata]
    put("II", opt + 112 + 8, idata + 0x600, 20*(len(IMPORTS) + 1))
    dll = b"KERNEL32.dll\0"
    buf[imp+0x6b0:imp+0x6b0+len(dll)] = dll
    name_at = 0x800
    for i, (slot, name) in enumerate(IMPORTS):
        ilt = 0x700 + 16*i
        put("IIIII", imp+0x600+20*i, idata+ilt, 0, 0, idata+0x6b0, slot)
        put("Q", imp+ilt, idata+name_at)
        put("Q", imp+slot-idata, idata+name_at)
        hint = b"\0\0" + name.encode("ascii") + b"\0"
        buf[imp+name_at:imp+name_at+len(hint)] = hint
        name_at += (len(hint) + 1) & ~1
    return bytes(buf)
