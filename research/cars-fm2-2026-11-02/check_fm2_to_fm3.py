"""Validasi fm2_to_fm3 pada semua mobil disc FM2, dan terhadap FM3 untuk mobil yang ada di keduanya.

Hanya membaca. Untuk setiap mobil FM2: transkode, baca hasilnya dengan carbin_audit (FM3), lalu
bandingkan posisi, normal, UV dan indeks dengan decoder FM2. Untuk mobil yang juga ada di FM3
Disc 1: header hasil vs header FM3 asli (selain driver rig dan dua float akhir), dan untuk pasangan
vertex yang posisinya cocok unik, sumbu Z frame tangent dan nilai ambient hasil vs FM3 asli.
Dengan --helper, setiap hasil juga dikonversi ke FM4 (`carbin-cpu convert`) dan diaudit dengan
carbin_audit.audit_conversion, seperti mobil FM3.
Hasil: outputs/car-fm2-research-2026-11-02/fm2_to_fm3_check.json (diabaikan Git).
"""
from pathlib import Path
import argparse, collections, json, math, struct, subprocess, sys, tempfile, zipfile

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import survey_carbin as sv
from fm4_converter.fm2 import carbin as carbin_fm2, transcode as fm2_to_fm3
from fm4_converter.archives import forza_zip
from fm4_converter.fm3 import carbin_audit
from fm4_converter.paths import PROJECT_ROOT

OUT = PROJECT_ROOT / 'outputs/car-fm2-research-2026-11-02/fm2_to_fm3_check.json'


def same_geometry(model, fm3):
    """Posisi (m), sudut normal (derajat), UV, dan indeks hasil vs decoder FM2.

    Vertex yang posisinya non-finite di FM2 (dipindah oleh fm2_to_fm3.repair) hanya dihitung.
    """
    worst = dict(position=0.0, normal=0.0, uv=0.0, nonfinite_source_vertices=0)
    if [s.name for s in model.sections] != [s['name'] for s in fm3['sections']]:
        raise AssertionError('section order changed')
    for s2, s3 in zip(model.sections, fm3['sections']):
        pool = model.glass if s2.buffer == 'glass' else model.body
        positions = carbin_audit.positions(s3, s3['lod'], 'FM3')
        for k, i in enumerate(range(s2.base, s2.base + s3['lod']['count'])):
            v = pool[i]
            p = [v[0][j] + s2.origin[j] for j in range(3)]
            if not all(math.isfinite(c) for c in p):
                worst['nonfinite_source_vertices'] += 1
                continue
            worst['position'] = max(worst['position'], math.dist(p, positions[k]))
            n2 = carbin_fm2.unpack_normal(v[3])
            n3 = carbin_audit.normal3(s3['lod'], k)
            l2 = math.sqrt(sum(t * t for t in n2))
            if l2 > 1e-9:
                dot = sum(a * b for a, b in zip(n2, n3)) / l2
                worst['normal'] = max(worst['normal'], math.degrees(math.acos(max(-1, min(1, dot)))))
            uv3 = struct.unpack_from('>2e', s3['lod']['data'], k * 40 + 8)
            worst['uv'] = max(worst['uv'], max(abs(a - b) for a, b in zip(v[1], uv3)))
        if len(s2.subsections) != len(s3['meshes']):
            raise AssertionError(f'{s2.name}: mesh count changed')
        for sub, mesh in zip(s2.subsections, s3['meshes']):
            local = [i - s2.base for i in sub.indices if i >= 0]
            got = list(carbin_audit.index_values(mesh))
            if (sub.name, sub.lod, sub.index_type) != (mesh['name'], mesh['lod'], mesh['primitive']) or local != got:
                raise AssertionError(f'{s2.name}/{sub.name}: mesh changed')
    return worst


def header_check(ours, real):
    """Header hasil vs FM3 asli: struktur sama (selain record, driver rig dan dua float akhir), lalu isi."""
    a, b = ours['header'], real['header']
    if len(a) != len(b):
        return dict(same_length=False)
    records = struct.unpack_from('>I', a, 0x110)[0]
    rig = 0x114 + records * 140
    end = len(a) - 16
    mask = lambda h: h[0x104:0x114] + h[rig:rig + 4] + h[rig + 0x64:end] + h[end + 8:]
    return dict(same_length=True, same_structure=mask(a) == mask(b),
                same_records=a[0x114:rig] == b[0x114:rig], same_rig=a[rig + 4:rig + 0x64] == b[rig + 4:rig + 0x64])


def lenient_positions(section):
    """Posisi FM3 seperti carbin_audit.positions, tetapi vertex non-finite (ada di FM3 asli) jadi None."""
    b, pool = section['bounds'], section['lod']
    centre = [b[j] + (b[j + 3] + b[j + 6]) / 2 for j in range(3)]
    out = []
    for i in range(pool['count']):
        x, y, z, w = struct.unpack_from('>4e', pool['data'], i * pool['stride'])
        p = tuple(centre[j] + c * w for j, c in enumerate((x, y, z)))
        out.append(p if all(math.isfinite(c) for c in p) else None)
    return out


def frame_pairs(ours, real):
    """Dot sumbu Z tangent dan selisih ambient pada pasangan vertex dengan posisi unik yang sama."""
    names = {s['name']: s for s in real['sections']}
    dots, ambient = [], []
    for s in ours['sections']:
        t = names.get(s['name'])
        if t is None or t['lod']['stride'] != 40:
            continue
        a = sv.fm3_vertices(s, 1)
        b = sv.fm3_vertices(t, 1)
        index_a = {sv.key(p): i for i, p in enumerate(carbin_audit.positions(s, s['lod'], 'FM3'))}
        index_b = {sv.key(p): i for i, p in enumerate(lenient_positions(t)) if p is not None}
        for k in a:
            if len(a[k]) != 1 or len(b.get(k, ())) != 1 or k not in index_a or k not in index_b:
                continue
            i, j = index_a[k], index_b[k]
            za = np.array(carbin_fm2.unpack_normal(struct.unpack_from('>I', s['lod']['data'], i * 40 + 36)[0]))
            zb = np.array(carbin_fm2.unpack_normal(struct.unpack_from('>I', t['lod']['data'], j * 40 + 36)[0]))
            la, lb = np.linalg.norm(za), np.linalg.norm(zb)
            if la > 1e-6 and lb > 1e-6:
                dots.append(float(za @ zb / la / lb))
            va = np.array(struct.unpack_from('>4h', s['lod']['data'], i * 40 + 20))
            vb = np.array(struct.unpack_from('>4h', t['lod']['data'], j * 40 + 20))
            ambient.append(np.abs(va - vb) / 32767)
    return dots, ambient


def to_fm4(helper, fm3):
    """`carbin-cpu convert` lalu audit_conversion; ringkasan audit."""
    with tempfile.TemporaryDirectory() as tmp:
        source, target = Path(tmp) / 'in.carbin', Path(tmp) / 'out.carbin'
        source.write_bytes(fm3)
        result = subprocess.run([str(helper), 'convert', str(source), str(target)], capture_output=True, text=True)
        if result.returncode:
            raise AssertionError(f'helper: {result.stderr.strip()}')
        audit = carbin_audit.audit_conversion(fm3, target.read_bytes())
    return {k: audit[k] for k in ('passed', 'position_error_m', 'normal_error_degrees', 'uv_error')}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, default=OUT)
    p.add_argument('--limit', type=int)
    p.add_argument('--helper', type=Path, help='carbin-cpu.exe; tanpa ini konversi FM4 dilewati')
    a = p.parse_args()
    fm3 = sv.zips(sv.FM3)
    cars, failures, headers = {}, {}, collections.Counter()
    dots, ambient = [], []
    for name, path in sorted(sv.zips(sv.FM2).items())[:a.limit]:
        with zipfile.ZipFile(path) as z:
            data = z.read(next(i.filename for i in z.infolist() if i.filename.lower().endswith('.carbin')))
        try:
            out, summary = fm2_to_fm3.convert(data)
            ours = carbin_audit.parse(out, 'FM3')
            summary['worst'] = same_geometry(carbin_fm2.parse(data), ours)
            if a.helper:
                summary['fm4'] = to_fm4(a.helper, out)
        except (carbin_fm2.FormatError, carbin_audit.FormatError, AssertionError) as e:
            failures[name] = f'{type(e).__name__}: {e}'
            continue
        if name in fm3:
            with zipfile.ZipFile(fm3[name]) as z:
                main_name = next(i.filename for i in z.infolist() if i.filename.lower() == name + '.carbin')
                real = carbin_audit.parse(forza_zip.read(z, main_name), 'FM3')
            summary['header'] = header_check(ours, real)
            headers.update(k for k, v in summary['header'].items() if v)
            d, m = frame_pairs(ours, real)
            dots += d
            ambient += m
        cars[name] = summary
    worst = lambda k: max(c['worst'][k] for c in cars.values())
    amb = np.array(ambient) if ambient else np.zeros((0, 4))
    result = dict(
        cars=len(cars), failures=failures,
        fm4_audit_passed=sum(c.get('fm4', {}).get('passed', False) for c in cars.values()) if a.helper else None,
        fm4_worst_position_m=max((c['fm4']['position_error_m'] for c in cars.values()), default=None) if a.helper else None,
        worst_position_m=worst('position'), worst_normal_deg=worst('normal'), worst_uv=worst('uv'),
        moved_vertices={n: c['moved_vertices'] for n, c in cars.items() if c['moved_vertices']},
        fm3_header_checks=dict(cars=sum('header' in c for c in cars.values()), **headers),
        tangent_z_pairs=len(dots),
        tangent_z_dot=dict(median=float(np.median(dots)), p10=float(np.percentile(dots, 10)),
                           above_0_9=float(np.mean(np.array(dots) > 0.9))) if dots else None,
        ambient_abs_diff=dict(median=np.median(amb, 0).round(4).tolist(),
                              p90=np.percentile(amb, 90, 0).round(4).tolist()) if len(amb) else None)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(dict(summary=result, cars=cars), indent=1), encoding='utf-8')
    json.dump(result, sys.stdout, indent=1)
    print()


if __name__ == '__main__':
    main()
