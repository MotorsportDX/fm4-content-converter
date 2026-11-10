"""Pembaca model track FM2 (`<media>out.NNNNN.rmb.bin` di `bin.zip`), riset 11 November 2026.

Model FM2 adalah kontainer `CAFF21.11.05.0034` dengan section `.gpu`, `.data` dan `.stream`
(urutan section berbeda per model; tabel nama selalu di `.data`):

- `.data` chunk 1: record `rendergraph` versi `30.06.06.0036`, graf objek berserial dengan offset
  relatif terhadap awal record, tabel relokasi di ujungnya, dan shader binary Xbox 360 (magic
  `0x102a1100`). `.data` chunk 2: kumpulan string (nama properti material, nama shader).
- `.gpu` chunk 1: buffer vertex, buffer indeks 16-bit dan microcode; chunk 2: microcode lain.
- `.stream`: program gambar, record `00 LL OP 00` (LL panjang record dalam byte) sampai op `0x1d`,
  lalu area data (render state bernama, misalnya `D3DRS_CULLMODE`).

    python research/tracks-fm2-2026-11-11/fm2_model.py <bin.zip> <model>      # satu model
    python research/tracks-fm2-2026-11-11/fm2_model.py <bin.zip>              # ringkasan semua
"""
import collections
import struct
import sys
import zipfile

from fm4_converter.fm3.integration import archive_read

MAGIC = b"CAFF21.11.05.0034"
SHADER_MAGIC = 0x102A1100
END = 0x1D


class Model:
    def __init__(self, data):
        if not data.startswith(MAGIC):
            raise ValueError("not a CAFF21.11.05.0034 container")
        self.data = data
        n_names, n_chunks = struct.unpack_from(">II", data, 0x18)
        names_at, header = struct.unpack_from(">II", data, 0x44)
        self.sections, at = [], 0x50
        while at + 0x28 <= header:
            name = data[at:at + 8].rstrip(b"\0")
            if not name.startswith(b"."):
                break
            self.sections.append((name.decode(), struct.unpack_from(">I", data, at + 0x10)[0]))
            at += 0x28
        self.base, cursor = {}, header
        for name, size in self.sections:
            self.base[name] = cursor
            cursor += size
        blob = self.base[".data"] + names_at
        size = struct.unpack_from(">I", data, blob)[0]
        offs = struct.unpack_from(f">{n_names}I", data, blob + 4)
        start = blob + 4 + 4 * n_names
        self.names = [data[start + o:data.index(b"\0", start + o)].decode("latin1") for o in offs]
        chunk_at = start + size + 4
        self.chunks = []
        for i in range(n_chunks):
            cid, off, sz = struct.unpack_from(">III", data, chunk_at + 14 * i)
            section = self.sections[data[chunk_at + 14 * i + 12] - 1][0]
            self.chunks.append((section, cid, self.data[self.base[section] + off:self.base[section] + off + sz]))

    def chunk(self, section, cid):
        return next(body for s, c, body in self.chunks if s == section and c == cid)

    @property
    def graph(self):
        return self.chunk(".data", 1)

    @property
    def pool(self):
        found = [body for s, c, body in self.chunks if s == ".data" and c == 2]
        return found[0] if found else b""

    def strings(self):
        out, at = {}, 0
        for part in self.pool.split(b"\0"):
            out[at] = part.decode("latin1")
            at += len(part) + 1
        return out

    def program(self):
        """(header words, [(offset, op, body words)]) of the `.stream` draw program."""
        found = [body for s, c, body in self.chunks if s == ".stream"]
        if not found:
            return (), []
        st = found[0]
        header = struct.unpack_from(">I", st, 0)[0]
        o, out = header, []
        while o + 4 <= len(st):
            w = struct.unpack_from(">I", st, o)[0]
            length, op = (w >> 16) & 0xFF, (w >> 8) & 0xFF
            if w >> 24 or w & 0xFF or length < 4 or o + length > len(st):
                raise ValueError(f"bad program record at {o:#x}")
            out.append((o, op, struct.unpack_from(f">{(length - 4) // 4}I", st, o + 4)))
            o += length
            if op == END:
                break
        return struct.unpack_from(f">{header // 4}I", st, 0), out

    def resources(self):
        """(vertex buffers, index buffers) of the render graph's resource table:
        [(object offset, GPU offset, size)] each. The table ends the graph before its `.data`
        relocation list: vertex buffers as (object, offset, size) triples, then index buffers as
        (object, offset, size, 1); each runtime object is a zeroed slot of the graph (the D3D
        object FM2 fills at load), and a draw (op 1) names its index buffer's object."""
        g = self.graph
        words = struct.unpack(f">{len(g) // 4}I", g[:len(g) // 4 * 4])
        draws = [body for _, op, body in self.program()[1] if op == 1]
        if not draws:
            return [], []
        first = draws[0][2]
        at = next(i for i in range(len(words) - 3)
                  if words[i] == first and words[i + 3] == 1 and words[i + 1] + words[i + 2] <= len(self.chunk(".gpu", 1)))
        ibs, i = [], at
        while i + 3 < len(words) and words[i + 3] == 1 and words[i] < len(g):
            ibs.append(words[i:i + 3])
            i += 4
        # The vertex buffers precede the index buffers in the table, in ascending GPU order (an index
        # buffer may sit between two of them): read backwards while
        # the offsets keep falling (the words before the table are other objects).
        vbs, i, below = [], at - 3, len(self.chunk(".gpu", 1)) + 1
        while i >= 0 and words[i] < len(g) and words[i + 2] and words[i + 1] < below \
                and words[i + 1] + words[i + 2] <= len(self.chunk(".gpu", 1)):
            vbs.insert(0, words[i:i + 3])
            below = words[i + 1]
            if below == 0:
                break
            i -= 3
        return vbs, ibs

    def vertex_buffer(self, ib_offset):
        """The vertex buffer a draw uses: the last one that starts before its index buffer."""
        vbs, _ = self.resources()
        return max((v for v in vbs if v[1] < ib_offset), key=lambda v: v[1])

    def shaders(self):
        """Offsets of the shader binaries in the render graph."""
        g = self.graph
        return [o for o in range(0, len(g) - 4, 4) if struct.unpack_from(">I", g, o)[0] == SHADER_MAGIC]


def models(path):
    z = zipfile.ZipFile(path)
    for info in z.infolist():
        if info.filename.lower().endswith(".rmb.bin"):
            yield info.filename, Model(archive_read(z, info))


if __name__ == "__main__":
    if len(sys.argv) > 2:
        z = zipfile.ZipFile(sys.argv[1])
        m = Model(archive_read(z, sys.argv[2]))
        print("sections", m.sections, "names", m.names)
        print("strings", m.strings())
        print("shaders at", [hex(o) for o in m.shaders()])
        head, recs = m.program()
        print("program header", [hex(x) for x in head])
        for o, op, body in recs:
            print(f"  {o:04x} op {op:#04x} {[hex(x) for x in body]}")
    else:
        ops = collections.Counter()
        for name, m in models(sys.argv[1]):
            for _, op, body in m.program()[1]:
                ops[op, len(body)] += 1
        print(sorted(ops.items(), key=lambda x: -x[1]))
