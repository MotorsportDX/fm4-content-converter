"""Prototipe model FM4 untuk satu mobil FM2: <car>.carbin, <car>_lod0.carbin, <car>_cockpit.carbin, dan
velg stock-nya wheel/<velg>.carbin.

Alur: .carbin FM2 -> fm2_to_fm3 -> `carbin-cpu convert` (konverter FM3 -> FM4 yang dipakai untuk
mobil FM3) -> model utama FM4 (LOD 1-5). `carbin-cpu closeup` (CloseUpFromLod1 ForzaEditor) lalu
membuat _lod0 dan _cockpit dari LOD 1 model utama. Pembagian section mengikuti mobil disc FM4:
section kokpit (COCKPIT) masuk _cockpit, sisanya _lod0; game menggambar keduanya bersama di LOD 0.
Header kedua file close-up diambil dari file sejenis milik mobil FM4 donor (`--donor`), karena FM2
tidak punya header close-up; blok cermin kokpit dinolkan bila tidak ada mesh mirrorMiddle.
Material di _cockpit diganti menurut COCKPIT_MATERIALS: FM4 memetakan mesh kokpit LOD 0 ke teknik
`cockpit_<material>`, dan `cockpit_interior` tidak ada di efek FM4.

Audit: model utama dengan carbin_audit.audit_conversion (seperti mobil FM3); file close-up dibaca
carbin_audit (FM4), lalu setiap mesh LOD 0 dibandingkan segitiga demi segitiga (posisi, normal,
UV, word damage) dengan mesh LOD 1 yang sama di model utama. Tidak ada game yang dijalankan.

Velg: .carbin velg FM2 (type 1) -> fm2_to_fm3 (velg FM3 type 2) -> `carbin-cpu convert` (velg FM4
type 3, LOD 1-5, diaudit dengan audit_conversion) -> `carbin-cpu lod0` (Lod0FromLod1 ForzaEditor:
LOD 0 = salinan LOD 1 tanpa ban, seperti 441 dari 442 velg FM4). audit_wheel_lod0 membandingkan
LOD 1-5 sebelum dan sesudah, dan setiap mesh LOD 0 dengan mesh LOD 1 yang sama.
Hasil di --out (default outputs/car-fm2-prototype-2026-11-03/<car>, diabaikan Git).
"""
from pathlib import Path
import argparse, collections, hashlib, json, math, sqlite3, struct, subprocess, sys, zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fm2_to_fm3, survey_carbin as sv
from fm4_converter.archives import forza_zip
from fm4_converter.fm3 import carbin_audit
from fm4_converter.paths import PROJECT_ROOT

FM4 = Path(r'D:\Data\forza-motorsport-4\Forza Motorsport 4 (Japan, Asia) (Disc 1) (Play Disc)\Media\cars')
HELPER = PROJECT_ROOT / 'outputs/fm-car-converter/import-v1/carbin-cpu-v9/carbin-cpu.exe'
FM2_DB = Path(r'D:\Data\FM2\USA\Forza Motorsport 2 (USA)\Media\DB\gamedb.slt')
FM2_WHEELS = Path(r'D:\Data\FM2\USA\Forza Motorsport 2 (USA)\Media\wheels')
OUT = PROJECT_ROOT / 'outputs/car-fm2-prototype-2026-11-03'
# Section _cockpit FM4 yang juga ada di FM2 (a_pillar dan jarum gauge tidak ada di FM2).
COCKPIT = ('seatL', 'seatR', 'steering_wheel', 'cagerace', 'glassLF', 'glassRF',
           'mirrorL', 'mirrorR', 'interior', 'glassF', 'hooda')
# Material FM2 `interior` membaca atlas bodi (teknik `interior` di LOD 1-5). Di kokpit LOD 0 ia menjadi
# `cockpit_plastic`, yang membaca Interior_LOD0.xds; paket uji mengisinya dengan atlas bodi yang sama.
# Kaca spion FM2 bermaterial `chrome`; FM4 menggambar pantulan hanya untuk mirrorLeft/Right/Middle.
# Ketiga mesh cocok posisi, ukuran, dan arah normalnya dengan mesh spion JAG_XKRS_09 (REPORT 9.2).
# Material eksterior FM2 di section kokpit (REPORT 14.2) tidak punya teknik cockpit_<material> di FM4.
# Semua teknik kokpit FM4 kecuali kaca membaca atlas interior (di sini atlas bodi): matte_colors, misc
# dan weatherstrip FM2 memang membaca atlas bodi; UV mesh `black` (teknik FM4 tanpa tekstur) menunjuk
# texel hampir hitam pada mobil yang diukur. tail_light membaca atlas lampu, yang tidak terbaca teknik
# kokpit mana pun (5-6 vertex per mobil).
COCKPIT_MATERIALS = {'interior': 'plastic', 'mirrorL/chrome': 'mirrorLeft', 'mirrorR/chrome': 'mirrorRight',
                     'interior/chrome': 'mirrorMiddle', 'black': 'plastic', 'matte_colors': 'plastic',
                     'misc': 'plastic', 'weatherstrip': 'rubber', 'black_glass': 'glass', 'window': 'glass',
                     'tail_light': 'reflector'}
# Spion tengah dengan UV konstan tidak bisa dipetakan ke UV 0-1 mirrorMiddle; mesh itu tetap
# cockpit_chrome dan blok cermin dinolkan seperti mobil tanpa spion tengah.
NO_MIDDLE_MIRROR = 'Mirror mesh mirrorMiddle has constant UVs'
MIRROR_MATERIALS = ('mirrorLeft', 'mirrorRight', 'mirrorMiddle')
NO_MIRROR = bytes(76) + struct.pack('>I', 1)   # blok cermin model tanpa mirrorMiddle (lihat carbin_audit)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def helper(*args):
    result = subprocess.run([str(HELPER), *map(str, args)], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stderr.strip())
    return json.loads(result.stdout)


def fix_mirror(data):
    """Blok cermin harus mengikuti mesh mirrorMiddle; header donor membawa milik donor."""
    if carbin_audit.mirror_block(carbin_audit.parse(data, 'FM4')) is None:
        data = data[:carbin_audit.MIRROR_BLOCK] + NO_MIRROR + data[carbin_audit.MIRROR_BLOCK + 80:]
    return carbin_audit.with_mirror_block(data)


def triangles(section, mesh, pool):
    """Segitiga mesh sebagai tuple vertex (posisi, normal, uv0, word damage) dari file FM4."""
    positions = carbin_audit.positions(section, pool, 'FM4')
    damage = section['damage0' if mesh['lod'] == 0 else 'damage']
    idx = list(carbin_audit.index_values(mesh)) if mesh['primitive'] == 4 else None
    if idx is None:
        b = mesh['indices']
        restart = (1 << 8 * b['stride']) - 1
        code = '>H' if b['stride'] == 2 else '>I'
        raw = [v for (v,) in struct.iter_unpack(code, b['data'])]
        idx, flip, i = [], True, 0
        while i < len(raw) - 2:
            a, c, e = raw[i:i + 3]
            if e in (restart, 0xFFFFFF):
                i, flip = i + 3, True
                continue
            if a != c and c != e and a != e:
                idx += [a, c, e] if flip else [c, a, e]
            flip, i = not flip, i + 1

    def vertex(i):
        u, v = struct.unpack_from('>2H', pool['data'], i * 32 + 8)
        uv = mesh['uv']
        word = damage['data'][i * 4:i * 4 + 4] if damage and damage['count'] else b''
        return (positions[i], carbin_audit.normal4(pool, i), (uv[0] + uv[1] * u / 65535, uv[2] + uv[3] * v / 65535), word)
    return [tuple(vertex(i) for i in idx[k:k + 3]) for k in range(0, len(idx) - 2, 3)]


def audit_closeup(main, data, donor_head, kind, renames=None):
    """File close-up vs LOD 1 model utama: header donor, mesh, segitiga, posisi, normal, UV, damage.
    `renames` = penggantian nama material yang diharapkan ({lama atau section/lama: baru})."""
    renames = renames or {}
    rename = lambda section, name: renames.get(f'{section}/{name}', renames.get(name, name))
    model = carbin_audit.parse(data, 'FM4')
    if model['header'][carbin_audit.MIRROR_BLOCK + 80:] != donor_head[carbin_audit.MIRROR_BLOCK + 80:]:
        raise carbin_audit.FormatError(f'{kind}: header differs from the donor header')
    names = {s['name']: s for s in main['sections']}
    worst = dict(position_m=0.0, normal_deg=0.0, uv=0.0)
    meshes = tris = refitted = 0
    damage_words = 0
    for section in model['sections']:
        source = names[section['name']]
        lod1 = [m for m in source['meshes'] if m['lod'] == 1]
        expected = [(rename(section['name'], m['name']), m['primitive']) for m in lod1]
        if expected != [(m['name'], m['primitive']) for m in section['meshes']]:
            raise carbin_audit.FormatError(f'{kind}/{section["name"]}: meshes differ from LOD 1')
        if section['lod']['count']:
            raise carbin_audit.FormatError(f'{kind}/{section["name"]}: close-up file with LOD 1-5 vertices')
        for a, b in zip(lod1, section['meshes']):
            ta, tb = triangles(source, a, source['lod']), triangles(section, b, section['lod0'])
            if len(ta) != len(tb):
                raise carbin_audit.FormatError(f'{kind}/{section["name"]}/{b["name"]}: triangle count')
            # UV spion dipasang ulang ke 0..1 oleh helper (FitMirrorUv); yang lain harus sama.
            mirror = b['name'] in MIRROR_MATERIALS and b['name'] != a['name']
            refitted += mirror
            for fa, fb in zip(ta, tb):
                for va, vb in zip(fa, fb):
                    worst['position_m'] = max(worst['position_m'], math.dist(va[0], vb[0]))
                    dot = sum(x * y for x, y in zip(va[1], vb[1]))
                    worst['normal_deg'] = max(worst['normal_deg'], math.degrees(math.acos(max(-1, min(1, dot)))))
                    if not mirror:
                        worst['uv'] = max(worst['uv'], max(abs(x - y) for x, y in zip(va[2], vb[2])))
                    elif not all(-1e-3 <= x <= 1 + 1e-3 for x in vb[2]):
                        raise carbin_audit.FormatError(f'{kind}/{section["name"]}/{b["name"]}: mirror UV outside 0..1')
                    if va[3] != vb[3]:
                        raise carbin_audit.FormatError(f'{kind}/{section["name"]}: damage word changed')
                    damage_words += bool(vb[3])
            meshes += 1
            tris += len(tb)
    if worst['position_m'] > 0.001 or worst['normal_deg'] > 0.05:
        raise carbin_audit.FormatError(f'{kind}: geometry drift {worst}')
    return dict(passed=True, sections=[s['name'] for s in model['sections']], meshes=meshes, triangles=tris,
                lod0_vertices=sum(s['lod0']['count'] for s in model['sections']),
                damage_words_checked=damage_words, mirror_meshes_uv_refitted=refitted,
                **{f'worst_{k}': v for k, v in worst.items()},
                draw_lists=[len(l) for l in model['lists']],
                mirror_block=carbin_audit.audit_mirror_block(data), sha256=sha(data), runtime_tested=False)


def compare_meshes(sa, ma, pa, sb, mb, pb, worst, where):
    """Segitiga mesh ma (pool pa) vs mb (pool pb): posisi, normal, UV, word damage; memperbarui worst."""
    ta, tb = triangles(sa, ma, pa), triangles(sb, mb, pb)
    if len(ta) != len(tb):
        raise carbin_audit.FormatError(f'{where}: triangle count')
    for fa, fb in zip(ta, tb):
        for va, vb in zip(fa, fb):
            worst['position_m'] = max(worst['position_m'], math.dist(va[0], vb[0]))
            dot = sum(x * y for x, y in zip(va[1], vb[1]))
            worst['normal_deg'] = max(worst['normal_deg'], math.degrees(math.acos(max(-1, min(1, dot)))))
            worst['uv'] = max(worst['uv'], max(abs(x - y) for x, y in zip(va[2], vb[2])))
            if va[3] != vb[3]:
                raise carbin_audit.FormatError(f'{where}: damage word changed')
    return len(tb)


def audit_wheel_lod0(before, after):
    """Velg FM4 setelah `lod0`: LOD 1-5 tetap, LOD 0 = mesh LOD 1 selain ban, rentang LOD 0-5."""
    a, b = carbin_audit.parse(before, 'FM4'), carbin_audit.parse(after, 'FM4')
    if [s['name'] for s in a['sections']] != [s['name'] for s in b['sections']]:
        raise carbin_audit.FormatError('wheel: sections changed')
    kept, lod0 = dict(position_m=0.0, normal_deg=0.0, uv=0.0), dict(position_m=0.0, normal_deg=0.0, uv=0.0)
    meshes = tris = 0
    for sa, sb in zip(a['sections'], b['sections']):
        if any(m['lod'] == 0 for m in sa['meshes']):
            raise carbin_audit.FormatError('wheel: source already has LOD 0')
        rest = [m for m in sb['meshes'] if m['lod'] != 0]
        if [(m['name'], m['lod'], m['primitive']) for m in sa['meshes']] != \
                [(m['name'], m['lod'], m['primitive']) for m in rest]:
            raise carbin_audit.FormatError(f'wheel/{sa["name"]}: LOD 1-5 meshes changed')
        for ma, mb in zip(sa['meshes'], rest):
            compare_meshes(sa, ma, sa['lod'], sb, mb, sb['lod'], kept, f'wheel/{sa["name"]}/{ma["name"]}')
        lod1 = [m for m in rest if m['lod'] == 1 and m['name'] != 'tire']
        new = [m for m in sb['meshes'] if m['lod'] == 0]
        if [(m['name'], m['primitive']) for m in lod1] != [(m['name'], m['primitive']) for m in new]:
            raise carbin_audit.FormatError(f'wheel/{sa["name"]}: LOD 0 meshes differ from LOD 1')
        for m1, m0 in zip(lod1, new):
            tris += compare_meshes(sb, m1, sb['lod'], sb, m0, sb['lod0'], lod0, f'wheel/{sa["name"]}/{m0["name"]} LOD 0')
            meshes += 1
    lod_range = struct.unpack_from('>2I', after, 0x15C)
    if lod_range != (0, 5) or max(kept['position_m'], lod0['position_m']) > 0.001 or \
            max(kept['normal_deg'], lod0['normal_deg']) > 0.05:
        raise carbin_audit.FormatError(f'wheel: LOD range {lod_range} or drift {kept} {lod0}')
    return dict(passed=True, lod0_meshes=meshes, lod0_triangles=tris, lod_range=list(lod_range),
                draw_lists=[len(l) for l in b['lists']], **{f'lod1_5_worst_{k}': v for k, v in kept.items()},
                **{f'lod0_worst_{k}': v for k, v in lod0.items()}, sha256=sha(after), runtime_tested=False)


def build_wheel(car, out):
    """Velg stock FM2 mobil `car` sebagai velg FM4 di out/wheel/<velg>.carbin; laporan velg."""
    with sqlite3.connect(f'file:{FM2_DB}?mode=ro', uri=True) as db:
        wheel, = db.execute('SELECT w.MediaName FROM Data_Car c JOIN List_Wheels w ON w.ID = c.StockWheelID '
                            'WHERE lower(c.MediaName) = ?', (car,)).fetchone()
    name = wheel.lower()
    with zipfile.ZipFile(next(p for p in FM2_WHEELS.glob('*.zip') if p.stem.lower() == name)) as z:
        fm2 = z.read(next(i.filename for i in z.infolist() if i.filename.lower() == name + '.carbin'))
    folder = out / 'wheel'
    folder.mkdir()
    fm3, transcode = fm2_to_fm3.convert(fm2)
    (folder / f'{name}.fm3.carbin').write_bytes(fm3)
    convert = helper('convert', folder / f'{name}.fm3.carbin', folder / f'{name}.lod15.carbin')
    lod15 = (folder / f'{name}.lod15.carbin').read_bytes()
    helper('lod0', folder / f'{name}.lod15.carbin', folder / f'{name}.carbin')
    return dict(media=wheel, source_sha256=sha(fm2), transcode=transcode,
                conversion_report=convert['conversion'].splitlines(),
                audit=carbin_audit.audit_conversion(fm3, lod15),
                lod0=audit_wheel_lod0(lod15, (folder / f'{name}.carbin').read_bytes()))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('car', help='MediaName FM2, mis. JAG_XK_07')
    p.add_argument('--donor', required=True, help='mobil disc FM4 untuk header _lod0/_cockpit, mis. JAG_XKRS_09')
    p.add_argument('--out', type=Path)
    a = p.parse_args()
    car, donor = a.car.lower(), a.donor.lower()
    out = a.out or OUT / car
    out.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(sv.zips(sv.FM2)[car]) as z:
        fm2 = z.read(next(i.filename for i in z.infolist() if i.filename.lower() == car + '.carbin'))
    with zipfile.ZipFile(next(q for q in FM4.glob('*.zip') if q.stem.lower() == donor)) as z:
        heads = {k: forza_zip.read(z, f'{donor}_{k}.carbin') for k in ('lod0', 'cockpit')}
    for k, data in heads.items():
        (out / f'donor_{k}.carbin').write_bytes(data)
    fm3, transcode = fm2_to_fm3.convert(fm2)
    (out / f'{car}.fm3.carbin').write_bytes(fm3)
    convert = helper('convert', out / f'{car}.fm3.carbin', out / f'{car}.carbin')
    main_data = (out / f'{car}.carbin').read_bytes()
    report = dict(car=a.car, donor=a.donor, source_sha256=sha(fm2), transcode=transcode,
                  main=dict(conversion_report=convert['conversion'].splitlines(),
                            audit=carbin_audit.audit_conversion(fm3, main_data),
                            mirror_block=carbin_audit.audit_mirror_block(main_data)))
    (out / 'cockpit_sections.txt').write_text('\n'.join(COCKPIT) + '\n')
    model = carbin_audit.parse(main_data, 'FM4')
    # Helper menolak rename yang tidak mengenai mesh; hanya pasangan yang ada di section kokpit dipakai.
    present = {(s['name'], m['name']) for s in model['sections'] if s['name'] in COCKPIT for m in s['meshes']}
    materials = {k: v for k, v in COCKPIT_MATERIALS.items()
                 if (tuple(k.split('/')) in present if '/' in k else any(m == k for _, m in present))}
    (out / 'cockpit_materials.txt').write_text(''.join(f'{a} {b}\n' for a, b in materials.items()))
    for kind, mode in (('lod0', 'exclude'), ('cockpit', 'include')):
        raw = out / f'{car}_{kind}.helper.carbin'
        renames = materials if kind == 'cockpit' else {}
        args = ('closeup', out / f'{car}.carbin', out / f'donor_{kind}.carbin', raw, out / 'cockpit_sections.txt', mode)
        try:
            closeup = helper(*args, *([out / 'cockpit_materials.txt'] if renames else []))
        except RuntimeError as error:
            if not renames or NO_MIDDLE_MIRROR not in str(error):
                raise
            del materials['interior/chrome']
            (out / 'cockpit_materials.txt').write_text(''.join(f'{a} {b}\n' for a, b in materials.items()))
            closeup = helper(*args, out / 'cockpit_materials.txt')
            report['middle_mirror_dropped'] = str(error)
        data = fix_mirror(raw.read_bytes())
        (out / f'{car}_{kind}.carbin').write_bytes(data)
        donor_head = carbin_audit.parse(heads[kind], 'FM4')['header']
        report[kind] = audit_closeup(model, data, donor_head, kind, renames)
        report[kind]['renamed_meshes'] = closeup['renamed_meshes']
        report[kind]['mirror_uv_fit_residual'] = closeup['mirror_uv_fit_residual']
    names = [s['name'] for s in model['sections']]
    split = set(report['lod0']['sections']) | set(report['cockpit']['sections'])
    report['split'] = dict(main_sections=len(names), covered=split == set(names),
                           overlap=sorted(set(report['lod0']['sections']) & set(report['cockpit']['sections'])),
                           missing_vs_donor_cockpit=sorted(
                               {s['name'] for s in carbin_audit.parse(heads['cockpit'], 'FM4')['sections']}
                               - set(report['cockpit']['sections'])))
    report['wheel'] = build_wheel(car, out)
    (out / 'report.json').write_text(json.dumps(report, indent=1), encoding='utf-8')
    brief = {k: report[k] for k in ('car', 'donor', 'transcode', 'split')}
    brief['main'] = {k: report['main']['audit'][k] for k in ('passed', 'vertices', 'meshes', 'position_error_m',
                                                             'normal_error_degrees', 'uv_error')}
    for kind in ('lod0', 'cockpit'):
        brief[kind] = {k: v for k, v in report[kind].items() if k not in ('sections', 'sha256')}
    wheel = report['wheel']
    brief['wheel'] = dict(media=wheel['media'], lod0=wheel['lod0'],
                          **{k: wheel['audit'][k] for k in ('passed', 'vertices', 'meshes', 'position_error_m',
                                                            'normal_error_degrees', 'uv_error')})
    json.dump(brief, sys.stdout, indent=1)
    print()


if __name__ == '__main__':
    main()
