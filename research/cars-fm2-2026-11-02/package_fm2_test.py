"""Paket overlay uji FM4 untuk satu mobil FM2-only, mis. JAG_XK_07 (lihat REPORT bagian 8).

Isi paket (bentuknya sama dengan paket FM3 `batch_package.py`, satu mobil saja):
- `Media/Cars/<car>.zip`: model utama, `_lod0` dan `_cockpit` dari prototype_fm4_model.py; tekstur
  bodi FM2 dengan konstanta fetch FM4 (`asset_conversion.convert_texture`, header XDS FM2 = FM3);
  atlas `_lod0` = atlas LOD1 yang sama, karena `_lod0` dibuat dari mesh LOD1 dengan UV yang sama;
  `carattribs.xml` dan `physics/maxdata.xml` FM2; kaliper dan rotor dari mobil donor FM4;
  `shadersettings.xml` berisi PaintScale cockpit FM4 (`with_cockpit_paint_scales`).
- `Media/Wheels/<velg>.zip`: velg stock FM2 dari prototype_fm4_model.py (LOD 0-5) dan tekstur
  velg FM2; `wheel_lod0.xds` = `wheel.xds`, karena LOD 0 velg memakai UV LOD 1.
- Database: graf stock mobil donor FM4 disalin dengan kunci baru, `Data_Car.Id` = Id FM2,
  `MediaName`/`Year` FM2, `List_Wheels.MediaName` = velg FM2. Fisika, kelas, PI, sisa baris velg,
  posisi part dan kamera milik donor;
  kalibrasi fisika FM2 belum dikerjakan (REPORT bagian 4).
- Nama FM2 bahasa Inggris + " (FM2)" di `stringtables.zip` berprioritas tertinggi.
- Thumbnail FM2 (DXT5 256x128, sudah punya alpha) dalam atlas UI FM4 768x288.

Audit: `appearance_audit.audit` (teknik efek, tekstur, rig driver) seperti mobil FM3, ditambah
graf database yang dibaca ulang dari database paket. Game tidak dijalankan.

  python research/cars-fm2-2026-11-02/package_fm2_test.py JAG_XK_07 --donor JAG_XKRS_09 --out <paket-baru>
"""
from contextlib import closing
from pathlib import Path, PurePosixPath
import argparse, hashlib, io, json, shutil, sqlite3, sys, zipfile

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import survey_carbin as sv
from fm4_converter.fm3 import appearance_audit, batch_package, carbin_audit, integration, ui_names, ui_thumbnail
from fm4_converter.fm3 import converter as c
from fm4_converter.fm3.asset_conversion import convert_texture
from fm4_converter.fm3.integration import archive_read
from fm4_converter.fm3.texture_audit import Texture
from fm4_converter.paths import PROJECT_ROOT

FM2_MEDIA = Path(r'D:\Data\FM2\USA\Forza Motorsport 2 (USA)\Media')
CONTENT = Path(r'I:\FM4-build-usa\user-data\0000000000000000\4D530910\00000002')
PROTOTYPE = PROJECT_ROOT / 'outputs/car-fm2-prototype-2026-11-03'
FM2_WHEELS = FM2_MEDIA / 'wheels'
CARS, WHEELS, THUMBNAILS = Path('Media/Cars'), Path('Media/Wheels'), batch_package.THUMBNAILS
BODY_TEXTURES = ('nodamage', 'damage', 'lights', 'damagelights')
# Kunci Data_Car.str FM4 memakai word atas 0xCD49 (mis. _&3444170456).
STRING_PAGE = 0xCD49
# Kolom kepemilikan mobil di tabel presentasi, dan tabel yang punya kunci ID sendiri.
PRESENTATION = {'CarPartPositions': 'Ordinal', 'CarExceptions': 'CarID',
                'CameraOverrides': 'CarId', 'Combo_Colors': 'Ordinal'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def find(members, name):
    found = [k for k in members if k.casefold() == name.casefold()]
    if len(found) != 1:
        raise c.MappingError(f'Expected one {name}, got {found}')
    return found[0]


def thumbnail(data, template):
    """Atlas UI FM4 dari thumbnail FM2. Alpha FM2 sudah berupa cutout, jadi matte putih FM3
    tidak dihapus dan kurva warna FM3->FM4 tidak dipakai (diukur pada render FM3)."""
    t = Texture(data)
    if (t.width, t.height, t.codec) != (256, 128, 'DXT5'):
        raise c.MappingError('Unreviewed FM2 thumbnail format')
    cutout = Image.frombytes('RGBA', (t.width, t.height), t.read_level(0), 'bcn', 3)
    alpha = np.array(cutout)[:, :, 3]
    border = np.concatenate([alpha[0], alpha[-1], alpha[:, 0], alpha[:, -1]])
    if alpha.max() < 255 or (border > 0).mean() > ui_thumbnail.MAX_CROPPED_BORDER:
        raise c.MappingError('FM2 thumbnail alpha is not a car cutout')
    atlas = Image.new('RGBA', (768, 288))
    atlas.paste(ui_thumbnail.fit_view(cutout, (608, 288), ui_thumbnail.LARGE_LAYOUT), (0, 0))
    small = ui_thumbnail.fit_view(cutout, (288, 160), ui_thumbnail.SMALL_LAYOUT)
    atlas.paste(small.transpose(Image.Transpose.ROTATE_90), (608, 0))
    encoded = ui_thumbnail.encode(atlas, template)
    return encoded, dict(source=[t.width, t.height, t.codec], source_sha256=sha(data), target_sha256=sha(encoded),
                         alpha_border_share=float((border > 0).mean()), fm4_tone=False,
                         texture=Texture(encoded).audit())


def assets(car, donor, models, fm2_zip, donor_zip, wheel):
    """{Media/Cars/<car>/... dan Media/Wheels/<wheel>/...: bytes} dan catatan asal tiap berkas."""
    root, payloads, origin = CARS / car, {}, {}

    def put(name, data, source):
        payloads[root / name] = data
        origin[(root / name).as_posix()] = source
    for kind in ('', '_lod0', '_cockpit'):
        name = f'{car.lower()}{kind}.carbin'
        put(name, (models / name).read_bytes(), 'prototype_fm4_model.py')
    with zipfile.ZipFile(fm2_zip) as z:
        fm2 = {i.filename: z.read(i) for i in z.infolist() if not i.is_dir()}
    for texture in BODY_TEXTURES:
        data = convert_texture(fm2[find(fm2, texture + '.xds')], texture + '.xds')
        put(texture + '.xds', data, f'FM2 {texture}.xds, FM4 colour fetch constants')
        put(texture + '_lod0.xds', data, f'FM2 {texture}.xds (LOD0 meshes use the LOD1 UVs)')
        if texture == 'nodamage':
            # Mesh kokpit `interior` FM2 (kini cockpit_plastic) memakai UV atlas bodi.
            put('interior_lod0.xds', data, 'FM2 Nodamage.xds (cockpit meshes use the body atlas UVs)')
    put('carattribs.xml', fm2[find(fm2, 'CarAttribs.xml')], 'FM2 CarAttribs.xml')
    put('physics/maxdata.xml', fm2[find(fm2, 'Physics/MAXData.xml')], 'FM2 Physics/MAXData.xml')
    with zipfile.ZipFile(donor_zip) as z:
        for info in z.infolist():
            name = info.filename.lower()
            if name.startswith(donor.lower() + '_') and ('_caliper' in name or '_rotor' in name):
                put(car.lower() + name[len(donor):], archive_read(z, info), f'donor {info.filename}')
    if sum('_caliper' in k or '_rotor' in k for k in origin) != 8:
        raise c.MappingError('Donor must have four calipers and four rotors')
    # Velg stock FM2: model dari prototype_fm4_model.py, tekstur FM2; LOD 0 velg memakai UV LOD 1.
    wheel_root = WHEELS / wheel
    payloads[wheel_root / f'{wheel.lower()}.carbin'] = (models / 'wheel' / f'{wheel.lower()}.carbin').read_bytes()
    origin[(wheel_root / f'{wheel.lower()}.carbin').as_posix()] = 'prototype_fm4_model.py (FM2 wheel)'
    with zipfile.ZipFile(next(p for p in FM2_WHEELS.glob('*.zip') if p.stem.casefold() == wheel.casefold())) as z:
        rims = {i.filename: z.read(i) for i in z.infolist() if not i.is_dir()}
    for name in [n for n in rims if n.lower().endswith('.xds')]:
        data = convert_texture(rims[name], name)
        payloads[wheel_root / name.lower()] = data
        origin[(wheel_root / name.lower()).as_posix()] = f'FM2 wheel {name}, FM4 colour fetch constants'
        if name.lower() == 'wheel.xds':
            payloads[wheel_root / 'wheel_lod0.xds'] = data
            origin[(wheel_root / 'wheel_lod0.xds').as_posix()] = 'FM2 wheel wheel.xds (LOD 0 uses the LOD 1 UVs)'
    skipped = sorted(k for k in fm2 if not any(k.casefold() == f.casefold() for f in
                     [t + '.xds' for t in BODY_TEXTURES] + ['CarAttribs.xml', 'Physics/MAXData.xml', car.lower() + '.carbin']))
    return payloads, origin, skipped


def clone_stock(work, donor, media, car_id, year, reserved):
    """Graf stock donor dengan kunci baru (kunci bebas mulai 2000, lewati kunci DLC)."""
    graph = c.extract_stock(work, donor)
    occupied, allocation = {}, {}
    for role, node in sorted(graph['nodes'].items()):
        table, key = node['table'], node['row'][node['pk']]
        if table not in occupied:
            occupied[table] = {r[0] for r in work.execute(f"SELECT {c.qi(node['pk'])} FROM {c.qi(table)}")}
            occupied[table] |= set(reserved.get(table, ()))
        if (table, key) in allocation:
            continue
        value = car_id if role == 'car' else 2000
        while role != 'car' and value in occupied[table]:
            value += 1
        if value in occupied[table]:
            raise c.MappingError(f'Key already used: {table} {value}')
        allocation[table, key] = value
        occupied[table].add(value)
    nodes = {}
    for role, node in graph['nodes'].items():
        row = dict(node['row'])
        row[node['pk']] = allocation[node['table'], row[node['pk']]]
        nodes[role] = dict(node, row=row)
    for edge in graph['edges']:
        parent = graph['nodes'][edge['to']]
        nodes[edge['from']]['row'][edge['column']] = allocation[parent['table'], parent['row'][parent['pk']]]
    car = nodes['car']['row']
    car.update(MediaName=media, Year=year, ModelId=car_id, ContentId=0, IsInstalled=1, IsPurchased=1,
               IsArcade=1, IsUnicorn=0, IsDrivable=1, HasCarExperience=0, IsCarExperienceUnlocked=0)
    rows = [{'table': n['table'], 'row': n['row']} for n in nodes.values()]
    donor_id = graph['nodes']['car']['row']['Id']
    for table, column in PRESENTATION.items():
        own = 'ID' in {x['name'] for x in c.schema(work)[table]['columns']}
        next_id = 1 + max([work.execute(f'SELECT MAX(ID) FROM {table}').fetchone()[0] or 0,
                           *reserved.get(table, ())]) if own else None
        for original in c.rows(work, table, c.qi(column) + '=?', (donor_id,)):
            row = dict(original, **{column: car_id})
            if own:
                row['ID'], next_id = next_id, next_id + 1
            rows.append({'table': table, 'row': row})
    return graph, nodes, rows


def names(car_id, label, taken):
    """Dua kunci Data_Car.str bebas (tertinggi) untuk DisplayName dan ModelShort."""
    keys = {}
    for field in ('DisplayName', 'ModelShort'):
        free = next(k for k in range(65534, 0, -1) if k not in taken)
        taken.add(free)
        keys[field] = dict(reference=f'_&{STRING_PAGE << 16 | free}', symbol=f'IDS_{field}_{car_id}', text=label[field])
    return keys


def string_archive(target_root, content_root, keys):
    tables, inputs = ui_names.winning_tables(target_root, content_root, archive_read, c.sha)
    additions = [(ui_names.reference(k['reference']), k['symbol'], k['text']) for k in keys.values()]
    stream, reports = io.BytesIO(), []
    with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_STORED) as output:
        for _, (priority, language, origin, data) in sorted(tables.items()):
            table = ui_names.StringTable(data)
            encoded = table.add(additions)
            checked = ui_names.StringTable(encoded)
            if any(checked.texts[k] != v for k, v in table.texts.items()):
                raise c.MappingError('Existing localized text changed')
            output.writestr(zipfile.ZipInfo(f'{language}/Data_Car.str', (1980, 1, 1, 0, 0, 0)), encoded)
            reports.append(dict(language=language, winning_table=origin, winning_priority=priority))
    priority = max(r['winning_priority'] for r in reports) + 1
    return stream.getvalue(), priority, dict(inputs=inputs, languages=reports, priority=priority)


def build(car, donor, out, target=c.FM4_DEFAULT, content_root=CONTENT, models=None):
    target, out = Path(target).resolve(), Path(out).resolve()
    target_root, disc = target.parents[1], target.parents[2]
    if out.exists():
        raise c.MappingError('Choose a new package directory')
    if out == disc or disc in out.parents:
        raise c.MappingError('Package output must be outside the original disc')
    models = Path(models or PROTOTYPE / car.lower())
    prototype = json.loads((models / 'report.json').read_text(encoding='utf-8'))
    if prototype['car'].casefold() != car.casefold() or prototype['donor'].casefold() != donor.casefold():
        raise c.MappingError('Prototype models were built for another car or donor')
    with closing(sqlite3.connect(f'file:{FM2_MEDIA / "DB/gamedb.slt"}?mode=ro', uri=True)) as fm2_db:
        fm2_db.row_factory = sqlite3.Row
        fm2_car = c.one(c.rows(fm2_db, 'Data_Car', 'MediaName=?', (car,)), car)
    with zipfile.ZipFile(FM2_MEDIA / 'StringTables/EN.zip') as z:
        fm2_text = ui_names.StringTable(z.read('Data_Car.str')).texts
    label = {f: fm2_text[ui_names.reference(fm2_car[f]) & 65535] + ' (FM2)' for f in ('DisplayName', 'ModelShort')}
    reserved, registry, dlc_wheels, overlays = batch_package.installed_content(content_root)
    files, reports = out / 'files', out / 'reports'
    (files / 'Media/DB').mkdir(parents=True)
    reports.mkdir()
    database = files / 'Media/DB/gamedb.slt'
    shutil.copyfile(target, database)
    fm2_zip = sv.zips(sv.FM2)[car.lower()]
    donor_zip = next(p for p in (target_root / 'Cars').glob('*.zip') if p.stem.casefold() == donor.casefold())
    inputs = {str(p): c.sha(p) for p in (target, fm2_zip, donor_zip, FM2_MEDIA / 'DB/gamedb.slt',
                                          FM2_MEDIA / 'StringTables/EN.zip', FM2_MEDIA / 'UI/Textures.zip')}
    fm2_wheel = prototype['wheel']['media']
    inputs.update({str(models / n): c.sha(models / n) for n in
                   (f'{car.lower()}.carbin', f'{car.lower()}_lod0.carbin', f'{car.lower()}_cockpit.carbin',
                    f'wheel/{fm2_wheel.lower()}.carbin')})

    # Audio: FM4 masih membawa tuning audio banyak mobil FM2/FM3; wajib ada persis untuk mobil ini.
    with zipfile.ZipFile(target_root / 'audio/Cars/CarModelTuning.zip') as z:
        if [n for n in z.namelist() if n.casefold() == (car + '_CMT.xml').casefold()] == []:
            raise c.MappingError('Native FM4 car audio tuning is unavailable')

    with closing(sqlite3.connect(database)) as work:
        work.row_factory = sqlite3.Row
        car_id = fm2_car['Id']
        if c.rows(work, 'Data_Car', 'Id=? OR lower(MediaName)=lower(?)', (car_id, car)) or \
                car_id in reserved.get('Data_Car', ()):
            raise c.MappingError('The FM2 car identity already exists in FM4 or an installed DLC')
        graph, nodes, rows = clone_stock(work, donor, car, car_id, fm2_car['Year'], reserved)
        # Velg stock: baris List_Wheels donor (massa dan offset rem tetap donor), model dan tekstur FM2.
        if batch_package.native_wheel(target_root, dlc_wheels, fm2_wheel) is not None or                 (disc / WHEELS / (fm2_wheel + '.zip')).exists():
            raise c.MappingError('FM4 already ships a wheel folder with the FM2 wheel name')
        nodes['wheel']['row']['MediaName'] = fm2_wheel
        tables, _ = ui_names.winning_tables(target_root, content_root, archive_read, c.sha)
        taken = {k for _, _, _, data in tables.values() for k in ui_names.StringTable(data).texts}
        keys = names(car_id, label, taken)
        for field, key in keys.items():
            nodes['car']['row'][field] = key['reference']
        with work:
            inserted = integration.insert_rows(work, rows)
        replay = c.extract_stock(work, car)['nodes']
        if {r: n['row'] for r, n in replay.items()} != {r: n['row'] for r, n in nodes.items()}:
            raise c.MappingError('Package database does not reproduce the cloned stock graph')
        if work.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise c.MappingError('Package database failed integrity_check')
        wheel = nodes['wheel']['row']['MediaName']
        car_row = dict(nodes['car']['row'])

    payloads, origin, skipped = assets(car, donor, models, fm2_zip, donor_zip, wheel)
    source_payloads = dict(payloads)
    payloads, paint = appearance_audit.with_cockpit_paint_scales(payloads, car)
    appearance = appearance_audit.audit(source_payloads, payloads, target_root, car, wheel, archive_read)
    inputs.update(appearance['inputs'])
    for model in ('', '_lod0', '_cockpit'):
        carbin_audit.parse(payloads[CARS / car / f'{car.lower()}{model}.carbin'], 'FM4')

    with zipfile.ZipFile(target_root / 'UI/Textures.zip') as z:
        controls = [archive_read(z, f'Thumbnails/Thumbnail_{n}.xds') for n in (1002, 1003, 1305)]
    if len({b[:52] for b in controls}) != 1:
        raise c.MappingError('Native thumbnail control headers disagree')
    with zipfile.ZipFile(FM2_MEDIA / 'UI/Textures.zip') as z:
        thumb, thumb_report = thumbnail(z.read(f'Thumbnails/Thumbnail_{car_id}.xds'), controls[0])

    strings, priority, string_report = string_archive(target_root, content_root, keys)
    inputs.update(string_report.pop('inputs'))
    archives = {CARS / (car + '.zip'): integration.stored_zip(payloads, CARS / car),
                WHEELS / (wheel + '.zip'): integration.stored_zip(payloads, WHEELS / wheel),
                THUMBNAILS.with_suffix('.zip'): integration.stored_zip(
                    {THUMBNAILS / f'Thumbnail_{car_id}.xds': thumb}, THUMBNAILS),
                ui_names.OVERRIDE: strings}
    for relative in archives:
        if (disc / relative).exists():
            raise c.MappingError(f'Refusing to replace an existing asset: {relative}')
    manifest_data = integration.extend_zip_manifest((target_root / 'zipmanifest.xml').read_bytes(), archives, (),
                                                    {ui_names.OVERRIDE: priority})
    for relative, data in {**archives, Path('Media/zipmanifest.xml'): manifest_data}.items():
        (files / relative).parent.mkdir(parents=True, exist_ok=True)
        with (files / relative).open('xb') as f:
            f.write(data)
    for path, digest in inputs.items():
        if c.sha(path) != digest:
            raise c.MappingError(f'Input changed during packaging: {path}')

    class_id, pi = car_row['ClassID'], car_row['PerformanceIndex']
    c.dump(reports / 'database.json', dict(donor=donor, car_id=car_id, inserted_rows=inserted,
                                           allocation={r: [n['table'], n['row'][n['pk']]] for r, n in nodes.items()},
                                           presentation_rows=[r for r in rows if r['table'] in PRESENTATION],
                                           names=keys, car=car_row))
    c.dump(reports / 'assets.json', dict(origin=origin, sha256={k.as_posix(): sha(v) for k, v in payloads.items()},
                                         fm2_files_not_shipped=skipped, cockpit_paint_scales=paint))
    c.dump(reports / 'appearance_validation.json', appearance)
    c.dump(reports / 'ui_thumbnail_validation.json', thumb_report)
    c.dump(reports / 'ui_name_validation.json', string_report)
    manifest = {
        'package_type': 'Offline file overlay; not a complete game disc',
        'cars': [dict(media=car, status='packaged', car_id=car_id, names=label, wheel=wheel,
                      wheel_source='converted_fm2', donor=donor, class_id=class_id, performance_index=pi,
                      requires=[])],
        'packaged': 1, 'failed': 0, 'requires': [], 'inputs': inputs, 'sources_unchanged': True,
        'overlays_checked': len(overlays), 'content_root': str(content_root),
        'donor_values': ['physics', 'class', 'performance_index', 'List_Wheels row except MediaName', 'CarPartPositions',
                         'CameraOverrides', 'CarExceptions', 'Combo_Colors', 'calipers', 'rotors',
                         '_lod0/_cockpit headers'],
        'merged_database_sha256': c.sha(database), 'zip_manifest_sha256': c.sha(files / 'Media/zipmanifest.xml'),
        'archives': {p.as_posix(): sha(d) for p, d in archives.items()},
        'installed': False, 'accepted': False, 'runtime_tested': False,
        'files': {p.relative_to(files).as_posix(): c.sha(p) for p in files.rglob('*') if p.is_file()},
    }
    c.dump(out / 'manifest.json', manifest)
    return manifest, appearance


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('car')
    p.add_argument('--donor', required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--fm4', type=Path, default=c.FM4_DEFAULT)
    p.add_argument('--content-root', type=Path, default=CONTENT)
    p.add_argument('--models', type=Path, help='keluaran prototype_fm4_model.py (default outputs/car-fm2-prototype-2026-11-03/<car>)')
    a = p.parse_args()
    manifest, appearance = build(a.car, a.donor, a.out, a.fm4, a.content_root, a.models)
    print(json.dumps(dict(car=manifest['cars'][0], techniques=appearance['techniques'],
                          unknown_techniques=appearance['techniques_without_effect_native_precedent'],
                          absent_textures=appearance['absent_textures_with_native_precedent'],
                          files=len(manifest['files'])), indent=1))


if __name__ == '__main__':
    main()
