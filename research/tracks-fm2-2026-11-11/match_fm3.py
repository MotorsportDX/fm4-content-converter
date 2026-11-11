"""Pasangan objek New York FM2 dan FM3 yang posisinya sama, untuk menurunkan rumus UV FM2.

FM3 menyimpan posisi lokal (UnpackingData: offset dan skala) dan menempatkan model lewat instans
PVS (translasi `f40`); FM2 menyimpan posisi dunia. Vertex pertama setiap model FM3 (di dunia)
dicari di antara vertex model FM2. Untuk pasangan yang cocok, UV mentah FM2 (16_16, bilangan
bulat menurut `vfetch`) dibandingkan dengan UV FM3 setelah UVOffsetScale-nya.

    python research/tracks-fm2-2026-11-11/match_fm3.py <FM2 NewYork bin.zip> <FM3 NewYork bin.zip> <FM3 pvs>
"""
import io
import contextlib
import struct
import sys
import zipfile

import numpy as np

from fm2_model import Model
from plan_view import extent, stride_of
from fm4_converter.fm3 import track_pvs
from fm4_converter.fm3.integration import archive_read


def fm3_meshes(d):
    """[(positions world-less local float3 (n,3), uv0 raw (n,2) u16, uv offset/scale)] of an FM3 v4 model."""
    o = 4 + 32 + 64 + 4 + 8 + 4
    count = struct.unpack_from(">I", d, o)[0]
    o += 4
    out = []
    for _ in range(count):
        o += 4 + 48 + 4
        n = struct.unpack_from(">I", d, o)[0]
        o += 4 + n + 4
        vcount, stride = struct.unpack_from(">II", d, o)
        o += 8
        raw = np.frombuffer(d, np.uint8, vcount * stride, o).reshape(vcount, stride)
        o += vcount * stride
        o += 4
        meshes = struct.unpack_from(">I", d, o)[0]
        o += 4
        unpack = None
        for _ in range(meshes):
            o += 4 + 4
            n = struct.unpack_from(">I", d, o)[0]
            o += 4 + n + 12
            o += 4
            po, ps, uvos = struct.unpack_from(">4f", d, o), struct.unpack_from(">4f", d, o + 16), struct.unpack_from(">4f", d, o + 32)
            o += 48
            if unpack is None:
                unpack = (po, ps, uvos)
            o += 4
            icount, isize = struct.unpack_from(">II", d, o)
            o += 8 + icount * isize + 4
        pos = raw[:, :12].copy().view(">f4").reshape(-1, 3)
        uv = raw[:, 16:20].copy().view(">u2").reshape(-1, 2) if stride >= 20 else None
        out.append((pos, uv, unpack))
    return out


def main(fm2_zip, fm3_zip, fm3_pvs):
    p = track_pvs.parse(open(fm3_pvs, "rb").read())
    z3 = zipfile.ZipFile(fm3_zip)
    names3 = {i.filename.lower(): i for i in z3.infolist()}
    prefix = p["s132"].lower()
    world = {}
    for inst in p["l36"][:600]:
        name = f"{prefix}.{inst['u0']:05d}.rmb.bin"
        if name not in names3:
            continue
        try:
            meshes = fm3_meshes(archive_read(z3, names3[name]))
        except (struct.error, ValueError):
            continue
        for pos, uv, unpack in meshes:
            if uv is None or len(pos) < 4:
                continue
            po, ps, uvos = unpack
            w = pos * np.array(ps[:3]) + np.array(po[:3]) + np.array(inst["f40"])
            world[tuple(np.round(w[0], 2))] = (name, w, uv, uvos)
    print("fm3 meshes", len(world))
    z2 = zipfile.ZipFile(fm2_zip)
    found = 0
    for info in z2.infolist():
        if not info.filename.lower().endswith(".rmb.bin") or found >= 6:
            continue
        m = Model(archive_read(z2, info))
        try:
            vbs, ibs = m.resources()
        except StopIteration:
            continue
        gpu = m.chunk(".gpu", 1) if ibs else b""
        for vb in vbs:
            for stride in sorted(s for s in stride_of(m) if s):
                if vb[2] % stride:
                    continue
                n = vb[2] // stride
                raw = np.frombuffer(gpu, np.uint8, n * stride, vb[1]).reshape(n, stride)
                pos = raw[:, :12].copy().view(">f4").reshape(-1, 3)
                if not np.isfinite(pos).all():
                    continue
                keys = {tuple(np.round(v, 2)): k for k, v in enumerate(pos)}
                for key, (name, w, uv3, uvos) in world.items():
                    if key in keys:
                        k = keys[key]
                        uv2 = raw[k:k + 1, 16:20].copy().view(">i2").reshape(-1, 2)
                        u3 = uv3[0] / 65535.0 * np.array(uvos[2:]) + np.array(uvos[:2])
                        print(info.filename, "=", name, "fm2 raw uv", uv2[0], "fm3 uv", np.round(u3, 4), "uvos", uvos)
                        found += 1
                        break
    print("matches", found)


if __name__ == "__main__":
    main(*sys.argv[1:4])
