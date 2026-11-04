"""FM2 cockpit material renames and the packaging rules for keys, names, makes and donors."""
import sqlite3
import unittest

from fm4_converter.fm2 import models, package
from fm4_converter.fm3 import ui_names


def model(*sections):
    return {'sections': [{'name': name, 'meshes': [{'name': m, 'lod': lod} for m, lod in meshes]}
                         for name, meshes in sections]}


class CockpitRenameTests(unittest.TestCase):
    def test_bare_materials_only_rename_in_cockpit_parts(self):
        renames = models.cockpit_renames(model(
            ('interior', [('interior', 1), ('black', 1), ('window', 1), ('chrome', 1)]),
            ('steering_wheel', [('matte_colors', 1)]),
            ('glassF', [('window', 1), ('black_glass', 1)]),
            ('hooda', [('black', 1), ('matte_colors', 1)]),
            ('mirrorL', [('chrome', 1), ('black', 1)])))
        self.assertEqual(renames, {
            'interior/interior': 'plastic', 'interior/black': 'plastic', 'interior/window': 'glass',
            'interior/chrome': 'mirrorMiddle', 'steering_wheel/matte_colors': 'plastic',
            'mirrorL/chrome': 'mirrorLeft'})

    def test_only_lod1_meshes_and_cockpit_sections_count(self):
        renames = models.cockpit_renames(model(('interior', [('window', 3), ('tail_light', 1)]),
                                               ('bodyFL', [('black', 1)])))
        self.assertEqual(renames, {'interior/tail_light': 'reflector'})


def database(*tables):
    db = sqlite3.connect(':memory:')
    for sql in tables:
        db.execute(sql)
    return db


class KeyTests(unittest.TestCase):
    def test_free_key_skips_database_dlc_and_pending_rows(self):
        db = database('CREATE TABLE T (Id INTEGER)')
        db.executemany('INSERT INTO T VALUES (?)', [(2000,), (2002,)])
        rows = [{'table': 'T', 'row': {'Id': 2003}}, {'table': 'U', 'row': {'Id': 2001}}]
        self.assertEqual(package.free_key(db, 'T', 'Id', {'T': {2001}}, rows), 2004)

    def test_names_take_the_highest_free_string_keys(self):
        taken = {65534}
        keys = package.names(490, {'DisplayName': 'XK Coupe (FM2)', 'ModelShort': 'XK (FM2)'}, taken)
        self.assertEqual([ui_names.reference(k['reference']) & 65535 for k in keys.values()], [65533, 65532])
        self.assertEqual({ui_names.reference(k['reference']) >> 16 for k in keys.values()}, {package.STRING_PAGE})
        self.assertEqual(keys['ModelShort']['symbol'], 'IDS_ModelShort_490')
        self.assertTrue({65533, 65532} <= taken)


class MakeTests(unittest.TestCase):
    def setUp(self):
        self.fm2 = database('CREATE TABLE List_CarMake (ID INTEGER, ManufacturerCode TEXT)')
        self.fm2.executemany('INSERT INTO List_CarMake VALUES (?,?)', [(16, 'JAG'), (39, 'POR'), (40, 'PRO'), (7, 'BMW')])
        self.fm4 = database('CREATE TABLE List_CarMake (ID INTEGER, ManufacturerCode TEXT)')
        self.fm4.executemany('INSERT INTO List_CarMake VALUES (?,?)', [(16, 'JAG'), (7, 'BUG')])
        self.registry = {'List_CarMake': [('pack/34_pri_65.zip', {'ID': 39, 'ManufacturerCode': 'POR'})]}

    def test_disc_make_dlc_make_and_missing_make(self):
        self.assertEqual(package.make_for(self.fm2, self.fm4, self.registry, 16), (16, None))
        self.assertEqual(package.make_for(self.fm2, self.fm4, self.registry, 39), (39, 'pack/34_pri_65.zip'))
        self.assertEqual(package.make_for(self.fm2, self.fm4, self.registry, 40), (None, 'no FM4 make PRO'))

    def test_same_id_with_another_manufacturer_is_not_used(self):
        self.assertEqual(package.make_for(self.fm2, self.fm4, self.registry, 7), (None, 'FM4 make 7 is BUG, FM2 BMW'))


class DonorTests(unittest.TestCase):
    def test_donors_keep_the_steering_side(self):
        pool = [{'media': 'LHD', 'steer': -0.37}, {'media': 'RHD', 'steer': 0.35}]
        self.assertEqual([d['media'] for d in package.same_side(pool, 0.35)], ['RHD'])
        self.assertEqual([d['media'] for d in package.same_side(pool, -0.41)], ['LHD'])


if __name__ == '__main__':
    unittest.main()
