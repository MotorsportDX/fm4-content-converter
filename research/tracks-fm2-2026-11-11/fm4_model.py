"""Model track FM4 (RMB v5/v6) satu sub-model dan satu mesh: baca, ganti geometri, tulis ulang.

Urutan field mengikuti `CTrackModel` (template 010 Editor `FM3_rmb_bin.bt` dari Forza-X360-IO,
GPL-3.0, dipakai sebagai rujukan format): versi, MinBounds, MaxBounds, WorldTransform; urutan
sub-model (versi, NumLODs 0); container sub-model; per sub-model versi, OffsetFromModelOrigin,
MinBounds, MaxBounds, lalu TSubModel (versi, nama, buffer vertex: versi, jumlah, stride, data;
container mesh: versi, jumlah); per mesh versi CTrackMesh, versi CMesh, nama, LOD, tipe primitif,
indeks material, UnpackingData (versi, PositionOffset, PositionScale, UVOffsetScale), buffer
indeks (versi, jumlah, stride, data), flag mesh. Sisanya (material, nama, command buffer) dibawa
apa adanya dan command buffer-nya di-patch (`with_geometry`).

    python research/tracks-fm2-2026-11-11/fm4_model.py <bin.zip FM4> <model>
"""
import struct
import sys
import zipfile

from fm4_converter.fm3 import track_rmb
from fm4_converter.fm3.integration import archive_read

DRAW_INDX = 0x22


class R:
    def __init__(self, d, o=0):
        self.d, self.o = d, o

    def u(self):
        v = struct.unpack_from(">I", self.d, self.o)[0]
        self.o += 4
        return v

    def f(self, n):
        v = struct.unpack_from(f">{n}f", self.d, self.o)
        self.o += 4 * n
        return v

    def s(self):
        n = self.u()
        v = self.d[self.o:self.o + n]
        self.o += n
        return v


class OneMesh:
    """Offsets of the fields `with_geometry` replaces in a one-sub-model, one-mesh model."""

    def __init__(self, d):
        self.d = d
        r = R(d)
        self.version = r.u()
        self.bounds_at = r.o
        r.f(8)                      # MinBounds, MaxBounds
        r.f(16)                     # WorldTransform
        r.u()                       # TBaseModel version
        assert r.u() in (4, 5, 6) and r.u() == 0, "ordered sub-models"
        r.u()                       # container version
        if r.u() != 1:
            raise ValueError("not one sub-model")
        assert r.u() == 1
        self.sub_bounds_at = r.o
        r.f(12)                     # offset, min, max
        assert r.u() == 1
        self.name = r.s()
        assert r.u() == 2
        self.vb_at = r.o
        self.vcount, self.stride = r.u(), r.u()
        r.o += self.vcount * self.stride
        self.vb_end = r.o
        assert r.u() == 1
        if r.u() != 1:
            raise ValueError("not one mesh")
        assert r.u() == 1
        self.mesh_version = r.u()
        self.mesh_name = r.s()
        self.lod, self.prim, self.material = r.u(), r.u(), r.u()
        self.unpack_at = r.o
        assert r.u() == 1
        self.position_offset, self.position_scale, self.uv_offset_scale = r.f(4), r.f(4), r.f(4)
        self.ib_at = r.o
        assert r.u() == 3
        self.icount, self.istride = r.u(), r.u()
        r.o += self.icount * self.istride
        self.ib_end = r.o
        self.tail_at = r.o          # mesh flags, materials, names, command buffers
        self.group = track_rmb.group(d)

    def with_geometry(self, vertices, indices, prim, bounds, uv_offset_scale=None):
        """The model with these vertices (bytes, the template's stride), 16-bit indices and
        primitive, its bounds ((min xyz), (max xyz)), and DRAW_INDX's index counts patched in
        every slot."""
        if len(vertices) % self.stride:
            raise ValueError("vertex data is not of the template's stride")
        lo, hi = bounds
        d = bytearray(self.d)
        head = bytearray(d[:self.vb_at])
        struct.pack_into(">8f", head, self.bounds_at, *lo, 0.0, *hi, 0.0)
        centre = [(a + b) / 2 for a, b in zip(lo, hi)]
        struct.pack_into(">12f", head, self.sub_bounds_at, *centre, 0.0, *lo, 0.0, *hi, 0.0)
        mesh = bytearray(d[self.vb_end:self.ib_at])
        # The primitive type is the word before the material index, three words before UnpackingData.
        prim_at = self.unpack_at - 8 - self.vb_end
        struct.pack_into(">I", mesh, prim_at, prim)
        if uv_offset_scale is not None:
            struct.pack_into(">4f", mesh, self.unpack_at - self.vb_end + 4 + 32, *uv_offset_scale)
        out = (bytes(head) + struct.pack(">II", len(vertices) // self.stride, self.stride) + vertices
               + bytes(mesh) + struct.pack(">III", 3, len(indices), 2)
               + struct.pack(f">{len(indices)}H", *indices) + d[self.ib_end:self.group.at])
        g = track_rmb.group(self.d)
        for part in g.parts:
            part[1] = patch_draws(part[1], len(indices))
        return out + g.encode()


def patch_draws(physical, count):
    """Every DRAW_INDX of a slot's physical part drawing `count` indices."""
    buf = bytearray(physical)
    o = 0
    while o + 4 <= len(buf):
        h = struct.unpack_from(">I", buf, o)[0]
        kind = h >> 30
        n = ((h >> 16) & 0x3FFF) + 1
        if kind == 3 and (h >> 8) & 0x7F == DRAW_INDX:
            # [viz query, VGT_DRAW_INITIATOR (count << 16 | flags), index base, size (count, swap)]
            init = struct.unpack_from(">I", buf, o + 8)[0]
            struct.pack_into(">I", buf, o + 8, (count << 16) | (init & 0xFFFF))
            size = struct.unpack_from(">I", buf, o + 16)[0]
            struct.pack_into(">I", buf, o + 16, (size & 0xFF000000) | count)
            o += 4 + 4 * n
        elif kind == 3 or kind == 0:
            o += 4 + 4 * n
        else:
            o += 4
    return bytes(buf)


if __name__ == "__main__":
    m = OneMesh(archive_read(zipfile.ZipFile(sys.argv[1]), sys.argv[2]))
    print(m.name, m.mesh_name, "vertices", m.vcount, "x", m.stride, "indices", m.icount, "prim", m.prim,
          "material", m.material, "unpack", m.position_offset, m.position_scale, m.uv_offset_scale,
          "slots", [i for i, s in enumerate(m.group.slots) if s["sizes"] != (0, 0, 0)])
