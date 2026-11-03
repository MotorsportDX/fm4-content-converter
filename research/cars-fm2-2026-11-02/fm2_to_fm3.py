"""Prototipe: .carbin FM2 -> .carbin berbentuk FM3, untuk konverter FM3 -> FM4. Bodi mobil (FM2 type 2
-> FM3 type 1) dan velg (FM2 type 1 -> FM3 type 2).

FM2 dan FM3 memakai struktur yang sama kecuali hal-hal di bawah (diukur pada 146 mobil yang ada
di kedua game, lihat REPORT.md bagian 7). File hasilnya dibaca oleh carbin_audit (FM3) dan oleh
helper ForzaEditor, lalu `carbin-cpu convert` membuat model FM4 dengan jalur yang sama seperti
mobil FM3. Hanya membaca FM2; tidak ada data FM3 yang disalin selain konstanta struktural.

- header: FM2 [0x104] = 0x2CA, 1, N, N record 140 byte (sama dengan FM3), lalu 0x6C byte: word 1,
  24 float driver rig, (4, 4). FM3 [0x104] = 0xD, 0xB, 1, N, record, lalu 0x1AC byte: word 3, driver
  rig, 0xA8 byte konstan, 4 gauge frame netral (9 float), dua float x, y = -2x, (4, 4). Velg: FM2
  [0] = 1, 0x2CA, 1, N tanpa blok 0x100 byte; FM3 [0] = 2, 20 byte nol, lalu blok format yang sama
  (172 velg di kedua game). Velg FM2 hanya punya buffer kaca; buffer bodi kosong;
- section: marker 0x2C9 -> 2; FM2 punya word rentang vertex (first, last u16) di depan vbTest dan
  satu word ekstra setelah PostName; vertex ada di dua buffer bersama (kaca/bodi) di akhir file,
  FM3 menyimpan buffer LOD per section;
- subsection: FM2 8 byte di depan nama dan urutan (tipe indeks, LOD); FM3 9 byte, (LOD, tipe),
  56 byte konstan setelahnya dan 4 byte nol di akhir;
- vertex 60 -> 40 byte: posisi dan normal disalin; UV fixed-point u16 -> half; 4 nilai ambient
  S16 FM3 = 4 S16 pertama FM2 (offset 28) x AMBIENT_SCALE; word damage dan word berikutnya dari
  offset 20 dan 24; sumbu Z frame tangent (FM2 tidak menyimpannya) = -dP/dv dari UV segitiga.

Empat mobil disc FM2 punya section 3-6 vertex dengan posisi NaN (w = 0x7FFF) dan bounds +-1.7e38;
section seperti itu diciutkan ke satu titik (lihat repair) agar draw list tetap utuh.
"""
from pathlib import Path
import argparse, struct, sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import carbin_fm2

FM3_TYPE_CAR, FM3_TYPE_WHEEL = 1, 2
FM2_TYPE_CAR, FM2_TYPE_WHEEL = 2, 1
FM3_FORMAT = (0xD, 0xB)
RIG_WORD = 3                      # FM3/FM4 main; FM2 menyimpan 1
FM3_STRIDE = 40
# 0xA8 byte setelah driver rig: konstan pada semua mobil disc FM3 (survei 200 mobil).
AFTER_RIG = struct.pack('>42I', *([0] * 30 + [0x3F800000] + [0] * 9 + [1, 5]))
NEUTRAL_FRAME = struct.pack('>9f', 0, 0, 0, 0, 0, 1, 0, 0, 1)
# Dua float akhir header (x, y = -2x; arti belum diketahui). Median 200 mobil disc FM3.
END_FLOATS = (-0.33879199624061584, 0.6790955066680908)
# Velg FM3: 270 dari 389 header identik sampai dua float akhir. Rig velg FM2 semuanya nol; rig velg
# FM3 hanya berisi 1.0 di float ke-7, dan word ke-41 blok setelah rig 0 (mobil 1). Float akhir = median.
WHEEL_RIG = struct.pack('>24f', *([0] * 6 + [1] + [0] * 17))
WHEEL_AFTER_RIG = struct.pack('>42I', *([0] * 30 + [0x3F800000] + [0] * 9 + [0, 5]))
WHEEL_END_FLOATS = (-0.32778599858283997, 0.6643739938735962)
SUB_PRE9 = bytes.fromhex('000000020000000002')
SUB_FIXED56 = bytes.fromhex('00000000000000010000000000000000000000000000'
                            '00003f8000003f8000003f8000003f80000000000000'
                            '000000003f8000003f800000')
TRAILER = bytes.fromhex('000000010000000000000001000000000000000100000000')
# FM3 ambient S16 ~ FM2 S16 x 1.48 (median rasio 1.47-1.49 pada 39031 pasangan vertex 4 mobil,
# korelasi 0.96-0.99; FM3 dipanggang ulang, jadi bukan padanan persis).
AMBIENT_SCALE = 1.48
# Panjang minimum sumbu Z tangent setelah diproyeksikan ke bidang normal (lihat frame_z).
MIN_FRAME_AXIS = 0.1


class FormatError(carbin_fm2.FormatError):
    pass


def u32(v):
    return struct.pack('>I', v)


def raw_section(data, offset):
    """Field mentah satu section FM2 yang tidak disimpan decoder (urutan carbin_fm2.section_head)."""
    r = carbin_fm2.Reader(data)
    r.pos = offset
    out = {}
    marker = r.u32()
    if marker not in carbin_fm2.SECTION_MARKERS:
        raise FormatError(f'section at 0x{offset:x} without marker')
    out['bounds'] = r.f32s(9)
    out['unk1c'] = data[r.pos:r.pos + 0x1C]
    r.skip(0x1C)
    start = r.pos
    r.counted_skip(0x10)
    out['shards'] = data[start:r.pos]                 # count + 16-byte vertices (pecahan kaca)
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
    out['post'] = data[r.pos:r.pos + 8]               # 2 (PostName FM3), 1
    r.skip(8)
    if (r.i32(), r.u32()) != (0, carbin_fm2.VERTEX_SIZE):
        raise FormatError(f'{out["name"]}: section with its own vertices')
    out['after_lod'] = data[r.pos:r.pos + 4]
    r.skip(4)
    return out


def raw_indices(data, sub):
    """Indeks mentah (lokal section, restart utuh) tepat seperti di file FM2."""
    r = carbin_fm2.Reader(data)
    r.pos = sub.offset + 8
    r.skip(r.i32() + 12)
    count, size = r.i32(), r.i32()
    return count, size, data[r.pos:r.pos + count * size]


def header(data, model):
    """Header FM3 dari header FM2: prefix, format FM3, record, driver rig, konstanta."""
    block = 0x104 if model.type_id == FM2_TYPE_CAR else 4
    if model.type_id not in (FM2_TYPE_CAR, FM2_TYPE_WHEEL) or             struct.unpack_from('>2I', data, block) != (carbin_fm2.FM2_MARKER, 1):
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
    """Vektor (n, 3) -> word 11:11:10 bertanda (kebalikan carbin_fm2.unpack_normal)."""
    x = np.clip(np.round(v[:, 0] * 1023), -1023, 1023).astype(np.int64) & 0x7FF
    y = np.clip(np.round(v[:, 1] * 1023), -1023, 1023).astype(np.int64) & 0x7FF
    z = np.clip(np.round(v[:, 2] * 511), -511, 511).astype(np.int64) & 0x3FF
    return (x | (y << 11) | (z << 22)).astype('>u4')


def repair(pool, bounds, name):
    """Vertex dengan posisi non-finite dipindah ke origin section (xyz = w = 0).

    Bounds yang rusak (non-finite atau |nilai| > 1e30) hanya diterima bila semua vertex section
    juga rusak; section itu menjadi satu titik di origin yang masih finite, bounds +-1 mm.
    Mengembalikan (vertex, bounds, jumlah vertex yang dipindah).
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
    """Sumbu Z frame tangent FM3 (= -dP/dv) per vertex section, dari segitiga semua LOD-nya."""
    pos = raw[:, 0:8].copy().view('>f2').astype(np.float64).reshape(-1, 4)
    p = pos[:, :3] * pos[:, 3:4]
    uv = (raw[:, 8:12].copy().view('>u2').astype(np.float64).reshape(-1, 2) - 32768) / 1310.72
    acc = np.zeros((len(raw), 3))
    for sub in section.subsections:
        faces = np.array(carbin_fm2.faces(sub), dtype=np.int64).reshape(-1, 3) - local
        if not len(faces):
            continue
        e1, e2 = p[faces[:, 1]] - p[faces[:, 0]], p[faces[:, 2]] - p[faces[:, 0]]
        d1, d2 = uv[faces[:, 1]] - uv[faces[:, 0]], uv[faces[:, 2]] - uv[faces[:, 0]]
        det = d1[:, 0] * d2[:, 1] - d2[:, 0] * d1[:, 1]
        ok = np.abs(det) >= 1e-12
        b = (e2[ok] * d1[ok, :1] - e1[ok] * d2[ok, :1]) / det[ok, None]
        for k in range(3):
            np.add.at(acc, faces[ok, k], b)
    # Di bidang normal, seperti FM3. Bila -dP/dv (hampir) sejajar normal, nol: frame quaternion FM4
    # dari sumbu sependek itu tidak stabil (normal bergeser sampai 0,8 derajat), dan writer FM4
    # memakai sumbu bawaannya untuk sumbu nol.
    normal = np.array([carbin_fm2.unpack_normal(int(w)) for w in raw[:, 16:20].copy().view('>u4').ravel()])
    normal /= np.maximum(np.linalg.norm(normal, axis=1), 1e-12)[:, None]
    length = np.linalg.norm(acc, axis=1)
    z = np.where(length[:, None] > 1e-12, -acc / np.maximum(length, 1e-300)[:, None], 0.0)
    z -= normal * np.sum(z * normal, axis=1)[:, None]
    length = np.linalg.norm(z, axis=1)
    z = np.where(length[:, None] > MIN_FRAME_AXIS, z / np.maximum(length, 1e-300)[:, None], 0.0)
    return pack111110(z)


def vertices(raw, section, local):
    """Vertex FM2 60 byte (array (n, 60) uint8) -> FM3 40 byte."""
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
    """Bytes .carbin FM2 (mobil atau velg) -> bytes .carbin FM3 dan ringkasan."""
    model = carbin_fm2.parse(data)
    head, lists_at = header(data, model)
    # Draw list, word sebelum section dan jumlah section disalin apa adanya.
    first_section = model.sections[0].offset
    out = [head, data[lists_at:first_section]]
    # Lokasi data dua buffer bersama (urutan carbin_fm2.parse).
    buffers = {}
    r = carbin_fm2.Reader(data)
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
            raise FormatError(f'{section.name}: range starts at {first}, decoder base {section.base}')
        pool = buffers[section.buffer]
        if last >= len(pool) or last < first:
            raise FormatError(f'{section.name}: range {first}..{last} outside {section.buffer} buffer')
        bmin, bmax = raw['bounds'][3:6], raw['bounds'][6:9]
        if any(abs(a + b) > 1e-6 for a, b in zip(bmin, bmax)):
            # FM3 menambahkan pusat bounds ke posisi, FM2 tidak; semua mobil disc FM2 simetris.
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
    p.add_argument('source', type=Path, help='.carbin FM2')
    p.add_argument('target', type=Path, help='.carbin FM3 baru (tidak menimpa)')
    a = p.parse_args()
    data, summary = convert(a.source.read_bytes())
    with open(a.target, 'xb') as f:
        f.write(data)
    print(summary)


if __name__ == '__main__':
    main()
