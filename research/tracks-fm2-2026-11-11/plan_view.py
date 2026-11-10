"""Gambar tampak atas semua segitiga model track FM2 (cek decode posisi, indeks dan draw).

Setiap draw (op 1) memakai buffer indeksnya dari tabel resource; buffer vertex-nya adalah VB yang
berakhir tepat sebelum buffer indeks itu atau VB pertama (dugaan yang dicek gambar ini). Posisi
adalah float3 di awal setiap vertex (stride dari `vfetch` shader).

    python research/tracks-fm2-2026-11-11/plan_view.py <bin.zip> <out.png>
"""
import struct
import sys
import zipfile

import numpy as np
from PIL import Image, ImageDraw

from fm2_model import Model
from fm4_converter.fm3.integration import archive_read


def stride_of(model):
    code = b"".join(b for s, c, b in model.chunks if s == ".gpu")
    found = set()
    for o in range(0, len(code) - 12, 4):
        w0, w1, w2 = struct.unpack_from(">3I", code, o)
        if w0 & 31 == 0 and (w0 >> 19) & 1 and (w1 >> 16) & 63 == 57 and (w2 >> 8) & 0x7FFFFF == 0:
            found.add((w2 & 255) * 4)
    return found


def extent(gpu, vb, stride, idx):
    """The largest side of the box of the vertices idx names; infinite when they are not floats."""
    n = vb[2] // stride
    pos = np.frombuffer(gpu, np.uint8, n * stride, vb[1]).reshape(n, stride)[:, :12].copy().view(">f4")
    pos = pos.reshape(n, 3)[idx]
    return float(np.ptp(pos, axis=0).max()) if np.isfinite(pos).all() else float("inf")


def triangles(model):
    vbs, ibs = model.resources()
    gpu = model.chunk(".gpu", 1)
    strides = stride_of(model)
    out = []
    for _, op, body in model.program()[1]:
        if op != 1:
            continue
        prim, count, obj = body
        ib = next(i for i in ibs if i[0] == obj)
        idx = np.frombuffer(gpu, ">u2", count, ib[1]).astype(np.int64)
        vb = model.vertex_buffer(ib[1])
        fits = [s for s in sorted(strides) if s and vb[2] % s == 0 and idx.max() < vb[2] // s]
        if not fits:
            continue
        stride = min(fits, key=lambda s: extent(gpu, vb, s, idx))
        n = vb[2] // stride
        raw = np.frombuffer(gpu, np.uint8, n * stride, vb[1]).reshape(n, stride)
        pos = raw[:, :12].copy().view(">f4").reshape(n, 3)
        if prim == 4:
            tris = idx[:count // 3 * 3].reshape(-1, 3)
        else:
            continue
        out.append(pos[tris])
    return out


def main(path, png, size=2048):
    tris = []
    z = zipfile.ZipFile(path)
    for info in z.infolist():
        if info.filename.lower().endswith(".rmb.bin") and ".pre_" not in info.filename and ".sky." not in info.filename:
            try:
                tris += triangles(Model(archive_read(z, info)))
            except (ValueError, StopIteration):
                pass
    allt = np.concatenate(tris)
    allt = allt[np.isfinite(allt).all(axis=(1, 2)) & (np.abs(allt) < 1e5).all(axis=(1, 2))]
    xz = allt[:, :, [0, 2]].reshape(-1, 2)
    lo, hi = np.percentile(xz, 0.5, axis=0), np.percentile(xz, 99.5, axis=0)
    scale = (size - 1) / (hi - lo).max()
    img = Image.new("RGB", (size, size), (20, 20, 20))
    draw = ImageDraw.Draw(img)
    for t in allt[::1]:
        p = [tuple(((v[[0, 2]] - lo) * scale).tolist()) for v in t]
        draw.polygon(p, outline=(200, 200, 200))
    img.save(png)
    print(len(allt), "triangles", lo, hi)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
