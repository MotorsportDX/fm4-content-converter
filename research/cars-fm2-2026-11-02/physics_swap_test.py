"""Paket uji fisika FM2 pada mobil yang juga ada di FM4 (REPORT bagian 12).

Graf stock mobil FM4 native ditimpa di tempat oleh `physics_fm2.apply` dengan nilai FM2 mobil yang
sama; mobil itu sendiri menjadi "donor", sehingga grup yang di studi tetap donor bernilai FM4 asli.
Model, tekstur, audio, nama, PerformanceIndex dan ClassID tetap native: lawan di grid Quick Race
sama, dan run FM4 asli melawan run "dari FM2" hanya berbeda pada fisika.

Baris graf yang juga dipakai mobil drivable lain (mis. velg bersama) tidak boleh berubah; bila
`apply` mengubahnya, paket ditolak. Hanya `Media/DB/gamedb.slt` yang ditimpa.

  python research/cars-fm2-2026-11-02/physics_swap_test.py NIS_SkylineGTRVSpecII_02 --out <paket-baru>
"""
from contextlib import closing
from pathlib import Path
import argparse, copy, json, shutil, sqlite3, sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import physics_fm2
from package_fm2_test import free_key
from fm4_converter.fm3 import batch_package, integration
from fm4_converter.fm3 import converter as c
from package_fm2_test import CONTENT

STUDY = physics_fm2.OUT / 'study.json'


def shared_rows(db, media):
    """(tabel, kunci) graf stock `media` yang juga ada di graf mobil drivable lain."""
    own = {(n['table'], n['row'][n['pk']]) for n in c.extract_stock(db, media)['nodes'].values()}
    shared = set()
    for (other,) in db.execute('SELECT MediaName FROM Data_Car WHERE IsDrivable=1 AND MediaName<>?', (media,)):
        try:
            nodes = c.extract_stock(db, other)['nodes'].values()
        except c.MappingError:
            continue
        shared |= own & {(n['table'], n['row'][n['pk']]) for n in nodes}
    return shared


def build(media, out, target=c.FM4_DEFAULT, study=STUDY, content_root=CONTENT):
    out = Path(out).resolve()
    if out.exists():
        raise c.MappingError('Choose a new package directory')
    study_data = json.loads(Path(study).read_text(encoding='utf-8'))
    (out / 'files/Media/DB').mkdir(parents=True)
    database = out / 'files/Media/DB/gamedb.slt'
    shutil.copyfile(target, database)
    reserved = batch_package.installed_content(content_root)[0]
    with closing(c.connect(physics_fm2.FM2_DB)) as fm2, closing(sqlite3.connect(database)) as work:
        work.row_factory = sqlite3.Row
        car_id = c.one(c.rows(work, 'Data_Car', 'MediaName=?', (media,)), media)['Id']
        fm2_car = c.one(c.rows(fm2, 'Data_Car', 'Id=? AND MediaName=?', (car_id, media)), f'FM2 {media}')
        source = physics_fm2.extract(fm2, fm2_car['Id'], work)
        native = c.extract_stock(work, media)['nodes']
        nodes = copy.deepcopy(native)
        log = physics_fm2.apply(nodes, source, study_data, work)
        car = nodes['car']['row']
        log['class_kept_native'] = {'computed': {k: car[k] for k in ('PerformanceIndex', 'ClassID')},
                                    'native': {k: native['car']['row'][k] for k in ('PerformanceIndex', 'ClassID')}}
        car.update(log['class_kept_native']['native'])
        shared = shared_rows(work, media)
        touched = {(native[r]['table'], native[r]['row'][native[r]['pk']]) for r in native
                   if r in log['removed_roles'] or nodes.get(r, {}).get('row') != native[r]['row']}
        if touched & shared:
            raise c.MappingError(f'FM2 physics would change rows shared with other cars: {sorted(touched & shared)}')
        added = []
        with work:
            for role in log['removed_roles']:
                n = native[role]
                work.execute(f'DELETE FROM {c.qi(n["table"])} WHERE {c.qi(n["pk"])}=?', (n['row'][n['pk']],))
                nodes.pop(role)
            for role, node in nodes.items():
                if role in log['added_roles']:
                    node['row'][node['pk']] = free_key(work, node['table'], node['pk'], reserved, added)
                    added.append({'table': node['table'], 'row': node['row']})
                elif node['row'] != native[role]['row']:
                    columns = [k for k in node['row'] if k != node['pk']]
                    work.execute(f'UPDATE {c.qi(node["table"])} SET ' + ','.join(f'{c.qi(k)}=?' for k in columns) +
                                 f' WHERE {c.qi(node["pk"])}=?',
                                 [node['row'][k] for k in columns] + [node['row'][node['pk']]])
            integration.insert_rows(work, added)
        replay = c.extract_stock(work, media)['nodes']
        if {r: n['row'] for r, n in replay.items()} != {r: n['row'] for r, n in nodes.items()}:
            raise c.MappingError('Package database does not reproduce the FM2 physics graph')
        if work.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise c.MappingError('Package database failed integrity_check')
    (out / 'reports').mkdir()
    c.dump(out / 'reports/physics.json', log)
    manifest = {'package_type': 'Offline file overlay; FM2 physics on a native FM4 car, not for distribution',
                'car': media, 'car_id': car_id, 'study': str(study), 'changed': len(log['changed']),
                'removed_roles': log['removed_roles'], 'added_roles': log['added_roles'],
                'class_kept_native': log['class_kept_native'], 'shared_rows_untouched': len(shared),
                'inputs': {str(p): c.sha(p) for p in (target, physics_fm2.FM2_DB, study)},
                'files': {'Media/DB/gamedb.slt': c.sha(database)}, 'runtime_tested': False}
    c.dump(out / 'manifest.json', manifest)
    return manifest


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('car')
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--fm4', type=Path, default=c.FM4_DEFAULT)
    p.add_argument('--study', type=Path, default=STUDY)
    p.add_argument('--content-root', type=Path, default=CONTENT)
    a = p.parse_args()
    m = build(a.car, a.out, a.fm4, a.study, a.content_root)
    print(json.dumps({k: m[k] for k in ('car', 'changed', 'removed_roles', 'added_roles', 'class_kept_native',
                                        'shared_rows_untouched')}, indent=1))


if __name__ == '__main__':
    main()
