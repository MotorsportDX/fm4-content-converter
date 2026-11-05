"""FM2 downloadable content from the Bonus Disc, laid out as the FM2 disc's Media folder.

The Bonus Disc carries the FM2 DLC as STFS packages (`archives.stfs_reader`). Each car pack holds
DLC<n>_pri_<p>.zip with media/cars/<car>/, media/wheels/<wheel>/, media/UI/Textures/Thumbnails/ and
database patches in media/db/patch/, plus DLC<n>Overrides1_pri_<p>.zip with the cumulative
Data_Car.str string tables. This module writes:

  <out>/Media/DB/gamedb.slt              FM2 disc database + every <n>_merge.slt and <n>_execute.sql
                                         patch, in order of <n> as the game applies them
  <out>/Media/cars/<car>.zip             one archive per DLC car, members relative to the car folder
  <out>/Media/wheels/<wheel>.zip         as the disc's wheel archives
  <out>/Media/UI/Textures.zip            Thumbnails/Thumbnail_<Id>.xds of the DLC cars
  <out>/Media/StringTables/EN.zip        Data_Car.str of the highest-priority override

A merge patch has the disc's schema and adds its rows, skipping rows the database already has (`merge`).
An execute patch is SQL run as it is: it sets IsPurchased, fills StockGarage, adds CarExceptions or
deletes the SplitPoints that the next merge replaces (39999 before 40000). `sources` reads this
folder next to the disc. Only reads the disc.

  python -m fm4_converter.fm2.dlc [--bonus-disc <root>] [--out <new folder>]
"""
from contextlib import closing
from pathlib import Path
import argparse, io, json, re, shutil, sqlite3, zipfile

from . import sources
from ..archives.stfs_reader import STFS
from ..fm3 import converter as c

PACKAGES = Path('content/0000000000000000/FFED2000/FFFFFFFF')
ARCHIVE = re.compile(r'Media/DLCZips/(?P<name>[^/]+)_pri_(?P<priority>\d+)\.zip$')
PATCH = re.compile(r'media/db/patch/(?P<order>\d+)_(?P<kind>merge\.slt|execute\.sql)$', re.I)
STAMP = (1980, 1, 1, 0, 0, 0)


def archives(bonus_disc):
    """[(package display name, archive name, priority, ZipFile)] of every DLC archive."""
    out = []
    for path in sorted((Path(bonus_disc) / PACKAGES).iterdir()):
        with STFS(path) as package:
            for entry in package.entries:
                match = ARCHIVE.fullmatch(entry['name'])
                if entry['directory'] or match is None:
                    continue
                data = package.read(entry, limit=512 << 20)
                out.append((package.meta['display_name'], match['name'], int(match['priority']),
                            zipfile.ZipFile(io.BytesIO(data))))
    return out


def folders(z, kind):
    """{folder name: {member path relative to the folder: bytes}} under media/<kind>/."""
    out = {}
    for name in z.namelist():
        parts = name.split('/')
        if len(parts) > 3 and parts[0].lower() == 'media' and parts[1].lower() == kind and parts[-1]:
            out.setdefault(parts[2], {})['/'.join(parts[3:])] = z.read(name)
    return out


def stored(members):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_STORED) as z:
        for name, data in sorted(members.items()):
            z.writestr(zipfile.ZipInfo(name, STAMP), data)
    return stream.getvalue()


def merge(database, patch):
    """Rows of `patch` (same schema as `database`) not already in it; {table: rows added}. FM2 tables
    have no primary key, and every pack repeats shared rows (e.g. AeroPhysicsID 1), so a row is
    added only when no identical row exists. A key that ends up with two different rows is refused
    (`key_conflicts`)."""
    counts = {}
    with closing_db(patch) as source:
        for table, in source.execute("SELECT name FROM sqlite_master WHERE type='table'"):
            columns = [r[1] for r in source.execute(f'PRAGMA table_info({c.qi(table)})')]
            target = [r[1] for r in database.execute(f'PRAGMA table_info({c.qi(table)})')]
            if columns != target:
                raise c.MappingError(f'Patch table {table} does not have the disc schema')
            present = set(database.execute(f'SELECT * FROM {c.qi(table)}'))
            rows = [r for r in dict.fromkeys(source.execute(f'SELECT * FROM {c.qi(table)}')) if r not in present]
            if rows:
                database.executemany(f'INSERT INTO {c.qi(table)} VALUES ({",".join("?" * len(columns))})', rows)
                counts[table] = len(rows)
    return counts


def key_conflicts(database, base):
    """Tables whose first column is unique on the disc but not after the merge: {table: [keys]}."""
    out = {}
    with closing_db(base) as disc:
        for table, in disc.execute("SELECT name FROM sqlite_master WHERE type='table'"):
            key = next(r[1] for r in disc.execute(f'PRAGMA table_info({c.qi(table)})'))
            q = f'SELECT {c.qi(key)} FROM {c.qi(table)} GROUP BY {c.qi(key)} HAVING COUNT(*) > 1'
            if disc.execute(q).fetchone() is None:
                dup = [r[0] for r in database.execute(q)]
                if dup:
                    out[table] = dup
    return out


def closing_db(path):
    return closing(sqlite3.connect(f'file:{path}?mode=ro', uri=True))


def build(out=None, bonus_disc=None, base_db=None):
    """None: the `sources` locations at call time."""
    out = Path(out or sources.FM2_DLC.parent).resolve()
    bonus_disc, base_db = bonus_disc or sources.FM2_BONUS_DISC, base_db or sources.FM2_DB
    if out.exists():
        raise c.MappingError('Choose a new output folder')
    media = out / 'Media'
    for folder in ('DB', 'cars', 'wheels', 'UI', 'StringTables'):
        (media / folder).mkdir(parents=True)
    found = archives(bonus_disc)
    database = media / 'DB/gamedb.slt'
    shutil.copyfile(base_db, database)
    patches, cars, wheels, thumbnails, strings = [], {}, {}, {}, None
    work = Path(out) / 'patches'
    work.mkdir()
    for pack, name, priority, z in found:
        for member in z.namelist():
            match = PATCH.fullmatch(member)
            if match:
                path = work / f'{match["order"]}_{match["kind"]}'
                path.write_bytes(z.read(member))
                patches.append((int(match['order']), pack, name, path))
            elif member.lower().startswith('media/ui/textures/thumbnails/') and member.lower().endswith('.xds'):
                thumbnails['Thumbnails/' + member.split('/')[-1]] = z.read(member)
        for car, members in folders(z, 'cars').items():
            if car in cars:
                raise c.MappingError(f'{car} is in two DLC archives')
            cars[car] = (pack, members)
        for wheel, members in folders(z, 'wheels').items():
            wheels.setdefault(wheel, (pack, members))
        if 'Overrides' in name and 'EN/Data_Car.str' in z.namelist() and (strings is None or priority > strings[0]):
            strings = (priority, pack, z.read('EN/Data_Car.str'))
    merged = []
    with sqlite3.connect(database) as db:
        for order, pack, name, path in sorted(patches):
            if path.suffix == '.sql':
                db.executescript(path.read_text(encoding='utf-8-sig'))
                merged.append({'order': order, 'package': pack, 'archive': name, 'executed': path.name})
            else:
                merged.append({'order': order, 'package': pack, 'archive': name, 'rows': merge(db, path)})
        conflicts = key_conflicts(db, base_db)
        if conflicts:
            raise c.MappingError(f'DLC rows conflict with other rows of the same key: {conflicts}')
        if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise c.MappingError('Merged FM2 database failed integrity_check')
    shutil.rmtree(work)
    for car, (pack, members) in cars.items():
        (media / 'cars' / f'{car}.zip').write_bytes(stored(members))
    for wheel, (pack, members) in wheels.items():
        (media / 'wheels' / f'{wheel}.zip').write_bytes(stored(members))
    (media / 'UI/Textures.zip').write_bytes(stored(thumbnails))
    if strings is None:
        raise c.MappingError('No DLC string override')
    (media / 'StringTables/EN.zip').write_bytes(stored({'Data_Car.str': strings[2]}))
    report = {'bonus_disc': str(bonus_disc), 'base_database': str(base_db), 'base_database_sha256': c.sha(base_db),
              'merged': merged, 'strings': {'package': strings[1], 'priority': strings[0]},
              'cars': {car: pack for car, (pack, _) in sorted(cars.items())},
              'wheels': sorted(wheels), 'thumbnails': sorted(thumbnails),
}
    c.dump(out / 'report.json', report)
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--bonus-disc', type=Path, default=sources.FM2_BONUS_DISC)
    p.add_argument('--out', type=Path, default=sources.FM2_DLC.parent, help='new folder')
    a = p.parse_args()
    report = build(a.out, a.bonus_disc)
    print(json.dumps({k: report[k] for k in ('cars', 'merged')}, indent=1))


if __name__ == '__main__':
    main()
