"""Bounded CPU-only XDS mip reader; it never creates a graphics device.

Format references: ForzaEditor XdsTexture*.cs and XenosTiling.cs at revision
8807c7d137646dab8d9eecab7e8d5a6602ef58aa (Xenos addressing from Xenia).
Credit: FMdangaina / ForzaEditor, Mike Davis / Forza Studio, and Ben Vanik
with Xenia contributors. See CREDITS.md and THIRD_PARTY_NOTICES.md at repo root.
SPDX-License-Identifier: GPL-3.0-only
"""
import hashlib
import struct


class TextureError(ValueError):
    pass


FORMATS = {6: ("RGBA8", 1, 4), 50: ("RGBA8", 1, 4),
           18: ("DXT1", 4, 8), 51: ("DXT1", 4, 8),
           19: ("DXT3", 4, 16), 52: ("DXT3", 4, 16),
           20: ("DXT5", 4, 16), 53: ("DXT5", 4, 16),
           49: ("DXN", 4, 16), 59: ("DXT5A", 4, 8)}


def align(value, size):
    return (value + size - 1)//size*size


def tiled_address(x, y, pitch, log_bytes):
    outer = (((y >> 5)*(pitch >> 5))+(x >> 5)) << 6
    inner = (((y >> 1) & 7) << 3) | (x & 7)
    offset = (outer | inner) << log_bytes
    pipe = ((x >> 3) & 3) ^ (((y >> 3) & 1) << 1)
    return (((y & 1) << 4) | (pipe << 6) | (((y >> 4) & 1) << 11)
            | (offset & 15) | (((offset >> 4) & 1) << 5)
            | (((offset >> 5) & 7) << 8) | ((offset >> 8) << 12))


class Texture:
    def __init__(self, data):
        if len(data) < 52:
            raise TextureError("Truncated XDS header")
        self.header = struct.unpack_from(">13I", data)
        if self.header[:2] != (3, 1):
            raise TextureError("Unsupported XDS version or type")
        f = self.header[7:]
        self.format = f[1] & 63
        if (f[5] >> 9) & 3 != 1 or self.format not in FORMATS:
            raise TextureError("Unsupported XDS dimension or format")
        self.codec, self.block, self.bytes = FORMATS[self.format]
        self.width, self.height = (f[2] & 8191)+1, ((f[2] >> 13) & 8191)+1
        self.pitch = ((f[0] >> 22) & 511) << 5
        if self.pitch < self.width:
            raise TextureError("Texture pitch is smaller than its width")
        self.tiled = bool(f[0] >> 31)
        self.endian = (f[1] >> 6) & 3
        self.base, self.mip = (f[1] >> 12)*4096, (f[5] >> 12)*4096
        self.gamma = (f[0] >> 2) & 63
        self.packed = max(0, (min(self.width, self.height)-1).bit_length()-4) if f[5] & 2048 else 100
        self.base_tail = self.mip == 0 and self.packed == 0
        self.levels = (min((f[4] >> 6) & 15, max(self.width, self.height).bit_length()-1)+1
                       if self.mip or self.base_tail else 1)
        self.data = data[52:]

    def storage(self, level, base=False):
        width = self.pitch if base else max((1 << (self.width-1).bit_length()) >> level, 1)
        height = self.height if base else max((1 << (self.height-1).bit_length()) >> level, 1)
        pitch = align((width+self.block-1)//self.block, 32)
        rows = align((height+self.block-1)//self.block, 32)
        row_bytes = pitch*self.bytes if self.tiled else align(pitch*self.bytes, 256)
        return pitch, row_bytes, align(row_bytes*rows, 4096)

    def layout(self, level):
        if not 0 <= level < self.levels:
            raise TextureError("Mip level outside texture")
        width, height = max(self.width >> level, 1), max(self.height >> level, 1)
        x, y = 0, 0
        if level == 0 or self.base_tail:
            offset, (pitch, row_bytes, _) = self.base, self.storage(0, True)
        else:
            storage_level = min(level, self.packed)
            offset = self.mip + sum(self.storage(n)[2] for n in range(1, storage_level))
            pitch, row_bytes, _ = self.storage(storage_level)
        if level >= self.packed:
            lw, lh = (self.width-1).bit_length(), (self.height-1).bit_length()
            tail = level-self.packed
            if tail < 3:
                if lw > lh:
                    y = 16 >> tail
                else:
                    x = 16 >> tail
            elif lw > lh:
                x = (1 << (lw-self.packed)) >> (tail-2)
            else:
                y = (1 << (lh-self.packed)) >> (tail-2)
            x, y = x//self.block, y//self.block
        return width, height, offset, pitch, row_bytes, x, y

    def read_level(self, level):
        width, height, offset, pitch, row_bytes, x0, y0 = self.layout(level)
        bw, bh = (width+self.block-1)//self.block, (height+self.block-1)//self.block
        result = bytearray(bw*bh*self.bytes)
        view = memoryview(result)
        source = memoryview(self.data)
        log_bytes = self.bytes.bit_length()-1
        dest = 0
        for y in range(bh):
            for x in range(bw):
                at = offset + (tiled_address(x+x0, y+y0, pitch, log_bytes) if self.tiled
                               else (y+y0)*row_bytes+(x+x0)*self.bytes)
                if at < 0 or at+self.bytes > len(source):
                    raise TextureError(f"Mip {level} block ({x},{y}) outside XDS payload")
                view[dest:dest+self.bytes] = source[at:at+self.bytes]
                dest += self.bytes
        if self.endian:
            step = 2 if self.endian == 1 else 4
            order = (1, 0) if step == 2 else ((3, 2, 1, 0) if self.endian == 2 else (2, 3, 0, 1))
            swapped = bytearray(len(result))
            for to, src in enumerate(order):
                swapped[to::step] = result[src::step]
            result = swapped
        return bytes(result)

    def audit(self):
        levels = []
        for level in range(self.levels):
            blocks = self.read_level(level)
            width, height, *_ = self.layout(level)
            levels.append({"level": level, "width": width, "height": height,
                           "linear_bytes": len(blocks),
                           "sha256": hashlib.sha256(blocks).hexdigest()})
        return {"codec": self.codec, "width": self.width, "height": self.height,
                "tiled": self.tiled, "gamma_sign_bits": self.gamma, "mips": levels,
                "all_referenced_blocks_in_bounds": True, "cpu_only": True}


def compare(source, target):
    a, b = Texture(source), Texture(target)
    fields = ("codec", "width", "height", "pitch", "endian", "base", "mip", "levels", "tiled", "packed")
    if any(getattr(a, key) != getattr(b, key) for key in fields):
        raise TextureError("Texture layout or codec changed")
    if a.data != b.data:
        raise TextureError("Source pixel payload changed")
    # Identical layout and pixel bytes imply identical decoded block bytes at
    # every mip. Enumerate the target to reject truncated/misaligned payloads.
    return {**b.audit(), "source_pixels_unchanged": True,
            "all_mip_blocks_preserved": True}
