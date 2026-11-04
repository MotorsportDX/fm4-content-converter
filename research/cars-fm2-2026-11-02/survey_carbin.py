"""Survei decoder .carbin FM2 ke semua mobil disc FM2, plus pembanding vertex FM3.

Hanya membaca. Untuk mobil yang juga punya ZIP di FM3 Disc 1, LOD1 hasil decode FM2
dibandingkan dengan LOD1 bodi FM3 yang dibaca carbin_audit project: bounding box, lalu UV0,
normal dan word sisa vertex pada pasangan vertex yang posisinya cocok secara unik.
Hasil: outputs/car-fm2-research-2026-11-02/carbin_survey.json (diabaikan Git).
"""
from pathlib import Path
import argparse, collections, json, math, struct, sys, zipfile

from fm4_converter.fm2 import carbin as carbin_fm2
from fm4_converter.archives import forza_zip
from fm4_converter.fm3 import carbin_audit
from fm4_converter.paths import PROJECT_ROOT

FM2 = Path(r'D:\Data\FM2\USA\Forza Motorsport 2 (USA)\Media\cars')
FM3 = Path(r'D:\Data\FM3\USA\Forza Motorsport 3 (USA) (Disc 1) (Play Disc)\Media\cars')
OUT = PROJECT_ROOT / 'outputs/car-fm2-research-2026-11-02/carbin_survey.json'
UV_STEP = 1 / 1310.72


def zips(root):
    return {p.stem.casefold(): p for p in root.glob('*.zip')}


def key(point):
    return tuple(round(v, 4) for v in point)


def fm2_vertices(model, section, lod, material=None):
    """{posisi: set(vertex)} untuk subsection LOD tsb; posisi = xyz*w + origin section."""
    pool = model.glass if section.buffer == 'glass' else model.body
    out = collections.defaultdict(set)
    for sub in section.subsections:
        if sub.lod == lod and material in (None, sub.name):
            for i in sub.indices:
                if i >= 0:
                    v = pool[i]
                    out[key(v[0][j] + section.origin[j] for j in range(3))].add((v[1], v[3], v[4]))
    return out


def fm3_vertices(section, lod, material=None):
    """Sama untuk FM3; hanya vertex yang dirujuk, karena ada pool FM3 dengan vertex non-finite."""
    pool = section['lod0'] if lod == 0 else section['lod']
    b = section['bounds']
    center = [b[j] + (b[j + 3] + b[j + 6]) / 2 for j in range(3)]
    out = collections.defaultdict(set)
    for mesh in section['meshes']:
        if mesh['lod'] != lod or material not in (None, mesh['name']):
            continue
        for i in carbin_audit.index_values(mesh):
            o = i * pool['stride']
            x, y, z, w, u, v = struct.unpack_from('>6e', pool['data'], o)
            raw = pool['data'][o:o + pool['stride']] if pool['stride'] == 40 else None
            normal = tuple(carbin_audit.normal3(pool, i))
            out[key(center[j] + c * w for j, c in enumerate((x, y, z)))].add(((u, v), normal, raw))
    return out


def box(points):
    return [min(p[j] for p in points) for j in range(3)], [max(p[j] for p in points) for j in range(3)]


def quantiles(values):
    if not values:
        return None
    v = sorted(values)
    return dict(n=len(v), median=v[len(v) // 2], p90=v[int(.9 * len(v))], p99=v[int(.99 * len(v))], max=v[-1])


def compare(model, fm3):
    """Bounding box LOD1 seluruh mobil, lalu pasangan vertex unik per section+material."""
    a = [p for s in model.sections for p in fm2_vertices(model, s, 1)]
    b = [p for s in fm3['sections'] for p in fm3_vertices(s, 1)]
    (a0, a1), (b0, b1) = box(a), box(b)
    names3 = {s['name']: s for s in fm3['sections']}
    uv, angle, tail = [], [], collections.Counter()
    pairs = 0
    for s in model.sections:
        s3 = names3.get(s.name)
        if s3 is None:
            continue
        for material in {sub.name for sub in s.subsections if sub.lod == 1}:
            left, right = fm2_vertices(model, s, 1, material), fm3_vertices(s3, 1, material)
            for k, got in left.items():
                ref = right.get(k, ())
                if len(got) != 1 or len(ref) != 1:
                    continue
                (uv2, n2, t2), (uv3, n3, raw3) = next(iter(got)), next(iter(ref))
                pairs += 1
                uv.append(max(abs(uv2[0] - uv3[0]), abs(uv2[1] - uv3[1])))
                n2 = carbin_fm2.unpack_normal(n2)
                l2 = math.sqrt(sum(t * t for t in n2))
                if l2 > 1e-9:
                    dot = sum(p * q for p, q in zip(n2, n3)) / l2
                    angle.append(math.degrees(math.acos(max(-1.0, min(1.0, dot)))))
                if raw3 is not None:
                    for o3 in (20, 24, 28, 32, 36):
                        for o2 in range(0, 40, 4):
                            word = raw3[o3:o3 + 4]
                            if word != b'\0\0\0\0' and t2[o2:o2 + 4] == word:
                                tail[f'fm3@{o3}=fm2@{20 + o2}'] += 1
    return dict(fm2_min=a0, fm2_max=a1, fm3_min=b0, fm3_max=b1,
                bbox_diff_m={'min_y': b0[1] - a0[1],
                             'other_max': max(abs(x - y) for j, (x, y) in enumerate(zip(a0 + a1, b0 + b1)) if j != 1)},
                fm3_extra_sections=sorted(set(names3) - {s.name for s in model.sections}),
                pairs=pairs, uv_abs_diff=quantiles(uv),
                uv_within_two_steps=sum(d <= 2 * UV_STEP for d in uv),
                normal_angle_deg=quantiles(angle), tail_word_matches=dict(tail.most_common(6)))


def survey_car(path):
    with zipfile.ZipFile(path) as z:
        name = next(i.filename for i in z.infolist() if i.filename.lower().endswith('.carbin'))
        data = z.read(name)
    m = carbin_fm2.parse(data)
    subs = [sub for s in m.sections for sub in s.subsections]
    verts = m.glass + m.body
    return m, dict(
        carbin=name, bytes=len(data), type=m.type_id, sections=len(m.sections),
        subsections=len(subs), glass_vertices=len(m.glass), body_vertices=len(m.body),
        trailing_bytes=m.size - m.end, trailing=data[m.end:].hex(),
        section_markers=dict(collections.Counter(str(s.marker) for s in m.sections)),
        buffers=dict(collections.Counter(s.buffer for s in m.sections)),
        lods=dict(collections.Counter(str(sub.lod) for sub in subs)),
        index=dict(collections.Counter(f'{sub.index_type}/{sub.index_size}' for sub in subs)),
        triangles={str(l): sum(len(carbin_fm2.faces(sub)) for sub in subs if sub.lod == l)
                   for l in sorted({sub.lod for sub in subs})},
        uv0_range=[min(min(v[1]) for v in verts), max(max(v[1]) for v in verts)] if verts else None,
        uv1_nonzero=sum(v[2] != (-25.0, -25.0) and v[2] != (0.0, 0.0) for v in verts),
        section_names=[s.name for s in m.sections],
        materials=sorted({sub.name for sub in subs}))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, default=OUT)
    a = p.parse_args()
    fm3 = zips(FM3)
    cars, failures, compared = {}, {}, {}
    for name, path in sorted(zips(FM2).items()):
        try:
            model, cars[name] = survey_car(path)
        except carbin_fm2.FormatError as e:
            failures[name] = str(e)
            continue
        if name in fm3:
            with zipfile.ZipFile(fm3[name]) as z:
                main_name = next(i.filename for i in z.infolist() if i.filename.lower() == name + '.carbin')
                compared[name] = compare(model, carbin_audit.parse(forza_zip.read(z, main_name), 'FM3'))
    total = lambda field: dict(sum((collections.Counter(c[field]) for c in cars.values()), collections.Counter()))
    pick = lambda f: [f(v) for v in compared.values()]
    summary = dict(
        cars=len(cars), failures=failures,
        trailing_bytes=dict(collections.Counter(str(c['trailing_bytes']) for c in cars.values())),
        trailing_values=dict(collections.Counter(c['trailing'] for c in cars.values()).most_common(5)),
        section_markers=total('section_markers'), lods=total('lods'), index=total('index'),
        sections_range=[min(c['sections'] for c in cars.values()), max(c['sections'] for c in cars.values())],
        lod1_triangles_range=[min(c['triangles'].get('1', 0) for c in cars.values()),
                              max(c['triangles'].get('1', 0) for c in cars.values())],
        uv0_range=[min(c['uv0_range'][0] for c in cars.values()), max(c['uv0_range'][1] for c in cars.values())],
        cars_with_uv1=sum(c['uv1_nonzero'] > 0 for c in cars.values()),
        fm3_compared=len(compared),
        bbox_min_y_diff_m=quantiles(pick(lambda v: v['bbox_diff_m']['min_y'])),
        bbox_other_diff_m=quantiles(pick(lambda v: v['bbox_diff_m']['other_max'])),
        fm3_extra_sections=dict(collections.Counter(s for v in compared.values() for s in v['fm3_extra_sections']).most_common(8)),
        vertex_pairs=sum(pick(lambda v: v['pairs'])),
        uv_within_two_steps=sum(pick(lambda v: v['uv_within_two_steps'])),
        uv_median_diff_per_car=quantiles([v['uv_abs_diff']['median'] for v in compared.values() if v['uv_abs_diff']]),
        normal_p99_deg_per_car=quantiles([v['normal_angle_deg']['p99'] for v in compared.values() if v['normal_angle_deg']]),
        tail_word_matches=dict(sum((collections.Counter(v['tail_word_matches']) for v in compared.values()),
                                   collections.Counter()).most_common(6)))
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(dict(summary=summary, cars=cars, fm3=compared), indent=1), encoding='utf-8')
    json.dump(summary, sys.stdout, indent=1)
    print()


if __name__ == '__main__':
    main()
