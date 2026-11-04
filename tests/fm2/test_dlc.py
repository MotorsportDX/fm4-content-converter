"""FM2 DLC database patches and archive layout, without game data."""
from contextlib import closing
import io
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path

from fm4_converter.fm2 import dlc
from fm4_converter.fm3 import converter as c


def connect(path):
    return closing(sqlite3.connect(path, isolation_level=None))


def database(path, rows):
    with connect(path) as db:
        db.execute('CREATE TABLE List_AeroPhysics (AeroPhysicsID INTEGER, Drag0 REAL)')
        db.executemany('INSERT INTO List_AeroPhysics VALUES (?,?)', rows)


class MergeTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.base, self.patch = Path(self.dir.name) / 'base.slt', Path(self.dir.name) / 'patch.slt'
        database(self.base, [(1, 0.3), (2, 0.4)])

    def tearDown(self):
        self.dir.cleanup()

    def test_rows_already_present_are_not_added_again(self):
        # Every FM2 pack repeats the shared aero row 1; FM2 tables have no primary key.
        database(self.patch, [(1, 0.3), (3, 0.5), (3, 0.5)])
        with connect(self.base) as db:
            self.assertEqual(dlc.merge(db, self.patch), {'List_AeroPhysics': 1})
            self.assertEqual(db.execute('SELECT * FROM List_AeroPhysics ORDER BY 1').fetchall(),
                             [(1, 0.3), (2, 0.4), (3, 0.5)])

    def test_a_key_with_two_different_rows_is_a_conflict(self):
        database(self.patch, [(2, 0.9)])
        copy = Path(self.dir.name) / 'merged.slt'
        copy.write_bytes(self.base.read_bytes())
        with connect(copy) as db:
            dlc.merge(db, self.patch)
            self.assertEqual(dlc.key_conflicts(db, self.base), {'List_AeroPhysics': [2]})

    def test_a_patch_with_another_schema_is_refused(self):
        with connect(self.patch) as db:
            db.execute('CREATE TABLE List_AeroPhysics (AeroPhysicsID INTEGER)')
        with connect(self.base) as db, self.assertRaises(c.MappingError):
            dlc.merge(db, self.patch)


class ArchiveTests(unittest.TestCase):
    def test_folders_are_relative_to_the_car_folder(self):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as z:
            for name in ('media/cars/NIS_350Z_DLC1/nis_350z_dlc1.carbin', 'media/cars/NIS_350Z_DLC1/physics/MAXData.xml',
                         'media/wheels/NIS_350Z_DLC1/wheel.xds', 'media/db/patch/10000_merge.slt'):
                z.writestr(name, name)
        z = zipfile.ZipFile(stream)
        self.assertEqual(sorted(dlc.folders(z, 'cars')['NIS_350Z_DLC1']), ['nis_350z_dlc1.carbin', 'physics/MAXData.xml'])
        self.assertEqual(list(dlc.folders(z, 'wheels')), ['NIS_350Z_DLC1'])
        self.assertEqual(sorted(zipfile.ZipFile(io.BytesIO(dlc.stored({'b': b'2', 'a': b'1'}))).namelist()), ['a', 'b'])

    def test_patch_names(self):
        self.assertEqual(dlc.PATCH.fullmatch('media/db/patch/39999_execute.sql')['order'], '39999')
        self.assertEqual(dlc.PATCH.fullmatch('media/db/patch/40000_merge.slt')['kind'], 'merge.slt')
        self.assertIsNone(dlc.PATCH.fullmatch('media/db/patch/readme.txt'))


if __name__ == '__main__':
    unittest.main()
