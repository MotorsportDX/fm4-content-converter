"""FM4 models for one FM2 car: <car>.carbin, <car>_lod0.carbin, <car>_cockpit.carbin and its stock
wheel wheel/<wheel>.carbin.

Path: FM2 .carbin -> `transcode` -> `carbin-cpu convert` (the FM3 -> FM4 converter used for FM3
cars) -> FM4 main model (LOD 1-5). `carbin-cpu closeup` (ForzaEditor's CloseUpFromLod1) then builds
_lod0 and _cockpit from the main model's LOD 1. Sections are split as on FM4 disc cars: cockpit
sections (COCKPIT) go to _cockpit, the rest to _lod0; the game draws both together at LOD 0. Both
close-up headers come from the same files of an FM4 donor car, because FM2 has no close-up
header; the cockpit mirror block is zeroed when there is no mirrorMiddle mesh. Materials in
_cockpit are renamed by COCKPIT_MATERIALS: FM4 maps LOD 0 cockpit meshes to the technique
`cockpit_<material>`, and FM4's effects have no `cockpit_interior`.

Audit: the main model with carbin_audit.audit_conversion (as FM3 cars); the close-up files are
read by carbin_audit (FM4), then every LOD 0 mesh is compared triangle by triangle (position,
normal, UV, damage word) with the same LOD 1 mesh of the main model. No game is run.

Wheel: FM2 wheel .carbin (type 1) -> `transcode` (FM3 wheel, type 2) -> `carbin-cpu convert` (FM4
wheel type 3, LOD 1-5, audited with audit_conversion) -> `carbin-cpu lod0` (ForzaEditor's
Lod0FromLod1: LOD 0 = copy of LOD 1 without the tyre, as 441 of 442 FM4 wheels). audit_wheel_lod0
compares LOD 1-5 before and after, and every LOD 0 mesh with the same LOD 1 mesh.
"""
from pathlib import Path
import argparse, hashlib, json, math, sqlite3, struct, subprocess, sys, zipfile

from . import sources, transcode
from ..archives import forza_zip
from ..fm3 import appearance_audit, carbin_audit
from ..paths import PROJECT_ROOT

HELPER = PROJECT_ROOT / 'outputs/fm-car-converter/import-v1/carbin-cpu-v9/carbin-cpu.exe'
# FM4 _cockpit sections that FM2 also has (FM2 has no a_pillar or gauge needles).
COCKPIT = ('seatL', 'seatR', 'steering_wheel', 'cagerace', 'glassLF', 'glassRF',
           'mirrorL', 'mirrorR', 'interior', 'glassF', 'hooda')
# The FM2 material `interior` reads the body atlas (technique `interior` at LOD 1-5). In the LOD 0
# cockpit it becomes `cockpit_plastic`, which reads Interior_LOD0.xds; packages fill that with the
# same body atlas. FM2 mirror glass uses `chrome`; FM4 only draws reflections for
# mirrorLeft/Right/Middle. The three meshes match the position, size and normal direction of the
# JAG_XKRS_09 mirror meshes (REPORT 9.2).
# FM2 exterior materials in cockpit sections (REPORT 14.2) have no cockpit_<material> technique in
# FM4. Every FM4 cockpit technique except glass reads the interior atlas (here the body atlas):
# FM2's matte_colors, misc and weatherstrip read the body atlas too; the UVs of `black` meshes (an
# untextured FM4 technique) point at near-black texels on the cars measured. tail_light reads the
# lights atlas, which no cockpit technique reads (5-6 vertices per car).
COCKPIT_MATERIALS = {'interior': 'plastic', 'mirrorL/chrome': 'mirrorLeft', 'mirrorR/chrome': 'mirrorRight',
                     'interior/chrome': 'mirrorMiddle', 'black': 'plastic', 'matte_colors': 'plastic',
                     'misc': 'plastic', 'weatherstrip': 'rubber', 'black_glass': 'glass', 'window': 'glass',
                     'tail_light': 'reflector'}
# A middle mirror with constant UVs cannot be fitted to mirrorMiddle's 0-1 UVs; that mesh stays
# cockpit_chrome and the mirror block is zeroed as on cars without a middle mirror.
NO_MIDDLE_MIRROR = 'Mirror mesh mirrorMiddle has constant UVs'
MIRROR_MATERIALS = ('mirrorLeft', 'mirrorRight', 'mirrorMiddle')
NO_MIRROR = bytes(76) + struct.pack('>I', 1)   # mirror block of a model without mirrorMiddle (see carbin_audit)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def run_helper(helper, *args):
    result = subprocess.run([str(helper), *map(str, args)], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stderr.strip())
    return json.loads(result.stdout)


def cockpit_renames(model):
    """`section/material` renames for the _cockpit sections of the FM4 main model. A `section/material`
    key of COCKPIT_MATERIALS applies as written; a bare `material` key only applies in sections that
    FM4 maps to `cockpit_<material>` (appearance_audit.COCKPIT_PARTS): glass, mirror, hood and cage
    sections keep their exterior techniques (frontwindow, black, ...). The helper rejects renames
    that match nothing, so only meshes that exist are listed."""
    out = {}
    for section in model['sections']:
        if section['name'] not in COCKPIT:
            continue
        cockpit = any(p in section['name'].casefold() for p in appearance_audit.COCKPIT_PARTS)
        for mesh in (m for m in section['meshes'] if m['lod'] == 1):   # close-ups are built from LOD 1
            key = f"{section['name']}/{mesh['name']}"
            if key in COCKPIT_MATERIALS:
                out[key] = COCKPIT_MATERIALS[key]
            elif cockpit and mesh['name'] in COCKPIT_MATERIALS:
                out[key] = COCKPIT_MATERIALS[mesh['name']]
    return out


def fix_mirror(data):
    """The mirror block must follow the mirrorMiddle mesh; the donor header carries the donor's."""
    if carbin_audit.mirror_block(carbin_audit.parse(data, 'FM4')) is None:
        data = data[:carbin_audit.MIRROR_BLOCK] + NO_MIRROR + data[carbin_audit.MIRROR_BLOCK + 80:]
    return carbin_audit.with_mirror_block(data)


def triangles(section, mesh, pool):
    """A mesh's triangles as vertex tuples (position, normal, uv0, damage word) from an FM4 file."""
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
    """Close-up file vs the main model's LOD 1: donor header, meshes, triangles, positions, normals,
    UVs, damage. `renames` = the expected material renames ({old or section/old: new})."""
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
            # The helper refits mirror UVs to 0..1 (FitMirrorUv); everything else must match.
            mirror = b['name'] in MIRROR_MATERIALS and b['name'] != a['name']
            refitted += mirror
            for fa, fb in zip(ta, tb):
                for va, vb in zip(fa, fb):
                    worst['position_m'] = max(worst['position_m'], math.dist(va[0], vb[0]))
                    dot = sum(x * y for x, y in zip(va[1], vb[1]))
                    worst['normal_deg'] = max(worst['normal_deg'], math.degrees(math.acos(max(-1, min(1, dot)))))
                    if not mirror:
                        worst['uv'] = max(worst['uv'], max(abs(x - y) for x, y in zip(va[2], vb[2])))
                    else:
                        # A mirror whose vertices FM2 shares with its housing keeps the best
                        # affine fit (FitMirrorUv); the shared vertices can then fall a little
                        # outside the glass's 0..1, recorded here. Far outside, the fit is wrong.
                        outside = max(max(-x, x - 1, 0) for x in vb[2])
                        worst['mirror_uv_outside'] = max(worst.get('mirror_uv_outside', 0), outside)
                        if outside > 1:
                            raise carbin_audit.FormatError(f'{kind}/{section["name"]}/{b["name"]}: mirror UV far '
                                                           f'outside 0..1 ({outside:.3f})')
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
    """Triangles of mesh ma (pool pa) vs mb (pool pb): position, normal, UV, damage word; updates worst."""
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
    """FM4 wheel after `lod0`: LOD 1-5 unchanged, LOD 0 = LOD 1 meshes except the tyre, LOD range 0-5."""
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


def build_wheel(car, out, helper=HELPER):
    """The FM2 stock wheel of `car` as an FM4 wheel in out/wheel/<wheel>.carbin; the wheel report."""
    with sqlite3.connect(f'file:{sources.fm2_db()}?mode=ro', uri=True) as db:
        wheel, = db.execute('SELECT w.MediaName FROM Data_Car c JOIN List_Wheels w ON w.ID = c.StockWheelID '
                            'WHERE lower(c.MediaName) = ?', (car,)).fetchone()
    name = wheel.lower()
    with zipfile.ZipFile(sources.fm2_zip('wheels', name)) as z:
        fm2 = z.read(next(i.filename for i in z.infolist() if i.filename.lower() == name + '.carbin'))
    folder = out / 'wheel'
    folder.mkdir()
    fm3, summary = transcode.convert(fm2)
    (folder / f'{name}.fm3.carbin').write_bytes(fm3)
    convert = run_helper(helper, 'convert', folder / f'{name}.fm3.carbin', folder / f'{name}.lod15.carbin')
    lod15 = (folder / f'{name}.lod15.carbin').read_bytes()
    run_helper(helper, 'lod0', folder / f'{name}.lod15.carbin', folder / f'{name}.carbin')
    return dict(media=wheel, source_sha256=sha(fm2), transcode=summary,
                conversion_report=convert['conversion'].splitlines(),
                audit=carbin_audit.audit_conversion(fm3, lod15),
                lod0=audit_wheel_lod0(lod15, (folder / f'{name}.carbin').read_bytes()))


def build(car_media, donor_media, out, helper=HELPER):
    """Write the models of FM2 car `car_media` with close-up headers of FM4 disc car `donor_media`
    into the new folder `out`; returns the report, also saved as out/report.json."""
    car, donor, out = car_media.lower(), donor_media.lower(), Path(out)
    out.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(sources.fm2_zip('cars', car)) as z:
        fm2 = z.read(next(i.filename for i in z.infolist() if i.filename.lower() == car + '.carbin'))
    with zipfile.ZipFile(sources.disc_zip(sources.FM4_CARS, donor)) as z:
        heads = {k: forza_zip.read(z, f'{donor}_{k}.carbin') for k in ('lod0', 'cockpit')}
    for k, data in heads.items():
        (out / f'donor_{k}.carbin').write_bytes(data)
    fm3, summary = transcode.convert(fm2)
    (out / f'{car}.fm3.carbin').write_bytes(fm3)
    convert = run_helper(helper, 'convert', out / f'{car}.fm3.carbin', out / f'{car}.carbin')
    main_data = (out / f'{car}.carbin').read_bytes()
    report = dict(car=car_media, donor=donor_media, source_sha256=sha(fm2), transcode=summary,
                  main=dict(conversion_report=convert['conversion'].splitlines(),
                            audit=carbin_audit.audit_conversion(fm3, main_data),
                            mirror_block=carbin_audit.audit_mirror_block(main_data)))
    (out / 'cockpit_sections.txt').write_text('\n'.join(COCKPIT) + '\n')
    model = carbin_audit.parse(main_data, 'FM4')
    materials = cockpit_renames(model)
    (out / 'cockpit_materials.txt').write_text(''.join(f'{a} {b}\n' for a, b in materials.items()))
    for kind, mode in (('lod0', 'exclude'), ('cockpit', 'include')):
        raw = out / f'{car}_{kind}.helper.carbin'
        renames = materials if kind == 'cockpit' else {}
        args = ('closeup', out / f'{car}.carbin', out / f'donor_{kind}.carbin', raw, out / 'cockpit_sections.txt', mode)
        try:
            closeup = run_helper(helper, *args, *([out / 'cockpit_materials.txt'] if renames else []))
        except RuntimeError as error:
            if not renames or NO_MIDDLE_MIRROR not in str(error):
                raise
            materials.pop('interior/chrome', None)
            (out / 'cockpit_materials.txt').write_text(''.join(f'{a} {b}\n' for a, b in materials.items()))
            closeup = run_helper(helper, *args, out / 'cockpit_materials.txt')
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
    report['wheel'] = build_wheel(car, out, helper)
    (out / 'report.json').write_text(json.dumps(report, indent=1), encoding='utf-8')
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('car', help='FM2 MediaName, e.g. JAG_XK_07')
    p.add_argument('--donor', required=True, help='FM4 disc car for the _lod0/_cockpit headers, e.g. JAG_XKRS_09')
    p.add_argument('--out', type=Path, required=True, help='new folder for the models')
    p.add_argument('--helper', type=Path, default=HELPER, help='reviewed CPU-only carbin-cpu.exe')
    a = p.parse_args()
    report = build(a.car, a.donor, a.out, a.helper)
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
