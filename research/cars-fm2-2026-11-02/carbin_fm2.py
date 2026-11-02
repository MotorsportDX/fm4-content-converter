"""Decoder riset .carbin bodi mobil FM2, mengikuti urutan baca Forza Studio (ForzaVersion.Two).

Acuan: ForzaCarBin.cs, ForzaCarSection.cs, ForzaCarSubSection.cs dan ForzaVertex.cs dari
Forza Studio (Mike Davis, MIT) di checkout ForzaEditor yang dipin untuk helper CPU. Berbeda
dari Forza Studio, decoder ini tidak menelan exception, mencatat offset setiap blok, dan
menolak indeks di luar buffer. Hanya membaca; tidak ada penulis FM2 atau FM4 di sini.
"""
from dataclasses import dataclass, field
import struct

FM2_MARKER = 0x2CA
SECTION_MARKERS = (0x2C9, 2, 5)
VERTEX_SIZE = 60
TRI_LIST, TRI_STRIP = 4, 6


class FormatError(ValueError):
    pass


class Reader:
    def __init__(self, data):
        self.data, self.pos = data, 0

    def need(self, n):
        if n < 0 or self.pos + n > len(self.data):
            raise FormatError(f'read {n} bytes at 0x{self.pos:x} past end 0x{len(self.data):x}')

    def skip(self, n):
        self.need(n)
        self.pos += n

    def u8(self):
        self.need(1)
        self.pos += 1
        return self.data[self.pos - 1]

    def u32(self):
        self.need(4)
        self.pos += 4
        return struct.unpack_from('>I', self.data, self.pos - 4)[0]

    def i32(self):
        return struct.unpack('>i', struct.pack('>I', self.u32()))[0]

    def f32s(self, n):
        self.need(4 * n)
        self.pos += 4 * n
        return struct.unpack_from(f'>{n}f', self.data, self.pos - 4 * n)

    def ascii(self, n):
        self.need(n)
        self.pos += n
        return self.data[self.pos - n:self.pos].decode('ascii')

    def counted_skip(self, unit):
        """u32 jumlah lalu jumlah*unit byte; mengembalikan jumlah."""
        n = self.u32()
        self.skip(n * unit)
        return n


def is_fm2(data):
    """Aturan deteksi Forza Studio: type 1 + 0x2CA di 4, atau type 2 + 0x2CA di 0x104."""
    if len(data) <= 0x200:
        return False
    kind = struct.unpack_from('>I', data, 0)[0]
    return ((kind == 1 and struct.unpack_from('>I', data, 4)[0] == FM2_MARKER)
            or (kind == 2 and struct.unpack_from('>I', data, 0x104)[0] == FM2_MARKER))


@dataclass
class SubSection:
    name: str
    index_type: int
    lod: int
    index_size: int
    indices: list
    offset: int


@dataclass
class Section:
    name: str
    offset: int
    marker: int | None
    origin: tuple
    bounds_min: tuple
    bounds_max: tuple
    vb_test: tuple
    buffer: str
    base: int = 0
    subsections: list = field(default_factory=list)


@dataclass
class Model:
    type_id: int
    sections: list
    glass: list
    body: list
    buffers_offset: int
    end: int
    size: int


def uv_word(word):
    """UV FM2: u16 fixed-point, (word - 32768) / 1310.72, rentang [-25, 25).

    Forza Studio membacanya sebagai half float lalu mengalikan 12800; itu hanya benar selama
    exponent half <= 1. Skala 32768/25 dicocokkan dengan UV FM3 pada mobil yang sama.
    """
    return (word - 32768) / 1310.72


def read_vertices(r, count, size):
    """Vertex: (posisi, uv0, uv1, normal 11:11:10, 40 byte sisa) dengan posisi = xyz*w (half)."""
    if size != VERTEX_SIZE:
        raise FormatError(f'vertex size {size} at 0x{r.pos:x}, FM2 car parts use {VERTEX_SIZE}')
    r.need(count * size)
    out = []
    for i in range(count):
        p = r.pos + i * size
        x, y, z, w = struct.unpack_from('>4e', r.data, p)
        u0, v0, u1, v1 = map(uv_word, struct.unpack_from('>4H', r.data, p + 8))
        normal, = struct.unpack_from('>I', r.data, p + 16)
        out.append(((x * w, y * w, z * w), (u0, v0), (u1, v1), normal, r.data[p + 20:p + 60]))
    r.pos += count * size
    return out


def unpack_normal(u):
    """ToN3 Forza Studio: X/Y 11 bit, Z 10 bit, bertanda."""
    sx = lambda v, bits: v - (1 << bits) if v >> (bits - 1) else v
    return (sx(u & 0x7FF, 11) / 1023, sx((u >> 11) & 0x7FF, 11) / 1023, sx((u >> 22) & 0x3FF, 10) / 511)


def skip_header(r):
    type_id = r.u32()
    if r.u32() != FM2_MARKER:
        if type_id == 2:
            r.skip(0x100)
        elif type_id == 1:
            r.skip(20)
    r.skip(4)
    r.counted_skip(140)
    r.skip(0x6C)
    for _ in range(r.u32() * 2):
        r.counted_skip(4)
    r.skip(4)
    return type_id


def section_head(r):
    start = r.pos
    marker = r.u32()
    if marker not in SECTION_MARKERS:
        r.pos -= 4
        marker = None
    origin, bmin, bmax = r.f32s(3), r.f32s(3), r.f32s(3)
    r.skip(0x1C)
    r.counted_skip(0x10)
    r.skip(4)
    r.counted_skip(2)
    r.skip(4)
    vb = (r.u32(), r.u32())
    name = r.ascii(r.u8())
    r.skip(8)
    return start, marker, origin, bmin, bmax, vb, name


def subsection(r, base):
    start = r.pos
    r.skip(8)
    name = r.ascii(r.i32())
    index_type, lod = r.u32(), r.i32()
    if r.u32() != 3:
        raise FormatError(f'subsection {name!r} at 0x{start:x}: index marker != 3')
    count, size = r.i32(), r.i32()
    if size not in (2, 4) or count < 0:
        raise FormatError(f'subsection {name!r}: index count {count} size {size}')
    r.need(count * size)
    raw = struct.unpack_from(f'>{count}{"H" if size == 2 else "I"}', r.data, r.pos)
    r.pos += count * size
    restart = 0xFFFF if size == 2 else 0xFFFFFF
    indices = [-1 if (i == restart if size == 2 else i >= restart) else i + base for i in raw]
    if index_type not in (TRI_LIST, TRI_STRIP):
        raise FormatError(f'subsection {name!r}: index type {index_type}')
    return SubSection(name, index_type, lod, size, indices, start)


def parse(data):
    if not is_fm2(data):
        raise FormatError('not an FM2 carbin')
    r = Reader(data)
    type_id = skip_header(r)
    count = r.u32()
    sections_at = r.pos
    # Pass 1 (seperti Forza Studio): lewati semua section untuk menemukan buffer kaca dan bodi bersama.
    for _ in range(count):
        *_, name = section_head(r)
        lod_count, lod_size = r.i32(), r.u32()
        if lod_count:
            raise FormatError(f'section {name!r} has {lod_count} own LOD vertices; pass 1 assumes none')
        r.skip(4)
        for _ in range(r.u32()):
            r.skip(8)
            r.skip(r.i32())
            r.skip(12)
            n, size = r.u32(), r.u32()
            r.skip(n * size)
    buffers_offset = r.pos
    r.skip(8)
    glass_count, glass_size = r.i32(), r.u32()
    r.skip(4)
    glass = read_vertices(r, glass_count, glass_size) if glass_count > 0 else []
    r.skip(12)
    body_count, body_size = r.i32(), r.u32()
    r.skip(4)
    body = read_vertices(r, body_count, body_size) if body_count > 0 else []
    end = r.pos
    # Pass 2: section dengan indeks. Indeks tiap section lokal, ditumpuk berurutan di buffer bersama.
    r.pos = sections_at
    sections, next_base = [], {'glass': 0, 'body': 0}
    for _ in range(count):
        start, marker, origin, bmin, bmax, vb, name = section_head(r)
        if vb[0] == vb[1]:
            buffer = 'glass'
        elif vb[0] == 0:
            buffer = 'body'
        else:
            raise FormatError(f'section {name!r}: vbTest {vb} selects neither shared buffer')
        r.skip(8)
        r.skip(4)
        section = Section(name, start, marker, origin, bmin, bmax, vb, buffer, next_base[buffer])
        section.subsections = [subsection(r, section.base) for _ in range(r.u32())]
        top = max((i for s in section.subsections for i in s.indices), default=-1)
        next_base[buffer] = max(next_base[buffer], top + 1)
        sections.append(section)
    if r.pos != buffers_offset:
        raise FormatError(f'pass 2 ended at 0x{r.pos:x}, pass 1 at 0x{buffers_offset:x}')
    limit = {'glass': len(glass), 'body': len(body)}
    for s in sections:
        for sub in s.subsections:
            bad = [i for i in sub.indices if i >= limit[s.buffer]]
            if bad:
                raise FormatError(f'{s.name}/{sub.name}: index {bad[0]} >= {s.buffer} buffer {limit[s.buffer]}')
    return Model(type_id, sections, glass, body, buffers_offset, end, len(data))


def faces(sub):
    """Segitiga dari tri list atau tri strip (restart -1, degenerasi dibuang), urutan seperti Forza Studio."""
    idx = sub.indices
    if sub.index_type == TRI_LIST:
        return [tuple(idx[i:i + 3]) for i in range(0, len(idx) - 2, 3)]
    out, flip, i = [], True, 0
    while i < len(idx) - 2:
        a, b, c = idx[i:i + 3]
        if c == -1:
            i += 3
            flip = True
            continue
        if a != b and b != c and a != c:
            out.append((a, b, c) if flip else (b, a, c))
        flip = not flip
        i += 1
    return out
