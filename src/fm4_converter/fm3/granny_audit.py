"""Bounded, lazy GR2 metadata reader for native FM4 driver assets.

Reads the two observed little-endian v7 layouts, resolving file fixups without
installing process pointers. Only section decompression uses a hash-pinned local
Granny DLL. No renderer, animation runtime, or game executable is invoked.
SPDX-License-Identifier: GPL-3.0-only
"""
import ctypes
from functools import lru_cache
import hashlib
import os
from pathlib import Path
from ..paths import PROJECT_ROOT
import struct
import zlib


class GrannyError(ValueError):
    pass


DECODER_SHA256 = "ccabcba2c038b1e6f3569c9c488cd5f43394b70ba4374c751b8b284b9f030e6c"
MAGICS = {
    bytes.fromhex("29de6cc0baa4532b25f5b7a5f666e2ee"): 4,
    bytes.fromhex("e59b495e6f631f141e13eba990beedc4"): 8,
}
PRIMITIVES = {10: "f", 11: "b", 12: "B", 13: "b", 14: "B",
              15: "h", 16: "H", 17: "h", 18: "H", 19: "i", 20: "I",
              21: "e", 23: "I"}


def decoder_path():
    default = PROJECT_ROOT / (
        "outputs/fm-car-converter/import-v1/references/ForzaTechStudio/"
        "ForzaTechStudio/Native/granny2_x64.dll")
    return Path(os.environ.get("FM_GRANNY_DLL", default))


@lru_cache(maxsize=4)
def _decoder(path, digest):
    if digest != DECODER_SHA256:
        raise GrannyError("Unreviewed Granny CPU decoder")
    library = ctypes.CDLL(str(path))
    fn = library.GrannyDecompressData
    fn.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_void_p,
                   ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_void_p]
    fn.restype = ctypes.c_int
    return library, fn


def bounded(data, offset, count):
    if offset < 0 or count < 0 or offset + count > len(data):
        raise GrannyError("GR2 span outside file/section")
    return data[offset:offset + count]


class File:
    def __init__(self, raw):
        if len(raw) < 104 or raw[:16] not in MAGICS:
            raise GrannyError("Unsupported GR2 header")
        self.ptrsize = MAGICS[raw[:16]]
        h = struct.unpack_from("<18I", raw, 32)
        if h[0] != 7 or h[1] != len(raw) or h[3] != 72 or not 1 <= h[4] <= 64:
            raise GrannyError("Unsupported GR2 v7 layout or size")
        if zlib.crc32(raw[104:]) & 0xffffffff != h[2]:
            raise GrannyError("GR2 CRC mismatch")
        self.sections, self.fixups, self.types = [], {}, {}
        table = bounded(raw, 104, h[4] * 44)
        headers = list(struct.iter_unpack("<11I", table))
        if sum(s[3] for s in headers) > 128 * 1024 * 1024:
            raise GrannyError("GR2 expanded data exceeds audit limit")
        path = decoder_path()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        _, decompress = _decoder(str(path.resolve()), digest)
        for s in headers:
            fmt, offset, size, expanded, align, stop0, stop1 = s[:7]
            data = bounded(raw, offset, size)
            if fmt not in (0, 1, 2) or not 0 <= stop0 <= stop1 <= expanded:
                raise GrannyError("Unsupported GR2 compression/section stops")
            if expanded == 0:
                if size:
                    raise GrannyError("Nonempty compressed zero-size section")
                output = b""
            elif fmt == 0:
                if size != expanded:
                    raise GrannyError("Uncompressed GR2 section size mismatch")
                output = data
            else:
                if not size:
                    raise GrannyError("Empty compressed GR2 section")
                src = ctypes.create_string_buffer(data)
                dst = ctypes.create_string_buffer(expanded)
                if not decompress(fmt, 0, size, src, stop0, stop1, expanded, dst):
                    raise GrannyError("GR2 decompression failed")
                output = dst.raw
            self.sections.append(output)
        for index, s in enumerate(headers):
            fixups = bounded(raw, s[7], s[8] * 12)
            bounded(raw, s[9], s[10] * 16)
            for start, section, offset in struct.iter_unpack("<III", fixups):
                bounded(self.sections[index], start, self.ptrsize)
                if section >= len(self.sections):
                    raise GrannyError("GR2 fixup targets unknown section")
                bounded(self.sections[section], offset, 1)
                key = (index, start)
                if key in self.fixups:
                    raise GrannyError("Duplicate GR2 fixup")
                self.fixups[key] = (section, offset)
        self.root = Node(self, (h[5], h[6]), (h[7], h[8]))

    def read(self, at, fmt):
        section, offset = at
        if not 0 <= section < len(self.sections):
            raise GrannyError("GR2 reference targets unknown section")
        return struct.unpack("<" + fmt, bounded(self.sections[section], offset,
                                               struct.calcsize("<" + fmt)))

    def pointer(self, at):
        value = self.read(at, "I" if self.ptrsize == 4 else "Q")[0]
        if at in self.fixups:
            return self.fixups[at]
        if value:
            raise GrannyError("GR2 non-null pointer has no fixup")
        return None

    def string(self, at):
        target = self.pointer(at)
        if target is None:
            return None
        section, start = target
        data = self.sections[section]
        end = data.find(b"\0", start, min(start + 4096, len(data)))
        if end < 0:
            raise GrannyError("Unterminated GR2 string")
        return data[start:end].decode("ascii")

    def layout(self, at, depth=0):
        if depth > 16 or at is None:
            raise GrannyError("Invalid/recursive GR2 inline type")
        if at in self.types:
            return self.types[at]
        section, start = at
        fields, size = {}, 0
        for i in range(256):
            pos = start + i * (20 + 3 * self.ptrsize)
            kind = self.read((section, pos), "I")[0]
            if kind == 0:
                self.types[at] = (fields, size)
                return fields, size
            name = self.string((section, pos + 4))
            child = self.pointer((section, pos + 4 + self.ptrsize))
            width = self.read((section, pos + 4 + 2 * self.ptrsize), "I")[0]
            if not name or name in fields or width > 65536:
                raise GrannyError("Invalid GR2 member name/width")
            count = max(1, width)
            if kind == 1:
                unit = self.layout(child, depth + 1)[1]
            elif kind in (2, 8, 22):
                unit = self.ptrsize
            elif kind in (3, 4):
                unit = 4 + self.ptrsize
            elif kind == 5:
                unit = 2 * self.ptrsize
            elif kind == 9:
                unit = 68
            elif kind in PRIMITIVES:
                unit = struct.calcsize("<" + PRIMITIVES[kind])
            else:
                raise GrannyError(f"Unsupported GR2 member type {kind}")
            fields[name] = (size, kind, child, count)
            size += unit * count
        raise GrannyError("Unterminated GR2 type definition")


class Node:
    def __init__(self, file, datatype, at):
        self.file, self.datatype, self.at = file, datatype, at
        fields, size = file.layout(datatype)
        file.read(at, f"{size}s")
        self.fields = fields

    def get(self, name):
        f, (section, start) = self.file, self.at
        offset, kind, child, width = self.fields[name]
        at = (section, start + offset)
        if kind == 8:
            return f.string(at)
        if kind == 2:
            pointer = f.pointer(at)
            return Node(f, child, pointer) if pointer else None
        if kind == 1:
            if width != 1:
                raise GrannyError("Inline GR2 array not requested by this audit")
            return Node(f, child, at)
        if kind == 5:
            dtype = f.pointer(at)
            pointer = f.pointer((section, at[1] + f.ptrsize))
            return Node(f, dtype, pointer) if pointer else None
        if kind in (3, 4):
            count = f.read(at, "I")[0]
            pointer = f.pointer((section, at[1] + 4))
            if count > 100000 or bool(count) != bool(pointer):
                raise GrannyError("Invalid GR2 array count/pointer")
            if not count:
                return []
            stride = f.ptrsize if kind == 4 else f.layout(child)[1]
            f.read(pointer, f"{stride * count}s")
            entries = [(pointer[0], pointer[1] + i * stride) for i in range(count)]
            if kind == 4:
                entries = [f.pointer(p) for p in entries]
            if any(p is None for p in entries):
                raise GrannyError("Null GR2 array element")
            return [Node(f, child, p) for p in entries]
        if kind == 9:
            return f.read(at, "I16f")
        if kind in PRIMITIVES:
            values = f.read(at, PRIMITIVES[kind] * width)
            return values[0] if width == 1 else values
        raise GrannyError(f"Unsupported GR2 field access {name}")
