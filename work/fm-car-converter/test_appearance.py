"""Real asset regressions, corruption checks, and original-code provenance.

CPU only: metadata, decompression and linear texture blocks; no renderer.
"""
import copy
import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import appearance_audit as a
import archive_cpu
import carbin_audit
import converter as c
import effect_audit
import integration
import texture_audit

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT/"outputs/fm-car-converter/import-v1/cobalt-offline-v4/files"
MODELS = ROOT/"outputs/fm-car-converter/import-v1/cobalt-models-offline"
CAR = Path("Media/Cars/CHE_Cobalt_05")


class MappingTests(unittest.TestCase):
    def test_loader_uses_part_and_mesh_lod_not_filename(self):
        self.assertEqual(a.technique("caliperLF", "top", 0), "caliper")
        self.assertEqual(a.technique("rotorLF", "left_side", 0), "rotor")
        self.assertEqual(a.technique("caliperLF", "geoShadowBrake", 0), "geoShadowBrake")
        self.assertEqual(a.technique("interior", "bump_leather", 0), "cockpit_bump_leather")
        self.assertEqual(a.technique("interior", "interior", 1), "interior")
        self.assertEqual(a.technique("glassF", "window", 0), "frontwindow")
        self.assertEqual(a.technique("wheel", "outer_rim", 0), "outer_rim")
        self.assertEqual(a.technique("wheel", "outer_rim", 1), "outer_rim_V2")
        self.assertEqual(a.technique("wheel", "outer_rim", 0, detailed=False), "outer_rim_V2")
        self.assertEqual(a.technique("mirrorL", "mirrorLeft", 0), "mirrorLeft")

    def test_load_flags_reject_unknown_expressions(self):
        flags = {"Cockpit": True, "SuperLOD": False}
        self.assertTrue(a.load_flags("Cockpit & !SuperLOD", flags))
        self.assertFalse(a.load_flags("Cockpit & SuperLOD", flags))
        for invalid in ("Cockpit | SuperLOD", "Unknown", "Cockpit & !"):
            with self.assertRaises(a.AppearanceError):
                a.load_flags(invalid, flags)
        self.assertEqual(a.xml(b'<a loadFlags="Cockpit & !SuperLOD" name="x&amp;y"/>').get("name"), "x&y")

    def test_effect_reader_rejects_bad_references(self):
        for data in (b"", bytes(4096), b"\xa3\xd7\x01\x41"*2048):
            with self.assertRaises(effect_audit.EffectError):
                effect_audit.read_effect(data)
        reader = effect_audit.Reader(b"abc\0")
        for offset in (-1, 1, 999):
            with self.assertRaises(effect_audit.EffectError):
                reader.number(offset)
        with self.assertRaises(effect_audit.EffectError):
            reader.string(4)


@unittest.skipUnless(c.FM3_DEFAULT.exists() and c.FM4_DEFAULT.exists() and BASE.exists(),
                     "Local source/target and offline-v4 asset fixtures unavailable")
class LocalAssetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source, cls.target = {}, {}
        for folder in ("Cars", "Wheels"):
            relative = Path("Media")/folder/"CHE_Cobalt_05"
            with zipfile.ZipFile(c.FM3_DEFAULT.parents[1]/folder/"CHE_Cobalt_05.zip") as z:
                for n in z.namelist():
                    if not n.endswith("/"):
                        cls.source[relative/n] = integration.archive_read(z, n)
            with zipfile.ZipFile(BASE/relative.with_suffix(".zip")) as z:
                for n in z.namelist():
                    cls.target[relative/n] = z.read(n)
        thumb = Path("Media/UI/Textures/Thumbnails/Thumbnail_305.xds")
        with zipfile.ZipFile(c.FM3_DEFAULT.parents[1]/"UI/Textures.zip") as z:
            cls.source[thumb] = integration.archive_read(z, "Thumbnails/Thumbnail_305.xds")
        with zipfile.ZipFile(BASE/"Media/UI/Textures/Thumbnails.zip") as z:
            cls.target[thumb] = z.read("Thumbnail_305.xds")

    def appearance(self, target=None):
        return a.audit(self.source, target if target is not None else self.target,
                       c.FM4_DEFAULT.parents[1], "CHE_Cobalt_05", "CHE_Cobalt_05",
                       integration.archive_read)

    def test_all_actual_meshes_textures_and_driver_dependencies(self):
        report = self.appearance()
        self.assertTrue(report["passed"])
        self.assertEqual(report["mesh_count"], 1250)
        self.assertEqual(len(report["techniques"]), 67)
        self.assertEqual(len(report["native_driver_assets"]), 68)
        self.assertEqual(len(report["texture_dependencies"]), 42)
        self.assertTrue(report["sampler_validation"]["passed"])
        self.assertTrue(report["driver_animation_validation"]["passed"])
        self.assertEqual(report["driver"]["gauge_tick_counts"], {"Speed": 3, "Tach": 3, "Fuel": 0, "Boost": 4})
        self.assertFalse(report["driver"]["hands_auto_offset"])
        self.assertLess(report["driver"]["rig"]["pivot_to_section_origin_m"], 0.024)
        self.assertFalse(report["runtime_tested"])
        self.assertEqual([x["parameter"] for x in report["material_overrides"]], ["CockpitBumpScale"]*2)

    def test_missing_cockpit_texture_rejected(self):
        target = {p: b for p, b in self.target.items() if p.name.lower() != "interior_lod0.xds"}
        with self.assertRaisesRegex(a.AppearanceError, "Missing local texture"):
            self.appearance(target)

    def test_unknown_mesh_material_rejected_without_fallback(self):
        target = dict(self.target)
        path = CAR/"che_cobalt_05.carbin"
        target[path] = target[path].replace(b"badge_chrome", b"zadge_chrome", 1)
        self.assertNotEqual(target[path], self.target[path])
        with self.assertRaisesRegex(a.AppearanceError, "Missing race technique"):
            self.appearance(target)

    def test_legacy_attributes_reject_bad_scales_and_gauges(self):
        data = self.source[CAR/"carattribs.xml"]
        cases = (data.replace(b'BodyScale="1.041002"', b'BodyScale="nan"'),
                 data.replace(b'NumTicks="3"', b'NumTicks="4"', 1),
                 data.replace(b'<CockpitNearPlane value="0.100000"', b'<CockpitNearPlane value="-1"'),
                 data.replace(b'Value="40.233601"', b'Value="10"'),
                 data.replace(b'<CarAttributes Version="15"', b'<CarAttributes Version="16"'))
        for broken in cases:
            self.assertNotEqual(broken, data)
            with self.subTest(data=broken[:35]), self.assertRaises(a.AppearanceError):
                a.driver_attributes(broken)

    def test_all_twenty_textures_preserve_every_mip(self):
        count = 0
        for p, b in self.source.items():
            if p.suffix.lower() == ".xds":
                with self.subTest(path=p):
                    report = texture_audit.compare(b, self.target[p])
                    self.assertTrue(report["all_mip_blocks_preserved"])
                    self.assertGreater(len(report["mips"]), 1)
                    self.assertEqual(report["gamma_sign_bits"], 0 if p.name.startswith("Thumbnail") else 63)
                count += 1
        self.assertEqual(count, 20)

    def test_texture_corruption_and_truncation_rejected(self):
        b = self.source[CAR/"interior_lod0.xds"]
        with self.assertRaisesRegex(texture_audit.TextureError, "payload changed"):
            texture_audit.compare(b, b[:-1]+bytes([b[-1]^1]))
        with self.assertRaisesRegex(texture_audit.TextureError, "outside XDS"):
            texture_audit.Texture(b[:4096]).audit()
        bad = bytearray(b)
        bad[36:40] = struct.pack(">I", 0x00000000)  # different dimensions, same payload
        with self.assertRaisesRegex(texture_audit.TextureError, "layout or codec"):
            texture_audit.compare(b, bytes(bad))

    def test_emblem_is_not_misdiagnosed_as_missing_badge_texture(self):
        effects = effect_audit.read_effect((c.FM4_DEFAULT.parents[1]/"Shaders/Cars/shaders_v16.fxobj").read_bytes())
        self.assertEqual(len(effects), 196)
        self.assertIn("Badge2Sampler", effects["emblem"]["samplers"])
        with zipfile.ZipFile(c.FM4_DEFAULT.parents[1]/"Cars/Shared.zip") as z:
            settings = a.xml(integration.archive_read(z, "ShaderSettings/Normal.xml"))
        self.assertIsNone(settings.find("emblem/Badge2Sampler"))
        self.assertIsNotNone(settings.find("badge2/Badge2Sampler"))
        self.assertFalse(any(p.name.lower() == "badge2.xds" for p in self.target))

    def test_native_colour_fetch_controls_for_car_and_wheel(self):
        # Compare like codecs: the 2010 Cobalt uses DXT5 wheel atlases while the
        # 2005 source uses DXT1. Conversion must not reinterpret DXT1 as DXT5.
        controls = {}
        for folder, control in (("Cars", "CHE_CobaltSS_10"), ("Wheels", "CHE_CobaltSS_10"),
                                ("Wheels", "acu_nsx_97")):
            with zipfile.ZipFile(c.FM4_DEFAULT.parents[1]/folder/(control+".zip")) as z:
                for filename in (("interior_lod0.xds", "lights.xds", "nodamage.xds") if folder == "Cars"
                                 else ("wheel.xds", "wheel0.xds", "wheel_lod0.xds")):
                    native = texture_audit.Texture(integration.archive_read(z, filename))
                    controls.setdefault(native.codec, set()).add((native.format, native.gamma, native.endian))
        for p, data in self.target.items():
            if p.suffix.lower() == ".xds" and not p.name.startswith("Thumbnail"):
                imported = texture_audit.Texture(data)
                with self.subTest(path=p):
                    self.assertIn((imported.format, imported.gamma, imported.endian), controls[imported.codec])

    def test_native_driver_fallback_checks_crc(self):
        with zipfile.ZipFile(c.FM4_DEFAULT.parents[1]/"Cars/Driver.zip") as z:
            info = z.getinfo("DriverLOD0.gr2")
            data = archive_cpu.read_xmem(z, info)
            self.assertEqual(len(data), info.file_size)
            corrupt = copy.copy(info)
            corrupt.CRC ^= 1
            with self.assertRaisesRegex(ValueError, "CRC"):
                archive_cpu.read_xmem(z, corrupt)
            with tempfile.TemporaryDirectory() as temp:
                dll = Path(temp)/"decoder.dll"
                dll.write_bytes(b"unreviewed")
                with patch.dict(os.environ, {"FM_XCOMPRESS_DLL": str(dll)}):
                    with self.assertRaisesRegex(ValueError, "Unreviewed"):
                        archive_cpu.read_xmem(z, info)


@unittest.skipUnless(MODELS.exists(), "Local model fixtures unavailable")
class RigTests(unittest.TestCase):
    def test_tangent_frame_flip_is_detected_even_with_identical_normal(self):
        source = (MODELS/"Cars-che_cobalt_05_cockpit.carbin").read_bytes()
        data = (MODELS/"Cars-che_cobalt_05_cockpit.fm4.carbin").read_bytes()
        model = carbin_audit.parse(data, "FM4")
        pool = next(s["lod0"] for s in model["sections"] if s["lod0"]["count"])
        offset = data.index(pool["data"])+16
        broken = bytearray(data)
        x,y,z,w = struct.unpack_from(">4h",data,offset)
        # Rotate 180 degrees around the frame's own normal: geometry and normal
        # survive, but a normal map would use a reversed tangent frame.
        struct.pack_into(">4h",broken,offset,w,z,-y,-x)
        changed_pool = dict(pool)
        changed_pool["data"] = bytes(broken[offset-16:offset-16+len(pool["data"])])
        self.assertEqual(carbin_audit.normal4(pool,0), carbin_audit.normal4(changed_pool,0))
        with self.assertRaisesRegex(carbin_audit.FormatError, "tangent frame drift"):
            carbin_audit.audit_conversion(source,bytes(broken))

    def test_animation_header_corruption_cannot_hide_behind_unchanged_vertices(self):
        source = carbin_audit.parse((MODELS/"Cars-che_cobalt_05_cockpit.carbin").read_bytes(), "FM3")
        data = (MODELS/"Cars-che_cobalt_05_cockpit.fm4.carbin").read_bytes()
        target = carbin_audit.parse(data, "FM4")
        for offset in (0x1c8, 0x228, 0x238, 0x270, 0x300):
            broken = dict(target)
            header = bytearray(target["header"])
            header[offset] ^= 1
            broken["header"] = bytes(header)
            with self.subTest(offset=hex(offset)), self.assertRaises(carbin_audit.FormatError):
                carbin_audit.audit_header(source, broken)

    def test_degenerate_axis_rejected(self):
        model = carbin_audit.parse((MODELS/"Cars-che_cobalt_05_cockpit.fm4.carbin").read_bytes(), "FM4")
        header = bytearray(model["header"])
        header[0x238:0x248] = bytes(16)
        model["header"] = bytes(header)
        with self.assertRaisesRegex(a.AppearanceError, "unit length"):
            a.rig(model)


class EvidenceTests(unittest.TestCase):
    def test_original_loader_and_hand_offset_instructions(self):
        path = ROOT/"outputs/fm-car-converter/code-semantics-v1/fm4/loaded-image.bin"
        if not path.exists():
            self.skipTest("Local executable evidence unavailable")
        data = path.read_bytes()
        self.assertEqual(a.sha(data), a.IMAGE_SHA256)
        for address, opcode in ((0x828F9C3C, 0x81660020), (0x828F9C4C, 0x2F0B0000),
                                (0x828FA17C, 0x2B1B0000), (0x828FA180, 0x419A0050),
                                (0x8290428C, 0x2F1A0010), (0x828E5C00, 0x894B0100),
                                (0x828E5C1C, 0x13EB49C7), (0x828DB6A8, 0xC18900F0)):
            self.assertEqual(struct.unpack_from(">I", data, address-0x82000000)[0], opcode)


if __name__ == "__main__":
    unittest.main()
