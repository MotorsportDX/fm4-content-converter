"""Offline binding regressions using native files and semantic corruptions."""
import copy
import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import zlib

from fm4_converter.fm3 import converter as c
from fm4_converter.fm3 import driver_audit as d
from fm4_converter.fm3 import granny_audit as g
from fm4_converter.fm3 import integration
from fm4_converter.fm3 import sampler_audit as s
from fm4_converter.fm3 import effect_audit


def recompute_crc(data):
    struct.pack_into("<I", data, 40, zlib.crc32(data[104:]) & 0xffffffff)
    return bytes(data)


@unittest.skipUnless(c.FM4_DEFAULT.exists() and c.FM3_DEFAULT.exists(), "Local native fixtures unavailable")
class BindingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with zipfile.ZipFile(c.FM4_DEFAULT.parents[1]/"Cars/Driver.zip") as z:
            cls.assets = {n.casefold(): integration.archive_read(z, n) for n in z.namelist()
                          if n.lower().endswith(".gr2")}
        with zipfile.ZipFile(c.FM3_DEFAULT.parents[1]/"Cars/CHE_Cobalt_05.zip") as z:
            cls.attributes = integration.archive_read(z, "carattribs.xml")
        cls.effects = effect_audit.read_effect(
            (c.FM4_DEFAULT.parents[1]/"Shaders/Cars/shaders_v16.fxobj").read_bytes())

    def test_cobalt_selected_native_steering_and_manual_shifts(self):
        report = d.audit(self.attributes, self.assets)
        self.assertFalse(report["selection"]["use_10_2"])
        self.assertFalse(report["selection"]["has_paddle_shifter"])
        self.assertEqual(report["selection"]["steering_clip_ids"], [0, 1, 2, 3])
        self.assertEqual(len(report["animations"]), 4)
        self.assertEqual([len(skin["bones"]) for skin in report["skins"]], [69, 69])
        self.assertEqual([a["matched_bones"] for a in report["animations"]], [65]*4)
        self.assertEqual(sum(sum(a["curve_formats"].values()) for a in report["animations"]), 912)
        self.assertFalse(report["pose_playback_tested"])

    def test_missing_selected_animation_fails(self):
        for name in ("steerlock2locksmall.gr2", "shiftstickconsoleright.gr2", "driverlod002.gr2"):
            with self.subTest(name=name), self.assertRaisesRegex(d.DriverError, "Missing native"):
                d.audit(self.attributes, {n: b for n, b in self.assets.items() if n != name})

    def test_attributes_choose_distinct_animation_families(self):
        alternate = self.attributes.replace(b'<Use10_2Animations value="0"', b'<Use10_2Animations value="1"')
        paddle = self.attributes.replace(b'HasPaddleShifter="0"', b'HasPaddleShifter="1"')
        self.assertEqual(d.selection(alternate)["steering_clip_ids"], [4, 5, 6, 7])
        self.assertIn("SteerLock2LockSmall_B.gr2", d.selection(alternate)["files"])
        self.assertEqual(d.selection(paddle)["shift_clip_ids_checked"], [16, 17])
        self.assertIn("SteerLock2LockLarge_ROT.gr2", d.selection(paddle)["files"])
        with self.assertRaisesRegex(d.DriverError, "Use10_2"):
            d.selection(self.attributes.replace(b'<Use10_2Animations value="0"', b'<Use10_2Animations value="2"'))

    def test_granny_crc_and_truncation_fail_closed(self):
        raw = self.assets["steerlock2locksmall.gr2"]
        for bad in (raw[:-1], raw[:-1]+bytes([raw[-1] ^ 1])):
            with self.assertRaises(g.GrannyError):
                g.File(bad)

    def test_invalid_granny_fixup_rejected_even_with_valid_crc(self):
        data = bytearray(self.assets["steerlock2locksmall.gr2"])
        fixups = struct.unpack_from("<I", data, 104+28)[0]
        struct.pack_into("<I", data, fixups+4, 999)
        with self.assertRaisesRegex(g.GrannyError, "unknown section"):
            g.File(recompute_crc(data))

    def test_invalid_compression_stops_rejected(self):
        data = bytearray(self.assets["steerlock2locksmall.gr2"])
        struct.pack_into("<I", data, 104+20, 0xffffffff)
        with self.assertRaisesRegex(g.GrannyError, "section stops"):
            g.File(recompute_crc(data))

    def test_unreviewed_decoder_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/"granny.dll"
            path.write_bytes(b"not a decoder")
            with patch.dict(os.environ, {"FM_GRANNY_DLL": str(path)}):
                with self.assertRaisesRegex(g.GrannyError, "Unreviewed"):
                    g.File(self.assets["driverlod001.gr2"])

    def test_skeleton_parent_cycle_rejected(self):
        file = g.File(self.assets["driverlod001.gr2"])
        skeleton = next(x for x in file.root.get("Skeletons") if x.get("Name") == "Bone_Spine_01")
        bone = skeleton.get("Bones")[3]
        section, offset = bone.at
        data = bytearray(file.sections[section])
        struct.pack_into("<i", data, offset+bone.fields["ParentIndex"][0], 3)
        file.sections[section] = bytes(data)
        with patch.object(g, "File", return_value=file), self.assertRaisesRegex(d.DriverError, "parent"):
            d.skeletons(self.assets)

    def test_missing_hand_track_rejected(self):
        file = g.File(self.assets["steerlock2locksmall.gr2"])
        group = next(x for x in file.root.get("Animations")[0].get("TrackGroups")
                     if x.get("Name") == "Bone_Spine_01")
        track = next(x for x in group.get("TransformTracks") if x.get("Name") == "Bone_HandR")
        section, offset = file.pointer((track.at[0], track.at[1]+track.fields["Name"][0]))
        data = bytearray(file.sections[section])
        data[offset:offset+10] = b"None_HandR"
        file.sections[section] = bytes(data)
        real = g.File
        def reader(raw):
            return file if raw == self.assets["steerlock2locksmall.gr2"] else real(raw)
        with patch.object(g, "File", side_effect=reader), self.assertRaisesRegex(d.DriverError, "bone tracks"):
            d.audit(self.attributes, self.assets)

    def test_nonfinite_curve_rejected(self):
        file = g.File(self.assets["steerlock2locksmall.gr2"])
        group = next(x for x in file.root.get("Animations")[0].get("TrackGroups")
                     if x.get("Name") == "Bone_Spine_01")
        curve = group.get("TransformTracks")[0].get("PositionCurve")
        data = curve.get("CurveData")
        section, offset = data.at
        raw = bytearray(file.sections[section])
        struct.pack_into("<f", raw, offset+data.fields["Controls"][0], float("nan"))
        file.sections[section] = bytes(raw)
        with self.assertRaisesRegex(d.DriverError, "Nonfinite"):
            d.curve(curve, 3, 4)

    def test_sampler_slots_are_technique_specific(self):
        body = {r["sampler"]: r["register"] for r in s.registers(self.effects["body"])}
        rim = {r["sampler"]: r["register"] for r in s.registers(self.effects["outer_rim"])}
        self.assertEqual(body["envSampler"], 5)
        self.assertEqual(rim["envSampler"], 1)
        effect = copy.deepcopy(self.effects["body"])
        records = [v for v in effect["passes"][0]["pixel"]["constants"] if v["sampler"]]
        records[1]["register"] = records[0]["register"]
        with self.assertRaisesRegex(s.SamplerError, "Overlapping"):
            s.registers(effect)

    def test_wheel_blur_uses_numbered_low_atlas_and_native_tires(self):
        meshes = [{"model": "Media/Wheels/test/wheel.carbin", "lod": 0, "technique": "tire"},
                  {"model": "Media/Wheels/test/wheel.carbin", "lod": 0, "technique": "outer_rim"}]
        def dependency(root, name):
            return root+name
        report = s.audit({"race": self.effects}, meshes, dependency,
                         "media/cars/test/", "media/wheels/test/", set())
        tire = report["bindings"]["wheel/lod0/tire"]["blurTireSampler"]
        self.assertEqual(tire["files"], [f"Shared/tire{c}0.xds" for c in "abc"])
        rim = report["bindings"]["wheel/lod0/outer_rim"]["baseSampler"]
        self.assertEqual(rim["files"], ["media/wheels/test/wheel_lod0.xds",
                                        "media/wheels/test/wheel.xds"])
        self.assertIn("trackLightmapSampler", report["unresolved_runtime_resources"])


if __name__ == "__main__":
    unittest.main()
