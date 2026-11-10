"""Uji di game: satu model satu-mesh Tsukuba (FM4) dengan geometri satu draw model FM2.

Geometri FM2 (posisi dipusatkan di titik asal model, normal, UV) ditulis sebagai vertex 36 byte
FM4: posisi, normal, warna putih, UV0, UV1 (UV0 bila FM2 hanya punya satu), tangent dan binormal
dari UV. Command buffer, material dan tekstur model template tetap. `bin.zip` Tsukuba ditulis
ulang dengan member tersimpan (stored), member lain disalin isinya.

    python research/tracks-fm2-2026-11-11/probe_tsukuba.py <FM4 Tsukuba bin.zip> <template model>
        <FM2 bin.zip> <FM2 model> <draw> <out bin.zip>
"""
import struct
import sys
import zipfile

import numpy as np

from fm2_model import Model
from fm4_model import OneMesh
from plan_view import extent, stride_of
from fm4_converter.fm3.integration import archive_read


def pack101010(v):
    v = np.clip(np.asarray(v, dtype=np.float64), -1, 1)
    q = np.round(v * 511).astype(np.int64) & 0x3FF
    return (q[..., 0] | (q[..., 1] << 10) | (q[..., 2] << 20)).astype(np.uint32)


def unpack101010(w):
    w = np.asarray(w, dtype=np.int64)
    out = []
    for shift in (0, 10, 20):
        q = (w >> shift) & 0x3FF
        q = np.where(q >= 512, q - 1024, q)
        out.append(q / 511.0)
    return np.stack(out, -1)


def fm2_draw(model, number):
    """(positions, normals (packed), uv0, uv1, indices, primitive) of one FM2 draw."""
    draws = [b for _, op, b in model.program()[1] if op == 1]
    prim, count, obj = draws[number]
    vbs, ibs = model.resources()
    gpu = model.chunk(".gpu", 1)
    ib = next(i for i in ibs if i[0] == obj)
    idx = np.frombuffer(gpu, ">u2", count, ib[1]).astype(np.int64)
    vb = model.vertex_buffer(ib[1])
    fits = [s for s in sorted(stride_of(model)) if s and vb[2] % s == 0 and idx.max() < vb[2] // s]
    stride = min(fits, key=lambda s: extent(gpu, vb, s, idx))
    n = vb[2] // stride
    raw = np.frombuffer(gpu, np.uint8, n * stride, vb[1]).reshape(n, stride)
    used = np.unique(idx)
    remap = np.full(n, -1, np.int64)
    remap[used] = np.arange(len(used))
    raw = raw[used]
    pos = raw[:, :12].copy().view(">f4").reshape(-1, 3).astype(np.float64)
    words = raw.copy().view(">u4")
    normal = words[:, 3]
    uv0 = words[:, 4]
    uv1 = words[:, 5] if stride >= 24 else uv0
    return pos, normal, uv0, uv1, remap[idx], prim


def tangents(pos, normal, uv, tris):
    """Per-vertex tangent and binormal from the texture coordinates (unit, orthogonal to n)."""
    n = unpack101010(normal)
    u = np.stack([(uv >> 16) & 0xFFFF, uv & 0xFFFF], -1) / 65535.0
    t = np.zeros_like(pos)
    for a, b, c in tris:
        e1, e2 = pos[b] - pos[a], pos[c] - pos[a]
        d1, d2 = u[b] - u[a], u[c] - u[a]
        r = d1[0] * d2[1] - d2[0] * d1[1]
        if abs(r) < 1e-12:
            continue
        tan = (e1 * d2[1] - e2 * d1[1]) / r
        t[[a, b, c]] += tan
    t = t - n * (t * n).sum(-1, keepdims=True)
    length = np.linalg.norm(t, axis=-1, keepdims=True)
    fallback = np.cross(n, [0.0, 1.0, 0.0])
    fallback[np.linalg.norm(fallback, axis=-1) < 1e-6] = [1.0, 0.0, 0.0]
    t = np.where(length > 1e-9, t / np.maximum(length, 1e-12), fallback / np.linalg.norm(fallback, axis=-1, keepdims=True))
    b = np.cross(n, t)
    return t, b


def fm4_vertices(pos, normal, uv0, uv1, tris):
    t, b = tangents(pos, normal, uv0, tris)
    out = np.zeros((len(pos), 9), ">u4")
    out[:, 0:3] = pos.astype(">f4").view(">u4")
    out[:, 3] = normal
    out[:, 4] = 0xFFFFFFFF
    out[:, 5] = uv0
    out[:, 6] = uv1
    out[:, 7] = pack101010(t)
    out[:, 8] = pack101010(b)
    return out.tobytes()


def main(fm4_zip, template, fm2_zip, fm2_name, number, out_zip):
    fm4 = zipfile.ZipFile(fm4_zip)
    tpl = OneMesh(archive_read(fm4, template))
    pos, normal, uv0, uv1, idx, prim = fm2_draw(Model(archive_read(zipfile.ZipFile(fm2_zip), fm2_name)), int(number))
    centre = (pos.min(0) + pos.max(0)) / 2
    pos = (pos - centre) * float(__import__("os").environ.get("PROBE_SCALE", "1"))
    tris = idx[:len(idx) // 3 * 3].reshape(-1, 3)
    data = tpl.with_geometry(fm4_vertices(pos, normal, uv0, uv1, tris), idx.tolist(), prim,
                             (tuple(pos.min(0)), tuple(pos.max(0))))
    OneMesh(data)   # reads back
    with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_STORED) as out:
        for info in fm4.infolist():
            body = data if info.filename == template else archive_read(fm4, info)
            out.writestr(zipfile.ZipInfo(info.filename, (1980, 1, 1, 0, 0, 0)), body)
    print("wrote", out_zip, "vertices", len(pos), "indices", len(idx), "extent", pos.max(0) - pos.min(0))


if __name__ == "__main__":
    main(*sys.argv[1:7])
