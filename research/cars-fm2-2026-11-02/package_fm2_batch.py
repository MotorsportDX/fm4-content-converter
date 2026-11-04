"""Satu paket overlay uji FM4 berisi semua mobil FM2-only (REPORT bagian 14).

Per mobil sama dengan package_fm2_test.py (model prototype_fm4_model.py, tekstur dan thumbnail FM2,
graf stock donor dengan fisika FM2 dari study.json), tetapi semua mobil ditulis ke SATU database,
satu Data_Car.str per bahasa, satu atlas thumbnail, dan satu zipmanifest, seperti
`fm3.batch_package`. Mobil direncanakan berurutan terhadap database paket yang terus bertambah,
jadi kunci baru tidak bertabrakan; kunci DLC terpasang tetap dicadangkan.

Berbeda dari paket satu mobil:
- Donor dipilih `physics_fm2.donor` (merek dan penggerak sama, massa dan tenaga terdekat) dari
  mobil disc FM4 yang punya _lod0, _cockpit, serta empat kaliper dan rotor. Model dibuat ulang
  dengan donor itu bila belum ada.
- `MakeID` FM2 dipakai bila FM4 atau DLC terpasang punya merek dengan ID dan kode pabrikan yang
  sama (DLC dicatat di `requires`); bila tidak, merek donor tetap dan dicatat.
- Velg yang sudah dikirim FM4 dipakai apa adanya; velg yang dipakai beberapa mobil FM2 dikirim
  sekali.
- Audio: `<car>_CMT.xml` native bila ada. Bila tidak, CMT donor disalin dengan nama mobil ke
  `Media/audio/Cars.zip` (mount `audio\\cars`, entri `CarModelTuning/<car>_CMT.xml`) dengan
  prioritas di atas `carmodeltuning.zip`, pola yang sama dengan `Media/stringtables.zip`.
  Suara mesin tetap milik `Data_Engine` donor.

Mobil yang gagal dicatat beserta alasannya; mobil lain tetap dipaketkan.

  python research/cars-fm2-2026-11-02/package_fm2_batch.py --out <paket-baru>
"""
from contextlib import closing
from pathlib import Path
import argparse, json, shutil, sqlite3, subprocess, sys, traceback, zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import physics_fm2
import prototype_fm4_model as pm
import survey_carbin as sv
from package_fm2_test import (CARS, CONTENT, FM2_MEDIA, PRESENTATION, THUMBNAILS, WHEELS, assets, clone_stock,
                              free_key, names, sha, string_archive, thumbnail)
from fm4_converter.fm3 import appearance_audit, batch_package, carbin_audit, integration, ui_names
from fm4_converter.archives import forza_zip
from fm4_converter.fm3 import converter as c
from fm4_converter.fm3.integration import archive_read
from fm4_converter.paths import PROJECT_ROOT

OUT = PROJECT_ROOT / 'outputs/car-fm2-batch-2026-11-04'
INVENTORY = PROJECT_ROOT / 'outputs/car-fm2-research-2026-11-02/inventory.json'
STUDY = physics_fm2.OUT / 'study.json'
AUDIO = Path('Media/audio/Cars.zip')
AUDIO_ROOT = Path('Media/audio/Cars')
AUDIO_PRIORITY = 96   # carmodeltuning.zip dipasang pada prioritas 95


def fm2_only():
    inventory = json.loads(INVENTORY.read_text(encoding='utf-8'))
    return [x['MediaName'] for x in inventory['cars'] if x['route'] == 'fm2_only']


def donor_pool(fm4):
    """Mobil disc FM4 yang bisa menjadi donor: header _lod0/_cockpit, empat kaliper dan rotor."""
    discs = {q.stem.casefold(): q for q in pm.FM4.glob('*.zip')}

    def usable(media):
        path = discs.get(media.casefold())
        if path is None:
            return False
        with zipfile.ZipFile(path) as z:
            members = [i.filename.lower() for i in z.infolist()]
            own = [m for m in members if m.startswith(media.lower() + '_')]
            if not ({f'{media.lower()}_lod0.carbin', f'{media.lower()}_cockpit.carbin'} <= set(members) and
                    sum('_caliper' in m for m in own) == 4 and sum('_rotor' in m for m in own) == 4):
                return False
            # Header close-up donor disalin ke model; AUD_2_R15TDI_09 punya float tak hingga di sana.
            try:
                for kind in ('lod0', 'cockpit'):
                    carbin_audit.parse(forza_zip.read(z, f'{media.lower()}_{kind}.carbin'), 'FM4')
            except carbin_audit.FormatError:
                return False
        return True
    return [d for d in physics_fm2.fm4_index(fm4) if usable(d['media'])]


def models_for(car, donor, root):
    """Folder prototype_fm4_model.py untuk (car, donor); dibuat bila belum ada."""
    folder = root / f'{car.lower()}--{donor.lower()}'
    if not (folder / 'report.json').exists():
        if folder.exists():
            shutil.rmtree(folder)
        result = subprocess.run([sys.executable, str(Path(pm.__file__)), car, '--donor', donor, '--out', str(folder)],
                                capture_output=True, text=True)
        if result.returncode:
            raise c.MappingError('prototype_fm4_model failed: ' + result.stderr.strip().splitlines()[-1])
    return folder


def make_for(fm2_db, work, registry, fm2_make):
    """(MakeID, asal) bila FM4 atau DLC terpasang punya merek FM2 yang sama; (None, alasan) bila tidak."""
    code = fm2_db.execute('SELECT ManufacturerCode FROM List_CarMake WHERE ID=?', (fm2_make,)).fetchone()[0]
    row = work.execute('SELECT ManufacturerCode FROM List_CarMake WHERE ID=?', (fm2_make,)).fetchone()
    if row is not None:
        return (fm2_make, None) if row[0] == code else (None, f'FM4 make {fm2_make} is {row[0]}, FM2 {code}')
    for origin, dlc in registry.get('List_CarMake', ()):
        if dlc['ID'] == fm2_make and dlc['ManufacturerCode'] == code:
            return fm2_make, origin
    return None, f'no FM4 make {code}'


def build(out, cars=None, target=c.FM4_DEFAULT, content_root=CONTENT, study=STUDY, models_root=OUT / 'models'):
    target, out = Path(target).resolve(), Path(out).resolve()
    target_root, disc = target.parents[1], target.parents[2]
    if out.exists():
        raise c.MappingError('Choose a new package directory')
    if out == disc or disc in out.parents:
        raise c.MappingError('Package output must be outside the original disc')
    study_data = json.loads(Path(study).read_text(encoding='utf-8'))
    reserved, registry, dlc_wheels, overlays = batch_package.installed_content(content_root)
    files, reports = out / 'files', out / 'reports'
    (files / 'Media/DB').mkdir(parents=True)
    reports.mkdir()
    database = files / 'Media/DB/gamedb.slt'
    shutil.copyfile(target, database)
    fm2_zips = sv.zips(sv.FM2)
    inputs = {str(p): c.sha(p) for p in (target, physics_fm2.FM2_DB, study, FM2_MEDIA / 'StringTables/EN.zip',
                                          FM2_MEDIA / 'UI/Textures.zip', target_root / 'audio/Cars/CarModelTuning.zip')}
    with zipfile.ZipFile(FM2_MEDIA / 'StringTables/EN.zip') as z:
        fm2_text = ui_names.StringTable(z.read('Data_Car.str')).texts
    with zipfile.ZipFile(target_root / 'audio/Cars/CarModelTuning.zip') as z:
        tuning = {i.filename.casefold(): archive_read(z, i) for i in z.infolist()}
    with zipfile.ZipFile(target_root / 'UI/Textures.zip') as z:
        controls = [archive_read(z, f'Thumbnails/Thumbnail_{n}.xds') for n in (1002, 1003, 1305)]
    if len({b[:52] for b in controls}) != 1:
        raise c.MappingError('Native thumbnail control headers disagree')

    payloads, origins, keys, thumbs, audio, shipped_wheels = {}, {}, {}, {}, {}, {}
    packaged, failed = [], []
    with closing(c.connect(physics_fm2.FM2_DB)) as fm2_db, closing(sqlite3.connect(database)) as work:
        work.row_factory = sqlite3.Row
        pool = donor_pool(work)
        tables, _ = ui_names.winning_tables(target_root, content_root, archive_read, c.sha)
        taken = {k for _, _, _, data in tables.values() for k in ui_names.StringTable(data).texts}
        for car in cars or fm2_only():
            log, car_keys = {'media': car}, {}
            try:
                fm2_car = c.one(c.rows(fm2_db, 'Data_Car', 'MediaName=?', (car,)), f'FM2 {car}')
                car_id = fm2_car['Id']
                if car.lower() not in fm2_zips:
                    raise c.MappingError('No FM2 car archive on the disc')
                if c.rows(work, 'Data_Car', 'Id=? OR lower(MediaName)=lower(?)', (car_id, car)) or \
                        car_id in reserved.get('Data_Car', ()):
                    raise c.MappingError('The FM2 car identity already exists in FM4 or an installed DLC')
                source = physics_fm2.extract(fm2_db, car_id, work)
                donor = physics_fm2.donor(pool, source, car_id)['media']
                log['donor'] = donor
                models = models_for(car, donor, Path(models_root))
                prototype = json.loads((models / 'report.json').read_text(encoding='utf-8'))
                requires = set()

                graph, nodes, rows = clone_stock(work, donor, car, car_id, fm2_car['Year'], reserved)
                # FM4 menyimpan baris TireMod_FrictionScale yatim untuk beberapa Id (Ordinal 288 = Camaro
                # SS FM2); extract_stock mengikatnya ke mobil dengan Id itu, jadi baris itu ikut graf.
                orphans = {}
                if 'tire.modifier' not in nodes:
                    found = c.rows(work, 'TireMod_FrictionScale', 'Ordinal=?', (car_id,))
                    if found:
                        orphans['tire.modifier'] = dict(found[0])
                        nodes['tire.modifier'] = {'table': 'TireMod_FrictionScale', 'pk': 'Ordinal',
                                                  'row': dict(found[0])}
                        log['existing_rows'] = {'tire.modifier': dict(found[0])}
                make, why = make_for(fm2_db, work, registry, fm2_car['MakeID'])
                if make is None:
                    log['make'] = {'kept_donor': nodes['car']['row']['MakeID'], 'reason': why}
                else:
                    nodes['car']['row']['MakeID'] = make
                    log['make'] = {'fm2': make, 'requires': why}
                    if why:
                        requires.add(why)
                physics = physics_fm2.apply(nodes, source, study_data, work)
                removed = {id(nodes.pop(role)['row']) for role in physics['removed_roles']}
                rows = [r for r in rows if id(r['row']) not in removed]
                for role in physics['added_roles']:
                    node = nodes[role]
                    node['row'][node['pk']] = free_key(work, node['table'], node['pk'], reserved, rows)
                    rows.append({'table': node['table'], 'row': node['row']})

                # Velg: FM4 (disc atau DLC terpasang), mobil lain di paket ini, atau velg FM2 hasil konversi.
                wheel = prototype['wheel']['media']
                nodes['wheel']['row']['MediaName'] = wheel
                native = batch_package.native_wheel(target_root, dlc_wheels, wheel)
                if native is not None:
                    wheel_origin, references = native
                    log['wheel'] = 'native_fm4' if wheel_origin is None else 'installed_dlc'
                    if wheel_origin:
                        requires.add(wheel_origin)
                elif wheel.casefold() in shipped_wheels:
                    references, log['wheel'] = shipped_wheels[wheel.casefold()], 'shared_in_package'
                else:
                    references, log['wheel'] = None, 'converted_fm2'

                label = {f: fm2_text[ui_names.reference(fm2_car[f]) & 65535] + ' (FM2)'
                         for f in ('DisplayName', 'ModelShort')}
                car_keys = names(car_id, label, taken)
                for field, key in car_keys.items():
                    nodes['car']['row'][field] = key['reference']

                donor_zip = next(p for p in pm.FM4.glob('*.zip') if p.stem.casefold() == donor.casefold())
                car_payloads, origin, skipped = assets(car, donor, models, fm2_zips[car.lower()], donor_zip,
                                                       wheel if log['wheel'] == 'converted_fm2' else None)
                source_payloads = dict(car_payloads)
                car_payloads, paint = appearance_audit.with_cockpit_paint_scales(car_payloads, car)
                appearance = appearance_audit.audit(source_payloads, {**(references or {}), **car_payloads},
                                                    target_root, car, wheel, archive_read)
                for model in ('', '_lod0', '_cockpit'):
                    carbin_audit.parse(car_payloads[CARS / car / f'{car.lower()}{model}.carbin'], 'FM4')
                with zipfile.ZipFile(FM2_MEDIA / 'UI/Textures.zip') as z:
                    thumb, thumb_report = thumbnail(z.read(f'Thumbnails/Thumbnail_{car_id}.xds'), controls[0])

                if (car + '_CMT.xml').casefold() in tuning:
                    log['audio'] = 'native_fm4'
                else:
                    audio[AUDIO_ROOT / 'CarModelTuning' / f'{car}_CMT.xml'] = tuning[(donor + '_CMT.xml').casefold()]
                    log['audio'] = f'donor {donor}_CMT.xml'

                with work:
                    inserted = integration.insert_rows(work, rows)
                    for role, before in orphans.items():
                        node = nodes[role]
                        if node['row'] != before:
                            columns = [k for k in node['row'] if k != node['pk']]
                            work.execute(f'UPDATE {c.qi(node["table"])} SET ' +
                                         ','.join(f'{c.qi(k)}=?' for k in columns) + f' WHERE {c.qi(node["pk"])}=?',
                                         [node['row'][k] for k in columns] + [node['row'][node['pk']]])
                    replay = c.extract_stock(work, car)['nodes']
                    if {r: n['row'] for r, n in replay.items()} != {r: n['row'] for r, n in nodes.items()}:
                        raise c.MappingError('Package database does not reproduce the planned stock graph')
            except Exception as error:   # noqa: BLE001 - satu mobil gagal tidak menghentikan paket
                taken.difference_update(ui_names.reference(k['reference']) & 65535 for k in car_keys.values())
                failed.append({**log, 'error': f'{type(error).__name__}: {error}',
                               'trace': traceback.format_exc().splitlines()[-3:]})
                print('FAILED', car, failed[-1]['error'], flush=True)
                continue
            payloads.update(car_payloads)
            origins.update(origin)
            if log['wheel'] == 'converted_fm2':
                shipped_wheels[wheel.casefold()] = {p: d for p, d in car_payloads.items() if p.is_relative_to(WHEELS / wheel)}
            thumbs[THUMBNAILS / f'Thumbnail_{car_id}.xds'] = thumb
            keys.update({f'{car}/{f}': k for f, k in car_keys.items()})
            car_row = dict(nodes['car']['row'])
            entry = {**log, 'status': 'packaged', 'car_id': car_id, 'names': label, 'wheel_media': wheel,
                     'class_id': car_row['ClassID'], 'performance_index': car_row['PerformanceIndex'],
                     'pi_rule': next((e.get('rule') for e in physics['changed'] if e['column'] == 'PerformanceIndex'),
                                     'donor'),
                     'physics': {'changed': len(physics['changed']), 'removed_roles': physics['removed_roles'],
                                 'added_roles': physics['added_roles']},
                     'requires': sorted(requires), 'merged_rows': inserted}
            packaged.append(entry)
            car_reports = reports / 'cars' / car
            car_reports.mkdir(parents=True)
            c.dump(car_reports / 'physics.json', physics)
            c.dump(car_reports / 'database.json', dict(donor=donor, car=car_row, names=car_keys,
                                                       allocation={r: [n['table'], n['row'][n['pk']]]
                                                                   for r, n in nodes.items()},
                                                       presentation_rows=[r for r in rows if r['table'] in PRESENTATION]))
            c.dump(car_reports / 'appearance_validation.json', appearance)
            c.dump(car_reports / 'ui_thumbnail_validation.json', thumb_report)
            c.dump(car_reports / 'assets.json', dict(origin=origin, fm2_files_not_shipped=skipped,
                                                     cockpit_paint_scales=paint))
            inputs.update(appearance['inputs'])
            print('packaged', car, donor, log['wheel'], log['audio'], car_row['ClassID'], flush=True)
        if work.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise c.MappingError('Package database failed integrity_check')

    if not packaged:
        raise c.MappingError('No car could be packaged')
    strings, priority, string_report = string_archive(target_root, content_root, keys)
    inputs.update(string_report.pop('inputs'))
    archives = {CARS / (e['media'] + '.zip'): integration.stored_zip(payloads, CARS / e['media']) for e in packaged}
    archives.update({WHEELS / (w + '.zip'): integration.stored_zip(payloads, WHEELS / w)
                     for w in {e['wheel_media'] for e in packaged if e['wheel'] == 'converted_fm2'}})
    archives[THUMBNAILS.with_suffix('.zip')] = integration.stored_zip(thumbs, THUMBNAILS)
    archives[ui_names.OVERRIDE] = strings
    priorities = {ui_names.OVERRIDE: priority}
    if audio:
        archives[AUDIO] = integration.stored_zip(audio, AUDIO_ROOT)
        priorities[AUDIO] = AUDIO_PRIORITY
    for relative in archives:
        if (disc / relative).exists():
            raise c.MappingError(f'Refusing to replace an existing asset: {relative}')
    manifest_data = integration.extend_zip_manifest((target_root / 'zipmanifest.xml').read_bytes(), archives, (),
                                                    priorities)
    for relative, data in {**archives, Path('Media/zipmanifest.xml'): manifest_data}.items():
        (files / relative).parent.mkdir(parents=True, exist_ok=True)
        with (files / relative).open('xb') as f:
            f.write(data)
    for path, digest in inputs.items():
        if c.sha(path) != digest:
            raise c.MappingError(f'Input changed during packaging: {path}')
    c.dump(reports / 'ui_name_validation.json', string_report)
    c.dump(reports / 'failed.json', failed)
    manifest = {
        'package_type': 'Offline file overlay; not a complete game disc',
        'cars': packaged, 'failed': [{k: f[k] for k in ('media', 'error')} for f in failed],
        'packaged_count': len(packaged), 'failed_count': len(failed),
        'requires': sorted({x for e in packaged for x in e['requires']}),
        'inputs': inputs, 'sources_unchanged': True, 'overlays_checked': len(overlays),
        'content_root': str(content_root), 'study': str(study),
        'audio_override': {'archive': AUDIO.as_posix(), 'priority': AUDIO_PRIORITY,
                           'entries': sorted(p.relative_to(AUDIO_ROOT).as_posix() for p in audio)},
        'donor_values': ['physics groups not chosen by the FM2 study', 'List_Wheels row except MediaName',
                         'CarPartPositions', 'CameraOverrides', 'CarExceptions', 'Combo_Colors', 'calipers',
                         'rotors', '_lod0/_cockpit headers', 'Data_Engine audio', 'CMT audio tuning when FM4 has none',
                         'MakeID when FM4 has no matching make'],
        'merged_database_sha256': c.sha(database), 'zip_manifest_sha256': c.sha(files / 'Media/zipmanifest.xml'),
        'archives': {p.as_posix(): sha(d) for p, d in archives.items()},
        'installed': False, 'accepted': False, 'runtime_tested': False,
        'files': {p.relative_to(files).as_posix(): c.sha(p) for p in files.rglob('*') if p.is_file()},
    }
    c.dump(out / 'manifest.json', manifest)
    return manifest


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--cars', nargs='*', help='MediaName FM2 (default: semua rute fm2_only di inventory)')
    p.add_argument('--fm4', type=Path, default=c.FM4_DEFAULT)
    p.add_argument('--content-root', type=Path, default=CONTENT)
    p.add_argument('--study', type=Path, default=STUDY)
    p.add_argument('--models-root', type=Path, default=OUT / 'models')
    a = p.parse_args()
    m = build(a.out, a.cars, a.fm4, a.content_root, a.study, a.models_root)
    print(json.dumps({k: m[k] for k in ('packaged_count', 'failed_count', 'requires', 'failed')}, indent=1))


if __name__ == '__main__':
    main()
