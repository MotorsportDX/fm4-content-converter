"""Many-car packaging: car selection, name keys and the legacy-asset audit rules it relies on."""
import copy
import sqlite3
import struct
import unittest

from fm4_converter.fm3 import appearance_audit as a
from fm4_converter.fm3 import batch_package as b
from fm4_converter.fm3 import carbin_audit
from fm4_converter.fm3 import code_semantics as s
from fm4_converter.fm3 import converter as c
from fm4_converter.fm3 import driver_audit
from fm4_converter.fm3 import ui_names


def cars(*names):
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE Data_Car (Id INTEGER, MediaName TEXT)")
    db.executemany("INSERT INTO Data_Car VALUES (?,?)", enumerate(names, 1))
    return db


class SelectionTests(unittest.TestCase):
    def test_missing_cars_excludes_disc_and_installed_dlc_cars(self):
        source, target = cars("CHE_Cobalt_05", "POR_959_87", "TOY_2000GT_69"), cars("toy_2000gt_69")
        registry = {"Data_Car":[("pack/34_pri_65.zip", {"MediaName":"POR_959_87"})]}
        self.assertEqual(b.missing_cars(source, target, registry), ["CHE_Cobalt_05"])


class CockpitPaintTests(unittest.TestCase):
    SOURCE = (b'<ShaderSettings>\r\n  <cockpit_bump_leather>\r\n    <CockpitBumpScale value="0.400000"/>\r\n'
              b'  </cockpit_bump_leather>\r\n  <cockpit_plastic>\r\n    <CockpitPlasticPaintScale value="0.2"/>\r\n'
              b'  </cockpit_plastic>\r\n</ShaderSettings>\r\n')

    def test_scales_added_for_used_techniques_and_source_kept(self):
        used = {"cockpit_bump_leather", "cockpit_plastic", "cockpit_leather", "cockpit_body", "cockpit_metal2"}
        out, added, unmeasured = a.cockpit_paint_settings(self.SOURCE, used)
        self.assertEqual([(x["technique"], x["parameter"], x["value"]) for x in added],
                         [("cockpit_bump_leather", "CockpitPaintScale", 0.183), ("cockpit_leather", "PaintScale", 0.22)])
        self.assertEqual(unmeasured, ["cockpit_metal2"])
        root = a.xml(out)
        self.assertEqual(root.find("cockpit_plastic/CockpitPlasticPaintScale").get("value"), "0.2")
        self.assertEqual(root.find("cockpit_bump_leather/CockpitBumpScale").get("value"), "0.400000")
        self.assertIsNone(root.find("cockpit_body"))
        self.assertNotIn(b"\n\n", out.replace(b"\r", b""))
        self.assertTrue(out.replace(b"\r\n", b"").count(b"\n") == 0)  # CRLF kept
        self.assertEqual(a.cockpit_paint_settings(out, used)[0], out)

    def test_repeated_source_element_kept(self):
        # DOD_57_ViperGTSR_00 names cockpit_carbon_fiber twice with different values.
        source = (b'<ShaderSettings>\n  <cockpit_carbon_fiber>\n    <CarbonFiberScale value="3.0"/>\n'
                  b'  </cockpit_carbon_fiber>\n  <cockpit_carbon_fiber>\n    <CarbonFiberScale value="1.2"/>\n'
                  b'  </cockpit_carbon_fiber>\n</ShaderSettings>\n')
        out, added, _ = a.cockpit_paint_settings(source, {"cockpit_plastic", "cockpit_carbon_fiber"})
        self.assertEqual([p.get("value") for p in a.xml(out).iter("CarbonFiberScale")], ["3.0", "1.2"])
        self.assertEqual(len(added), 1)

    def test_nothing_written_without_scaled_techniques(self):
        self.assertEqual(a.cockpit_paint_settings(None, {"cockpit_glass"}), (None, [], []))
        out, added, _ = a.cockpit_paint_settings(None, {"cockpit_solid"})
        self.assertEqual(a.xml(out).find("cockpit_solid/PaintScale").get("value"), "0.153")


class NameKeyTests(unittest.TestCase):
    def binding(self, key, field="DisplayName", car=1159):
        return {"reference":f"_&{(0xCD49 << 16) | key}", "key":(0xCD49 << 16) | key,
                "symbol":f"IDS_{field}_{car}", "text":"DBR9 (FM3)"}

    def test_colliding_key_moves_to_the_highest_free_key(self):
        bindings = {"AST/DisplayName":self.binding(23160), "AST/ModelShort":self.binding(100, "ModelShort")}
        taken = {23160, 65534}
        moved = ui_names.rekey(bindings, taken)
        self.assertEqual(moved, {"AST/DisplayName":f"_&{(0xCD49 << 16) | 65533}"})
        row = bindings["AST/DisplayName"]
        self.assertEqual(row["source_reference"], f"_&{(0xCD49 << 16) | 23160}")
        self.assertEqual(row["key"] & 65535, 65533)
        self.assertNotIn("source_reference", bindings["AST/ModelShort"])
        self.assertEqual(taken, {23160, 65534, 65533, 100})


V4 = b"""<CarAttributes Version="4"><Damage value="1"/><Tires FrontTireScale="1" RearTireScale="1"/>
<Driver Version="5" BodyScale="1.0" HasPaddleShifter="0"/><General OpenCockpit="0"/></CarAttributes>"""
COCKPIT = b"""<DriverHandsOffset value.x="0" value.y="0" value.z="0"/><DriverHandsScale value="1"/>
<CockpitNearPlane value="0.1"/><CockpitShadowScale value="1"/><DriverHandsSteeringWheelOverride value="0"/>
<SteeringWheelAngleOverride value="0"/><Use10_2Animations value="0"/>"""
GAUGE = b'NumTicks="2"><Tick Param="0" Value="0"/><Tick Param="1" Value="10"/>'
V10 = (b'<CarAttributes Version="10"><Driver Version="6" BodyScale="1" HasPaddleShifter="1"/>' + COCKPIT
       + b"".join(b"<%s %s</%s>" % (g, GAUGE, g) for g in (b"Speed", b"Tach", b"Fuel")) + b"</CarAttributes>")


class LegacyAttributeTests(unittest.TestCase):
    def test_layouts_fm4_ships_natively_are_accepted(self):
        self.assertEqual(a.driver_attributes(V4)["car_attributes_version"], 4)
        legacy = a.driver_attributes(V10)
        self.assertEqual(legacy["gauge_tick_counts"], {"Speed":2, "Tach":2, "Fuel":2})
        self.assertIsNone(a.driver_attributes(None)["car_attributes_version"])

    def test_layouts_without_native_precedent_are_rejected(self):
        for broken in (V4.replace(b'Version="4"', b'Version="9"', 1), V10.replace(b"<Tach ", b"<Oil ", 1).replace(b"</Tach>", b"</Oil>"),
                       V4.replace(b'Driver Version="5"', b'Driver Version="7"')):
            with self.subTest(data=broken[:40]), self.assertRaises(a.AppearanceError):
                a.driver_attributes(broken)

    def test_absent_animation_flags_take_the_standard_clips(self):
        for data in (None, V4):
            chosen = driver_audit.selection(data)
            self.assertFalse(chosen["use_10_2"])
            self.assertIn("Use10_2Animations", chosen["assumed_absent_defaults"])
        self.assertTrue(driver_audit.selection(V10)["has_paddle_shifter"])
        with self.assertRaises(driver_audit.DriverError):
            driver_audit.selection(V4.replace(b'HasPaddleShifter="0"', b'HasPaddleShifter="2"'))


class DegenerateFrameTests(unittest.TestCase):
    @staticmethod
    def pool(normal, axis):
        def pack(v, bits=(11, 11, 10)):
            word = 0
            for shift, value, width in zip((0, 11, 22), v, bits):
                scale = (1 << (width-1)) - 1
                word |= (round(value*scale) & ((1 << width)-1)) << shift
            return struct.pack(">I", word)
        data = bytearray(40)
        data[16:20], data[36:40] = pack(normal), pack(axis)
        return {"stride":40, "data":bytes(data), "count":1}

    def test_parallel_or_zero_source_axis_follows_the_converter_fallback(self):
        for normal, axis, expected in (((0, 1, 0), (0, 1, 0), (0, 0, 1)), ((0, 1, 0), (0, 0, 0), (0, 0, 1)),
                                       ((0, 0, 1), (0, 0, 1), (1, 0, 0))):
            pool = self.pool(normal, axis)
            n = carbin_audit.normal3(pool, 0)
            for x, y in zip(carbin_audit.tangent_axis3(pool, 0, n), expected):
                self.assertAlmostEqual(x, y, places=3)

    def test_zero_source_normal_reads_as_up(self):
        self.assertEqual(carbin_audit.normal3(self.pool((0, 0, 0), (1, 0, 0)), 0), (0.0, 1.0, 0.0))


class CroppedThumbnailTests(unittest.TestCase):
    def test_car_touching_one_edge_keeps_the_rest_of_the_matte(self):
        from PIL import Image, ImageDraw
        from fm4_converter.fm3 import ui_thumbnail as t
        im = Image.new("RGB", (160, 80), "white")
        ImageDraw.Draw(im).rectangle((0, 30, 100, 60), fill=(20, 30, 90))
        out, report = t.remove_white_matte(im)
        self.assertEqual(out.getpixel((150, 5))[3], 0)
        self.assertEqual(out.getpixel((0, 45))[3], 255)
        self.assertEqual(report["border_pixels_covered_by_car"], 31)
        ImageDraw.Draw(im).rectangle((0, 0, 159, 30), fill=(20, 30, 90))
        with self.assertRaisesRegex(t.ThumbnailError, "white border"):
            t.remove_white_matte(im)


@unittest.skipUnless(c.FM3_DEFAULT.exists() and c.FM4_DEFAULT.exists(), "Local source DBs required")
class StockWeightDeltaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src, cls.dst = c.connect(c.FM3_DEFAULT), c.connect(c.FM4_DEFAULT)
        cls.source = c.extract_stock(cls.src, c.MEDIA)

    @classmethod
    def tearDownClass(cls):
        cls.src.close()
        cls.dst.close()

    def test_negligible_stock_delta_is_bounded_not_rejected(self):
        source = copy.deepcopy(self.source)
        role = next(r for r, n in source["nodes"].items()
                    if r.startswith("List_Upgrade") and "WeightDistDiff" in n["row"])
        source["nodes"][role]["row"]["WeightDistDiff"] = 2e-4
        result = c.convert(self.src, self.dst, source)
        s.apply(result, source)
        record = s.inputs(result["candidate"], "fm4")
        self.assertEqual(record["nonzero_weight_delta_roles"], [{"role":role, "delta":2e-4}])
        self.assertLess(record["weighted_height_uncertainty_m"], 1e-4)
        source["nodes"][role]["row"]["WeightDistDiff"] = 2e-3
        with self.assertRaises(c.MappingError):
            s.apply(c.convert(self.src, self.dst, source), source)


if __name__ == "__main__":
    unittest.main()
