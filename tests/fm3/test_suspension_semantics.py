"""Regression tests for reference geometry, cap activation and atomic rejection."""
import copy
from contextlib import closing
import math
import sqlite3
import unittest

from fm4_converter.fm3 import converter as c
from fm4_converter.fm3 import code_semantics as cs
from fm4_converter.fm3 import ride_height_audit as oracle
from fm4_converter.fm3 import suspension_semantics as s


class ExtensionMathTests(unittest.TestCase):
    def test_piecewise_extension_and_active_cap(self):
        self.assertAlmostEqual(s.legacy_extension(.05), .05)
        self.assertAlmostEqual(s.legacy_extension(.08), .07)
        self.assertAlmostEqual(s.legacy_extension(.2), .15)
        self.assertAlmostEqual(s.extension_bound(.3, .1), .15)
        self.assertAlmostEqual(s.extension_bound(.3, .1, .5), .15)
        self.assertAlmostEqual(s.extension_bound(.3, .1, .1), .2)
        self.assertAlmostEqual(s.extension_bound(.3, .1, 0), .3)
        with self.assertRaises(c.MappingError):
            s.extension_bound(.3, .1, -1)

    def test_effective_ride_height_uses_normalized_default(self):
        row = {"MinRideHeight": .1, "DefRideHeight": .4, "MaxRideHeight": .2}
        self.assertAlmostEqual(s.effective(row, "RideHeight"), .2)
        self.assertAlmostEqual(s.effective(row, "RideHeight", 0), .1)
        self.assertAlmostEqual(s.effective(row, "RideHeight", .5), .15)
        row["MinRideHeight"] = .3
        with self.assertRaises(c.MappingError):
            s.effective(row, "RideHeight")

    @unittest.skipUnless(all(p.exists() for p in oracle.IMAGES.values()), "Local executable images required")
    def test_original_byte_oracles_and_changed_opcode_rejection(self):
        images = oracle.load_images()
        self.assertTrue(all(r["passed"] for r in oracle.micro_checks(images, 80).values()))
        for version in images:
            for kind in ("extension", "geometry", "rest"):
                broken = bytearray(images[version])
                lo = oracle.SLICES[version, kind][0] - 0x82000000
                broken[lo] ^= 1
                with self.assertRaisesRegex(c.MappingError, "Changed or missing"):
                    oracle.scalar_slice(broken, version, kind, {}, {}, {})


@unittest.skipUnless(c.FM3_DEFAULT.exists() and c.FM4_DEFAULT.exists(), "Local databases required")
class SuspensionConversionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fm3, cls.fm4 = c.connect(c.FM3_DEFAULT), c.connect(c.FM4_DEFAULT)
        cls.source = c.extract_stock(cls.fm3, "BMW_2_M3GTR_05")

    @classmethod
    def tearDownClass(cls):
        cls.fm3.close()
        cls.fm4.close()

    def candidate(self, source=None):
        return c.convert(self.fm3, self.fm4, self.source if source is None else source)

    def test_adjustable_stock_reference_and_cg_change_together(self):
        result = self.candidate()
        before = copy.deepcopy(result)
        cs.apply(result, self.source)
        car = s.row(result["candidate"], "car")
        self.assertAlmostEqual(car["FrontStockRideHeight"], .13)
        self.assertAlmostEqual(car["RearStockRideHeight"], .164)
        self.assertTrue(s.compare_geometry(self.source, result["candidate"])["preserved"])
        self.assertTrue(cs.compare_centers(self.source, result["candidate"])["source_preserved_within_tolerance"])
        changes = {(role, col) for role, node in result["candidate"]["nodes"].items()
                   for col, value in node["row"].items()
                   if before["candidate"]["nodes"][role]["row"].get(col) != value}
        self.assertEqual(changes, {("car", "FrontStockRideHeight"), ("car", "RearStockRideHeight"),
                                   (cs.WEIGHT, "CMHeight")})
        self.assertEqual(s.row(result["candidate"], "spring.front")["MaxStretchDeltaFromRideHeight"], .5)

    def test_fixed_height_toyota_retains_previous_coordinate_value(self):
        source = c.extract_stock(self.fm3, c.MEDIA)
        result = self.candidate(source)
        cs.apply(result, source)
        self.assertAlmostEqual(s.row(result["candidate"], cs.WEIGHT)["CMHeight"], .407)
        self.assertTrue(s.compare_geometry(source, result["candidate"])["preserved"])

    def test_cap_that_clips_extension_is_rejected_before_any_mutation(self):
        for cap in (.001, 0, -1, math.inf, math.nan):
            result = self.candidate()
            s.row(result["candidate"], "spring.rear")["MaxStretchDeltaFromRideHeight"] = cap
            before = copy.deepcopy(result)
            with self.subTest(cap=cap), self.assertRaises(c.MappingError):
                cs.apply(result, self.source)
            self.assertEqual(result, before)

    def test_full_spring_range_checked_even_when_default_would_pass(self):
        source = copy.deepcopy(self.source)
        s.row(source, "spring.front")["MinSpringRate"] = .1
        result = self.candidate(source)
        before = copy.deepcopy(result)
        with self.assertRaisesRegex(c.MappingError, "selected spring range"):
            cs.apply(result, source)
        self.assertEqual(result, before)

    def test_missing_provenance_for_either_axle_rejected_atomically(self):
        for role, col in (("car", "RearStockRideHeight"),
                          ("spring.rear", "MaxStretchDeltaFromRideHeight")):
            result = self.candidate()
            result["mapping"] = [m for m in result["mapping"] if (m["role"], m["target_column"]) != (role, col)]
            before = copy.deepcopy(result)
            with self.assertRaises(c.MappingError):
                cs.apply(result, self.source)
            self.assertEqual(result, before)

    def test_invalid_or_changed_geometry_rejected_atomically(self):
        for role, col, value in (("spring.rear", "MaxRideHeight", .8),
                                 ("spring.front", "ChassisPivotY", .8)):
            result = self.candidate()
            s.row(result["candidate"], role)[col] = value
            before = copy.deepcopy(result)
            with self.assertRaises(c.MappingError):
                cs.apply(result, self.source)
            self.assertEqual(result, before)
        for role, col, value in (("spring.rear", "MinSpringRate", 0),
                                 ("spring.rear", "MinRideHeight", -.1),
                                 ("spring.rear", "MinRideHeight", 1)):
            source = copy.deepcopy(self.source)
            s.row(source, role)[col] = value
            result = self.candidate(source)
            before = copy.deepcopy(result)
            with self.assertRaises(c.MappingError):
                cs.apply(result, source)
            self.assertEqual(result, before)

    def test_audi_historical_default_remains_raw_while_effective_rate_is_clamped(self):
        source = c.extract_stock(self.fm3, "AUD_2_R10_08")
        result = self.candidate(source)
        audit = cs.apply(result, source)
        self.assertEqual(s.row(result["candidate"], "spring.rear")["DefSpringRate"], 151.1875)
        axle = audit["suspension"]["axles"]["rear"]
        self.assertEqual(axle["effective_default_spring_rate"], 150.)
        self.assertGreater(axle["maximum_sag_over_spring_slider"], axle["default_sag"])
        self.assertTrue(axle["cap_nonbinding_over_selected_spring_range"])

    def test_target_answer_cannot_control_new_mapping(self):
        expected = self.candidate()
        cs.apply(expected, self.source)
        with closing(sqlite3.connect(":memory:")) as altered:
            altered.row_factory = sqlite3.Row
            self.fm4.backup(altered)
            target = c.extract_stock(altered, self.source["media_name"])
            target_id = s.row(target, "car")["Id"]
            altered.execute("UPDATE Data_Car SET FrontStockRideHeight=9, RearStockRideHeight=8 WHERE Id=?", (target_id,))
            altered.execute("UPDATE List_SpringDamperPhysics SET MaxStretchDeltaFromRideHeight=.001, MaxRideHeight=7 WHERE Ordinal=?", (target_id,))
            altered.set_authorizer(lambda action, table, column, database, trigger:
                                   sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_READ and table == "Data_Car"
                                   and column not in ("Id", "") else sqlite3.SQLITE_OK)
            actual = c.convert(self.fm3, altered, self.source)
            cs.apply(actual, self.source)
        self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
