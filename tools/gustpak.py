"""Gust PAK (KTGL) reader/writer for Ciel nosurge DX (Windows).

Format
------
header  : u32 version(0x00020000) | u32 nb_files | u32 header_size(16) | u32 flags
entry   : char name[128] | u32 size | u8 key[20] | u64 data_offset | u32 flags | pad -> 168 bytes
data    : starts at 16 + nb_files*168 ; each file XOR'd with its 20-byte key
          (an all-zero key means the entry is stored in the clear)
"""
import struct, os

ENTRY_SIZE = 0xA8
HDR_SIZE = 16


def _xor(data, key):
    if not any(key):
        return data
    k = bytes(key) * (len(data) // 20 + 2)
    return bytes(a ^ b for a, b in zip(data, k))


class Entry:
    __slots__ = ("name", "raw_name", "size", "key", "offset", "flags", "index")

    def __init__(self, name, raw_name, size, key, offset, flags, index):
        self.name, self.raw_name, self.size, self.key = name, raw_name, size, key
        self.offset, self.flags, self.index = offset, flags, index

    @property
    def path(self):
        """Normalised forward-slash path without the leading separator."""
        return self.name.strip("\\").replace("\\", "/")

    def __repr__(self):
        return f"<Entry {self.name} {self.size}B>"


class Pak:
    def __init__(self, path):
        self.path = path
        self.fh = open(path, "rb")
        ver, nb, hdr, flags = struct.unpack("<4I", self.fh.read(HDR_SIZE))
        if ver != 0x20000 or hdr != HDR_SIZE:
            raise ValueError(f"{path}: unexpected header {ver:#x}/{hdr}")
        self.version, self.flags = ver, flags
        table = self.fh.read(nb * ENTRY_SIZE)
        self.data_start = HDR_SIZE + nb * ENTRY_SIZE
        self.entries = []
        for i in range(nb):
            e = table[i * ENTRY_SIZE:(i + 1) * ENTRY_SIZE]
            raw_name = e[0:128]
            size, = struct.unpack("<I", e[128:132])
            key = e[132:152]
            off, = struct.unpack("<Q", e[152:160])
            eflags, = struct.unpack("<I", e[160:164])
            name = _xor(raw_name, key).split(b"\0")[0].decode("utf-8", "replace")
            self.entries.append(Entry(name, raw_name, size, key, off, eflags, i))
        self._by_path = {e.path.lower(): e for e in self.entries}

    def read(self, entry):
        if isinstance(entry, str):
            entry = self._by_path[entry.strip("\\").replace("\\", "/").lower()]
        self.fh.seek(self.data_start + entry.offset)
        return _xor(self.fh.read(entry.size), entry.key)

    def get(self, path):
        return self._by_path.get(path.strip("\\").replace("\\", "/").lower())

    def close(self):
        self.fh.close()

    def __iter__(self):
        return iter(self.entries)

    def __len__(self):
        return len(self.entries)


def rebuild(src_pak, replacements, out_path, progress=None):
    """Write a new PAK, substituting {entry_path_lower: new_bytes}.

    Offsets are recomputed; every file keeps its original XOR key so the
    game decrypts it exactly as before.
    """
    ents = src_pak.entries
    blobs, offset = [], 0
    offsets, sizes = [], []
    for e in ents:
        new = replacements.get(e.path.lower())
        data = src_pak.read(e) if new is None else new
        offsets.append(offset)
        sizes.append(len(data))
        blobs.append(_xor(data, e.key))
        offset += len(data)
        if progress and e.index % 500 == 0:
            progress(e.index, len(ents))
    with open(out_path, "wb") as o:
        o.write(struct.pack("<4I", src_pak.version, len(ents), HDR_SIZE, src_pak.flags))
        for e, off, sz in zip(ents, offsets, sizes):
            o.write(e.raw_name)   # verbatim -> untouched entries stay byte-identical
            o.write(struct.pack("<I", sz))
            o.write(bytes(e.key))
            o.write(struct.pack("<Q", off))
            o.write(struct.pack("<I", e.flags))
            o.write(b"\0" * (ENTRY_SIZE - 164))
        for b in blobs:
            o.write(b)
