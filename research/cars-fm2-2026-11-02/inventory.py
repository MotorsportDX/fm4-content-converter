"""Inventaris mobil FM2 -> FM4: rute sumber per mobil dan bentuk aset ZIP FM2.

Hanya membaca. Katalog mobil diambil dari evidence riset fisika 20 Oktober 2026
(outputs/physics-research-2026-10-20, diabaikan Git), ZIP mobil dibaca langsung
dari disc. Hasil ditulis ke outputs/car-fm2-research-2026-11-02/inventory.json.
"""
from pathlib import Path
import argparse, collections, csv, json, os, sys, zipfile

from fm4_converter.archives import forza_zip
from fm4_converter.paths import PHYSICS_RESEARCH_OUTPUT, PROJECT_ROOT

FM2 = Path(r'D:\Data\FM2\USA\Forza Motorsport 2 (USA)\Media\cars')
FM3 = Path(r'D:\Data\FM3\USA\Forza Motorsport 3 (USA) (Disc 1) (Play Disc)\Media\cars')
FM4 = Path(r'D:\Data\forza-motorsport-4\Forza Motorsport 4 (Japan, Asia) (Disc 1) (Play Disc)\Media\cars')
FM3_ONLY = PROJECT_ROOT / 'outputs/fm-car-converter/fm3-only-v1/package-paint/manifest.json'
OUT = PROJECT_ROOT / 'outputs/car-fm2-research-2026-11-02/inventory.json'
SAMPLES = ['ACU_42_NSX_02', 'JAG_XK_07', 'MAZ_RX7_ABFlug_95']


def rows(name):
    with open(PHYSICS_RESEARCH_OUTPUT / name, encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def catalogs():
    fm2 = [dict(Id=r['Id'], Year=r['Year'], MediaName=r['MediaName'], Package='base')
           for r in rows('fm2/cars_physics_map.csv')]
    fm2 += [dict(Id=r['Id'], Year=r['Year'], MediaName=r['MediaName'], Package=r['Package'])
            for r in rows('fm2/bonus_cars_map.csv')]
    fm3 = rows('fm3/cars_map.csv')
    fm4 = [dict(r, Package='disc') for r in rows('fm4/car_catalog.csv')] + rows('dlc/cars_catalog.csv')
    return fm2, fm3, fm4


def route(fm2, fm3, fm4, fm3_only):
    """Sumber terbaik per mobil FM2. Nama dicocokkan dulu, lalu Data_Car.Id."""
    by_name = lambda rs: {r['MediaName'].casefold(): r for r in rs}
    by_id = lambda rs: {r['Id']: r for r in rs}
    n4, i4 = by_name(fm4), by_id(fm4)
    d1 = [r for r in fm3 if r['edition'] == 'regular_d1']
    n3, i3 = by_name(d1), by_id(d1)
    nuc, iuc = by_name(fm3), by_id(fm3)
    out = []
    for car in fm2:
        k, i = car['MediaName'].casefold(), car['Id']
        if k in n4:
            kind, other = 'fm4_same_name', n4[k]['MediaName']
        elif i in i4:
            kind, other = 'fm4_same_id_renamed', i4[i]['MediaName']
        elif k in n3 or i in i3:
            kind, other = 'fm3_source', (n3.get(k) or i3[i])['MediaName']
        elif k in nuc or i in iuc:
            kind, other = 'fm3_uc_only', (nuc.get(k) or iuc[i])['MediaName']
        else:
            kind, other = 'fm2_only', None
        entry = dict(car, route=kind, match=other)
        if other and kind.startswith('fm3'):
            entry['fm3_only_package'] = fm3_only.get(other.casefold(), 'not_selected')
        out.append(entry)
    return out


def near_matches(car, fm3, fm4):
    """Mobil FM3/FM4 dengan prefix merek sama dan selisih tahun <= 1, untuk cek manual."""
    make, year = car['MediaName'].split('_')[0].casefold(), int(car['Year'])
    found = {(r['MediaName'], g) for g, rs in (('FM3', fm3), ('FM4', fm4)) for r in rs
             if r['MediaName'].split('_')[0].casefold() == make and abs(int(r['Year']) - year) <= 1}
    return sorted(f'{n} ({g})' for n, g in found)


def zip_path(root, media):
    return next((root / n for n in os.listdir(root) if n.casefold() == media.casefold() + '.zip'), None)


def zip_shape(path, headers=False):
    with zipfile.ZipFile(path) as z:
        infos = [i for i in z.infolist() if not i.is_dir()]
        carbins = sorted(i.filename for i in infos if i.filename.lower().endswith('.carbin'))
        shape = dict(
            members=len(infos), bytes=path.stat().st_size,
            methods=dict(collections.Counter(str(i.compress_type) for i in infos)),
            carbins=carbins,
            xds=sorted(i.filename for i in infos if i.filename.lower().endswith('.xds')),
            has_cockpit=any('_cockpit' in c.lower() for c in carbins),
            has_lod0=any('_lod0' in c.lower() for c in carbins),
            has_livery_masks=any(i.filename.lower().startswith('liverymasks/') for i in infos))
        if headers:
            shape['carbin_head'] = {c: forza_zip.read(z, c)[:16].hex() for c in carbins
                                    if '_caliper' not in c.lower() and '_rotor' not in c.lower()}
            shape['xds_head'] = sorted({forza_zip.read(z, x)[:8].hex() for x in shape['xds']})
    return shape


def asset_survey(fm2_cars):
    """Bentuk ZIP setiap mobil FM2 base. Mobil Bonus Disc ada di paket STFS dan tidak dibuka di sini."""
    shapes, missing = {}, []
    for car in fm2_cars:
        if car['Package'] != 'base':
            continue
        path = zip_path(FM2, car['MediaName'])
        if path is None:
            missing.append(car['MediaName'])
            continue
        with zipfile.ZipFile(path) as z:
            names = [i.filename for i in z.infolist() if not i.is_dir()]
            carbins = [n for n in names if n.lower().endswith('.carbin')]
            first = {z.open(n).read(4).hex() for n in carbins}
        shapes[car['MediaName']] = dict(carbins=len(carbins), version_words=sorted(first),
                                        livery_masks=any(n.lower().startswith('liverymasks/') for n in names),
                                        methods=sorted({str(i.compress_type) for i in z.infolist()}))
    summary = dict(
        zips=len(shapes), missing_zip=missing,
        carbins_per_zip=dict(collections.Counter(str(s['carbins']) for s in shapes.values())),
        carbin_version_word=dict(collections.Counter(' '.join(s['version_words']) for s in shapes.values())),
        zip_methods=dict(collections.Counter(' '.join(s['methods']) for s in shapes.values())),
        with_livery_masks=sum(s['livery_masks'] for s in shapes.values()))
    return summary, shapes


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, default=OUT)
    a = p.parse_args()
    fm2, fm3, fm4 = catalogs()
    fm3_only = {}
    if FM3_ONLY.exists():
        fm3_only = {c['media'].casefold(): c['status'] for c in json.loads(FM3_ONLY.read_text())['cars']}
    cars = route(fm2, fm3, fm4, fm3_only)
    for car in cars:
        if car['route'] == 'fm2_only':
            car['near_matches'] = near_matches(car, fm3, fm4)
    summary, shapes = asset_survey(fm2)
    samples = {}
    for media in SAMPLES:
        for game, root in (('FM2', FM2), ('FM3', FM3), ('FM4', FM4)):
            path = zip_path(root, media)
            if path:
                samples[f'{game}/{media}'] = zip_shape(path, headers=True)
    result = dict(
        counts=dict(fm2_definitions=len(fm2), **collections.Counter(c['route'] for c in cars)),
        fm3_source_package_status=dict(collections.Counter(
            c.get('fm3_only_package') for c in cars if c['route'].startswith('fm3'))),
        cars=cars, fm2_asset_summary=summary, fm2_asset_shapes=shapes, samples=samples)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding='utf-8')
    json.dump(dict(counts=result['counts'], fm3_source_package_status=result['fm3_source_package_status'],
                   fm2_asset_summary=summary), sys.stdout, indent=1)
    print()


if __name__ == '__main__':
    main()
