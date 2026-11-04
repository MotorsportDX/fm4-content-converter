"""FM2 .carbin -> FM3-shaped .carbin for the FM3 -> FM4 model converter. Car bodies (FM2 type 2
-> FM3 type 1) and wheels (FM2 type 1 -> FM3 type 2).

FM2 and FM3 share their structure except for the points below (measured on the 146 cars both
games ship, REPORT.md section 7). carbin_audit (FM3) and the ForzaEditor helper read the result,
and `carbin-cpu convert` then builds the FM4 model along the same path as FM3 cars. Only FM2 is
read; no FM3 data is copied besides structural constants.

- header: FM2 [0x104] = 0x2CA, 1, N, N records of 140 bytes (as FM3), then 0x6C bytes: word 1,
  24 driver rig floats, (4, 4). FM3 [0x104] = 0xD, 0xB, 1, N, records, then 0x1AC bytes: word 3,
  driver rig, 0xA8 constant bytes, 4 neutral gauge frames (9 floats), two floats x, y = -2x, (4, 4).
  Wheels: FM2 [0] = 1, 0x2CA, 1, N without the 0x100-byte block; FM3 [0] = 2, 20 zero bytes, then
  the same format block (172 wheels in both games). FM2 wheels only fill the glass buffer;
- section: marker 0x2C9 -> 2; FM2 has a vertex range word (first, last u16) before vbTest and one
  extra word after PostName; vertices live in two shared buffers (glass/body) at the end of the
  file, FM3 stores a LOD buffer per section;
- subsection: FM2 has 8 bytes before the name and the order (index type, LOD); FM3 has 9 bytes,
  (LOD, type), 56 constant bytes after it and 4 zero bytes at the end;
- vertex 60 -> 40 bytes: position and normal copied; fixed-point u16 UV -> half; FM3's 4 S16
  ambient values = FM2's first 4 S16 (offset 28) x AMBIENT_SCALE; the damage word and the next
  word from offsets 20 and 24; the tangent frame Z axis (FM2 does not store it) = -dP/dv from the
  triangle UVs.

Four FM2 disc cars have sections of 3-6 vertices with NaN positions (w = 0x7FFF) and bounds of
+-1.7e38; such sections collapse to one point (see `repair`) so the draw lists stay intact.
"""
from pathlib import Path
import argparse, struct

import numpy as np

from . import carbin

FM3_TYPE_CAR, FM3_TYPE_WHEEL = 1, 2
FM2_TYPE_CAR, FM2_TYPE_WHEEL = 2, 1
FM3_FORMAT = (0xD, 0xB)
RIG_WORD = 3                      # FM3/FM4 main models; FM2 stores 1
FM3_STRIDE = 40
# 0xA8 bytes after the driver rig: constant on every FM3 disc car (survey of 200 cars).
AFTER_RIG = struct.pack('>42I', *([0] * 30 + [0x3F800000] + [0] * 9 + [1, 5]))
NEUTRAL_FRAME = struct.pack('>9f', 0, 0, 0, 0, 0, 1, 0, 0, 1)
# The header's two final floats (x, y = -2x; meaning unknown). Median of 200 FM3 disc cars.
END_FLOATS = (-0.33879199624061584, 0.6790955066680908)
# FM3 wheels: 270 of 389 headers are identical up to the two final floats. FM2 wheel rigs are all
# zero; FM3 wheel rigs only hold 1.0 in float 7, and word 41 of the after-rig block is 0 (cars: 1).
# Final floats = median.
WHEEL_RIG = struct.pack('>24f', *([0] * 6 + [1] + [0] * 17))
WHEEL_AFTER_RIG = struct.pack('>42I', *([0] * 30 + [0x3F800000] + [0] * 9 + [0, 5]))
WHEEL_END_FLOATS = (-0.32778599858283997, 0.6643739938735962)
SUB_PRE9 = bytes.fromhex('000000020000000002')
SUB_FIXED56 = bytes.fromhex('00000000000000010000000000000000000000000000'
                            '00003f8000003f8000003f8000003f80000000000000'
                            '000000003f8000003f800000')
TRAILER = bytes.fromhex('000000010000000000000001000000000000000100000000')
# FM3 ambient S16 ~ FM2 S16 x 1.48 (median ratio 1.47-1.49 over 39031 vertex pairs of 4 cars,
# correlation 0.96-0.99; FM3 was rebaked, so this is no exact equivalent).
AMBIENT_SCALE = 1.48
# Minimum length of the tangent Z axis after projection onto the normal plane (see frame_z).
MIN_FRAME_AXIS = 0.1


class FormatError(carbin.FormatError):
    pass


def u32(v):
    return struct.pack('>I', v)


def raw_section(data, offset):
    """Raw fields of one FM2 section that the reader does not keep (order of carbin.section_head)."""
    r = carbin.Reader(data)
    r.pos = offset
    out = {}
    marker = r.u32()
    if marker not in carbin.SECTION_MARKERS:
        raise FormatError(f'section at 0x{offset:x} without marker')
    out['bounds'] = r.f32s(9)
    out['unk1c'] = data[r.pos:r.pos + 0x1C]
    r.skip(0x1C)
    start = r.pos
    r.counted_skip(0x10)
    out['shards'] = data[start:r.pos]                 # count + 16-byte vertices (glass shards)
    out['after_shards'] = data[r.pos:r.pos + 4]
    r.skip(4)
    start = r.pos
    r.counted_skip(2)
    out['shard_indices'] = data[start:r.pos]
    first, last = struct.unpack_from('>2H', data, r.pos)
    out['range'] = (first, last)
    r.skip(4)
    out['vb'] = (r.u32(), r.u32())
    out['name'] = r.ascii(r.u8())
    out['post'] = data[r.pos:r.pos + 8]               # 2 (FM3 PostName), 1
    r.skip(8)
    if (r.i32(), r.u32()) != (0, carbin.VERTEX_SIZE):
        raise FormatError(f'{out["name"]}: section with its own vertices')
    out['after_lod'] = data[r.pos:r.pos + 4]
    r.skip(4)
    return out


def raw_indices(data, sub):
    """Raw indices (section-local, restarts intact) exactly as in the FM2 file."""
    r = carbin.Reader(data)
    r.pos = sub.offset + 8
    r.skip(r.i32() + 12)
    count, size = r.i32(), r.i32()
    return count, size, data[r.pos:r.pos + count * size]


def header(data, model):
    """FM3 header from the FM2 header: prefix, FM3 format, records, driver rig, constants."""
    block = 0x104 if model.type_id == FM2_TYPE_CAR else 4
    if model.type_id not in (FM2_TYPE_CAR, FM2_TYPE_WHEEL) or \
            struct.unpack_from('>2I', data, block) != (carbin.FM2_MARKER, 1):
        raise FormatError('unexpected FM2 format block')
    records = struct.unpack_from('>I', data, block + 8)[0]
    end = block + 12 + records * 140
    rig_word, = struct.unpack_from('>I', data, end)
    if rig_word != 1 or data[end + 0x64:end + 0x6C] != u32(4) + u32(4):
        raise FormatError('unexpected FM2 header tail')
    if model.type_id == FM2_TYPE_CAR:
        prefix, rig, after, ends = u32(FM3_TYPE_CAR) + data[4:0x104], data[end + 4:end + 0x64], AFTER_RIG, END_FLOATS
    else:
        if records or any(data[end + 4:end + 0x64]):
            raise FormatError('FM2 wheel with records or a driver rig')
        prefix, rig, after, ends = u32(FM3_TYPE_WHEEL) + bytes(20), WHEEL_RIG, WHEEL_AFTER_RIG, WHEEL_END_FLOATS
    out = (prefix + u32(FM3_FORMAT[0]) + u32(FM3_FORMAT[1]) + u32(1)
           + u32(records) + data[block + 12:end] + u32(RIG_WORD) + rig + after
           + NEUTRAL_FRAME * 4 + struct.pack('>2f', *ends) + u32(4) + u32(4))
    return out, end + 0x6C


def pack111110(v):
    """Vectors (n, 3) -> signed 11:11:10 words (inverse of carbin.unpack_normal)."""
    x = np.clip(np.round(v[:, 0] * 1023), -1023, 1023).astype(np.int64) & 0x7FF
    y = np.clip(np.round(v[:, 1] * 1023), -1023, 1023).astype(np.int64) & 0x7FF
    z = np.clip(np.round(v[:, 2] * 511), -511, 511).astype(np.int64) & 0x3FF
    return (x | (y << 11) | (z << 22)).astype('>u4')


def repair(pool, bounds, name):
    """Vertices with non-finite positions move to the section origin (xyz = w = 0).

    Broken bounds (non-finite or |value| > 1e30) are only accepted when every vertex of the
    section is broken too; that section becomes one point at its still-finite origin, bounds
    +-1 mm. Returns (vertices, bounds, number of vertices moved).
    """
    pos = pool[:, 0:8].copy().view('>f2').astype(np.float64).reshape(-1, 4)
    bad = ~np.all(np.isfinite(pos[:, :3] * pos[:, 3:4]), axis=1)
    broken = [not (np.isfinite(v) and abs(v) < 1e30) for v in bounds]
    if not bad.any() and not any(broken):
        return pool, bounds, 0
    if any(broken) and not bad.all():
        raise FormatError(f'{name}: broken bounds with finite vertices')
    pool = pool.copy()
    pool[bad, 0:8] = 0
    if any(broken):
        bounds = tuple(0.0 if broken[c] else bounds[c] for c in range(3)) + (-1e-3,) * 3 + (1e-3,) * 3
    return pool, bounds, int(bad.sum())


def frame_z(section, raw, local):
    """FM3 tangent frame Z axis (= -dP/dv) per section vertex, from the triangles of all its LODs."""
    pos = raw[:, 0:8].copy().view('>f2').astype(np.float64).reshape(-1, 4)
    p = pos[:, :3] * pos[:, 3:4]
    uv = (raw[:, 8:12].copy().view('>u2').astype(np.float64).reshape(-1, 2) - 32768) / 1310.72
    acc = np.zeros((len(raw), 3))
    for sub in section.subsections:
        faces = np.array(carbin.faces(sub), dtype=np.int64).reshape(-1, 3) - local
        if not len(faces):
            continue
        e1, e2 = p[faces[:, 1]] - p[faces[:, 0]], p[faces[:, 2]] - p[faces[:, 0]]
        d1, d2 = uv[faces[:, 1]] - uv[faces[:, 0]], uv[faces[:, 2]] - uv[faces[:, 0]]
        det = d1[:, 0] * d2[:, 1] - d2[:, 0] * d1[:, 1]
        ok = np.abs(det) >= 1e-12
        b = (e2[ok] * d1[ok, :1] - e1[ok] * d2[ok, :1]) / det[ok, None]
        for k in range(3):
            np.add.at(acc, faces[ok, k], b)
    # In the normal plane, as FM3. When -dP/dv is (nearly) parallel to the normal, zero: the FM4
    # quaternion frame of such a short axis is unstable (normals shift by up to 0.8 degrees), and
    # the FM4 writer uses its default axis for a zero axis.
    normal = np.array([carbin.unpack_normal(int(w)) for w in raw[:, 16:20].copy().view('>u4').ravel()])
    normal /= np.maximum(np.linalg.norm(normal, axis=1), 1e-12)[:, None]
    length = np.linalg.norm(acc, axis=1)
    z = np.where(length[:, None] > 1e-12, -acc / np.maximum(length, 1e-300)[:, None], 0.0)
    z -= normal * np.sum(z * normal, axis=1)[:, None]
    length = np.linalg.norm(z, axis=1)
    z = np.where(length[:, None] > MIN_FRAME_AXIS, z / np.maximum(length, 1e-300)[:, None], 0.0)
    return pack111110(z)


def vertices(raw, section, local):
    """FM2 60-byte vertices ((n, 60) uint8 array) -> FM3 40-byte vertices."""
    n = len(raw)
    out = np.zeros((n, FM3_STRIDE), dtype=np.uint8)
    out[:, 0:8] = raw[:, 0:8]
    uv = (raw[:, 8:12].copy().view('>u2').astype(np.float64) - 32768) / 1310.72
    out[:, 8:12] = uv.astype('>f2').view(np.uint8).reshape(n, 4)
    out[:, 12:16] = np.zeros((n, 2), dtype='>f2').view(np.uint8).reshape(n, 4)
    out[:, 16:20] = raw[:, 16:20]
    ambient = raw[:, 28:36].copy().view('>i2').astype(np.float64) * AMBIENT_SCALE
    out[:, 20:28] = np.clip(np.round(ambient), -32767, 32767).astype('>i2').view(np.uint8).reshape(n, 8)
    out[:, 28:36] = raw[:, 20:28]
    out[:, 36:40] = frame_z(section, raw, local).view(np.uint8).reshape(n, 4)
    return out


def convert(data):
    """FM2 .carbin bytes (car or wheel) -> FM3 .carbin bytes and a summary."""
    model = carbin.parse(data)
    head, lists_at = header(data, model)
    # Draw lists, the word before the sections and the section count are copied as they are.
    first_section = model.sections[0].offset
    out = [head, data[lists_at:first_section]]
    # Data of the two shared buffers (order of carbin.parse).
    buffers = {}
    r = carbin.Reader(data)
    r.pos = model.buffers_offset + 8
    count = r.i32()
    r.skip(8)
    buffers['glass'] = np.frombuffer(data, np.uint8, count * 60, r.pos).reshape(-1, 60)
    r.skip(count * 60 + 12)
    count = r.i32()
    if count:
        r.skip(8)
        buffers['body'] = np.frombuffer(data, np.uint8, count * 60, r.pos).reshape(-1, 60)
    else:
        buffers['body'] = np.zeros((0, 60), np.uint8)
    summary = dict(sections=0, vertices=0, subsections=0, moved_vertices={})
    for section in model.sections:
        raw = raw_section(data, section.offset)
        first, last = raw['range']
        if first != section.base:
            raise FormatError(f'{section.name}: range starts at {first}, reader base {section.base}')
        pool = buffers[section.buffer]
        if last >= len(pool) or last < first:
            raise FormatError(f'{section.name}: range {first}..{last} outside {section.buffer} buffer')
        bmin, bmax = raw['bounds'][3:6], raw['bounds'][6:9]
        if any(abs(a + b) > 1e-6 for a, b in zip(bmin, bmax)):
            # FM3 adds the bounds centre to positions, FM2 does not; every FM2 disc car is symmetric.
            raise FormatError(f'{section.name}: asymmetric bounds')
        part, bounds, moved = repair(pool[first:last + 1], raw['bounds'], section.name)
        if moved:
            summary['moved_vertices'][section.name] = moved
        verts = vertices(part, section, first)
        subs = []
        for sub in section.subsections:
            count, size, idx = raw_indices(data, sub)
            name = sub.name.encode('ascii')
            subs.append(SUB_PRE9 + u32(len(name)) + name + u32(sub.lod) + u32(sub.index_type) + SUB_FIXED56
                        + u32(3) + u32(count) + u32(size) + idx + u32(0))
        name = raw['name'].encode('ascii')
        out += [u32(2), struct.pack('>9f', *bounds), raw['unk1c'], raw['shards'], raw['after_shards'],
                raw['shard_indices'], u32(raw['vb'][0]), u32(raw['vb'][1]), bytes([len(name)]), name,
                raw['post'][:4], u32(len(verts)), u32(FM3_STRIDE), verts.tobytes(), raw['after_lod'],
                u32(len(subs)), *subs, u32(2), u32(0), u32(0)]
        summary['sections'] += 1
        summary['vertices'] += len(verts)
        summary['subsections'] += len(subs)
    out.append(TRAILER)
    result = b''.join(out)
    summary['bytes'] = len(result)
    return result, summary


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('source', type=Path, help='FM2 .carbin')
    p.add_argument('target', type=Path, help='new FM3 .carbin (never overwritten)')
    a = p.parse_args()
    data, summary = convert(a.source.read_bytes())
    with open(a.target, 'xb') as f:
        f.write(data)
    print(summary)


if __name__ == '__main__':
    main()
