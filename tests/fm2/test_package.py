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

    @staticmethod
    def donor(media, id, wheel, mass=1600, power=300, make=19, drive=1, race=False):
        return {'media': media, 'id': id, 'drive': drive, 'make': make, 'mass': mass, 'power': power,
                'wheel': wheel, 'steer': wheel[0], 'race': race}

    POOL = [donor('JAG_XKRS_09', 1, (0.37, 0.65, -0.25), mass=1700, power=380),
            donor('JAG_33_XKR_10', 2, (0.4, 0.65, -0.25)),
            donor('JAG_XJ220_93', 3, (-0.4, 0.65, -0.25), mass=1500, power=400)]
    SOURCE = {'nodes': {'List_UpgradeCarBodyWeight': {'Mass': 1600}, 'engine': {'EngineGraphingMaxPower': 300},
                        'drivetrain': {'DrivetypeID': 1}, 'car': {'MakeID': 19}}}
    WHEEL = (0.47, 0.65, -0.3)

    def choose(self, pool, wheel=WHEEL, race=False, manual=None):
        donor, how = package.choose_donor(pool, self.SOURCE, 490, wheel, race, manual)
        return donor['media'], how

    def test_automatic_donor_keeps_the_steering_side(self):
        self.assertEqual(self.choose(self.POOL), ('JAG_33_XKR_10', 'automatic'))

    def test_automatic_donor_has_its_steering_wheel_near_the_fm2_one(self):
        # The nearest in mass and power has its wheel 0.33 m in front of the FM2 one (432R and Silvia).
        pool = [self.donor('NEAR_POWER', 1, (0.37, 0.65, -0.63)), self.donor('NEAR_WHEEL', 2, (0.37, 0.65, -0.35),
                                                                            mass=1700, power=380)]
        self.assertEqual(self.choose(pool), ('NEAR_WHEEL', 'automatic'))
        # dy beyond WHEEL_DY also counts (the Supra AB Flug's hands were hidden at +0.08).
        pool[0]['wheel'] = (0.37, 0.57, -0.35)
        self.assertEqual(self.choose(pool), ('NEAR_WHEEL', 'automatic'))

    def test_without_a_donor_in_the_window_the_nearest_wheel_wins(self):
        pool = [self.donor('FAR', 1, (0.37, 0.65, -1.0)), self.donor('LESS_FAR', 2, (0.37, 0.65, 0.2),
                                                                     mass=1700, power=380)]
        self.assertEqual(self.choose(pool), ('LESS_FAR', 'automatic'))

    def test_race_donors_only_for_race_cars(self):
        pool = [self.donor('STOCK_CAR', 1, (0.37, 0.65, -0.3), race=True),
                self.donor('ROAD_CAR', 2, (0.37, 0.65, -0.3), mass=1700, power=380)]
        self.assertEqual(self.choose(pool), ('ROAD_CAR', 'automatic'))
        self.assertEqual(self.choose(pool, race=True), ('STOCK_CAR', 'automatic'))

    def test_wheel_offset_and_window(self):
        donor = self.donor('D', 1, (0.36, 0.65, -0.24))
        dz, dy = package.wheel_offset((0.37, 0.58, 0.09), donor)
        self.assertAlmostEqual(dz, 0.33)
        self.assertAlmostEqual(dy, -0.07)
        self.assertAlmostEqual(package.outside((0.37, 0.58, 0.09), donor), 0.23)
        self.assertEqual(package.outside((0.37, 0.65, -0.24), donor), 0)

    def test_manual_donor_from_the_pool(self):
        self.assertEqual(self.choose(self.POOL, manual='jag_xkrs_09'), ('JAG_XKRS_09', 'manual'))

    def test_manual_donor_outside_the_pool_or_on_the_other_side_is_refused(self):
        with self.assertRaisesRegex(package.c.MappingError, 'not a usable donor'):
            self.choose(self.POOL, manual='AUD_2_R15TDI_09')
        with self.assertRaisesRegex(package.c.MappingError, 'other side'):
            self.choose(self.POOL, manual='JAG_XJ220_93')

    def test_donor_arguments(self):
        self.assertEqual(package.parse_donors(['JAG_XK_07=JAG_XKRS_09']), {'jag_xk_07': 'JAG_XKRS_09'})
        self.assertEqual(package.parse_donors(None), {})
        for bad in (['JAG_XK_07'], ['=JAG_XKRS_09'], ['A=B', 'a=C']):
            with self.assertRaises(package.c.MappingError):
                package.parse_donors(bad)

    def test_donor_for_a_car_that_is_not_packaged_is_refused(self):
        with self.assertRaisesRegex(package.c.MappingError, 'not packaged'):
            package.build('unused', cars=['JAG_XK_07'], donors={'maz_rx7_reamemiya_95': 'MAZ_RX8_04'})


if __name__ == '__main__':
    unittest.main()
