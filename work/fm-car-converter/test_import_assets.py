"""CPU-only import regressions using local, legally supplied game data."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import struct
import tempfile
import unittest
import zipfile

import asset_conversion as assets
import camera_semantics as camera
import carbin_audit as audit
import converter as c
import integration
import offline_package

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT/"outputs/fm-car-converter/import-v1/carbin-cpu-v3/carbin-cpu.exe"
EXPERIMENT = ROOT/"outputs/fm-car-converter/import-v1/cobalt-models-offline"


class BoundsTests(unittest.TestCase):
    def test_truncated_unknown_and_wrong_family_are_rejected(self):
        for data in (b"", b"\0"*100, struct.pack(">I",5)+b"\0"*1024):
            for family in ("FM3","FM4"):
                with self.subTest(family=family), self.assertRaises(audit.FormatError):
                    audit.parse(data,family)
        with self.assertRaises(audit.FormatError):
            audit.Reader(b"\0"*4).take(5)

    def test_restart_tokens_do_not_hide_other_invalid_indices(self):
        mesh = {"primitive":6,"indices":{"stride":4,"count":5,
                 "data":struct.pack(">5I",2,0xFFFFFF,0xFFFFFFFF,3,9999)}}
        self.assertEqual(list(audit.index_values(mesh)),[2,3,9999])
        mesh["primitive"]=4
        self.assertEqual(len(list(audit.index_values(mesh))),5)

    def test_normal_maps_and_thumbnails_are_not_gamma_rewritten(self):
        data = bytearray(60)
        data[:4]=struct.pack(">I",3)
        data[31]=2
        data[35]=0x54
        for name in ("leather_NRM.xds","normalmap.xds","Thumbnail_305.xds"):
            self.assertEqual(assets.convert_texture(bytes(data),name),data)
        changed = assets.convert_texture(bytes(data),"lights.xds")
        self.assertEqual([i for i,(a,b) in enumerate(zip(data,changed)) if a!=b],[31,35])
        self.assertEqual(changed[31],254)
        self.assertEqual(changed[35],0x75)

    def test_unknown_colour_format_fails_instead_of_guessing(self):
        data = struct.pack(">I",3)+bytes(56)
        with self.assertRaises(ValueError):
            assets.convert_texture(data,"lights.xds")

    def test_helper_tampering_is_rejected_before_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)
            (p/"carbin-cpu.exe").write_bytes(b"changed")
            (p/"build.json").write_text(json.dumps({
                "reference_commit":"8807c7d137646dab8d9eecab7e8d5a6602ef58aa",
                "helper_sha256":"not the hash"}))
            with self.assertRaisesRegex(ValueError,"executable differs"):
                assets.check_helper(p/"carbin-cpu.exe")


@unittest.skipUnless(c.FM3_DEFAULT.exists() and c.FM4_DEFAULT.exists(),"Local databases unavailable")
class CameraTests(unittest.TestCase):
    def test_explicit_camera_basepoint_is_preserved(self):
        with closing(c.connect(c.FM3_DEFAULT)) as a,closing(c.connect(c.FM4_DEFAULT)) as b:
            src,result=integration.build_plan(a,b,"CHE_Cobalt_05")
            record=result["integration"]["cockpit_reference"]
            self.assertTrue(record["applied"])
            added=[n["row"] for n in result["integration"]["presentation_rows"]
                   if n["table"]=="CarPartPositions" and n["row"]["PartId"]==9]
            self.assertEqual(len(added),1)
            old=c.rows(a,"CarPartPositions","Ordinal=305 AND PartId=4")[0]
            for axis in "XYZ":
                self.assertEqual(old["PartPos"+axis],added[0]["PartPos"+axis])
            self.assertEqual(record["reference_plus_offset"],[-0.377538,0.996491,-0.22479300000000002])

    def test_unknown_default_camera_is_reported_not_guessed(self):
        with closing(c.connect(c.FM3_DEFAULT)) as a,closing(c.connect(c.FM4_DEFAULT)) as b:
            with closing(sqlite3.connect(":memory:")) as m:
                m.row_factory=sqlite3.Row
                a.backup(m)
                m.execute("UPDATE CameraOverrides SET CamCockpitOffsetX=0, CamCockpitOffsetY=0, CamCockpitOffsetZ=0 WHERE CarId=305")
                rows=[]
                result=camera.apply(m,b,305,rows)
                self.assertFalse(result["applied"])
                self.assertEqual(rows,[])

    def test_dlc_conflict_is_rejected_before_package_creation(self):
        with closing(c.connect(c.FM3_DEFAULT)) as a,closing(c.connect(c.FM4_DEFAULT)) as b:
            _,plan=integration.build_plan(a,b,"CHE_Cobalt_05")
        with tempfile.TemporaryDirectory() as temp,closing(sqlite3.connect(":memory:")) as db:
            db.execute("CREATE TABLE Data_Car (Id INTEGER, MediaName TEXT)")
            db.execute("INSERT INTO Data_Car VALUES (305,'different')")
            path=Path(temp)/"dlc.zip"
            with zipfile.ZipFile(path,"w") as z:
                z.writestr("media/db/patch/test_merge.slt",db.serialize())
            with self.assertRaisesRegex(c.MappingError,"DLC identity conflict"):
                offline_package.overlay_collisions(plan,[path])


@unittest.skipUnless(EXPERIMENT.exists(),"Local converted-model fixtures unavailable")
class GeometryTests(unittest.TestCase):
    def test_all_twelve_actual_model_files_preserve_geometry(self):
        paths=[p for p in EXPERIMENT.glob("*.carbin") if not p.name.endswith(".fm4.carbin")]
        self.assertEqual(len(paths),12)
        total=0
        for p in paths:
            with self.subTest(file=p.name):
                result=audit.audit_conversion(p.read_bytes(),p.with_suffix(".fm4.carbin").read_bytes())
                self.assertTrue(result["passed"])
                total+=result["vertices"]
        self.assertEqual(total,300825)

    def test_raw_fm3_and_damaged_fm4_are_rejected(self):
        source=(EXPERIMENT/"Cars-che_cobalt_05.carbin").read_bytes()
        target=(EXPERIMENT/"Cars-che_cobalt_05.fm4.carbin").read_bytes()
        with self.assertRaises(audit.FormatError):
            audit.audit_conversion(source,source)
        model=audit.parse(target,"FM4")
        pool=next(s["lod"] for s in model["sections"] if s["lod"]["count"])
        start=target.index(pool["data"])
        damaged=bytearray(target)
        damaged[start:start+8]=struct.pack(">4h",32767,32767,32767,32767)
        with self.assertRaisesRegex(audit.FormatError,"position drift"):
            audit.audit_conversion(source,bytes(damaged))
        with self.assertRaises(audit.FormatError):
            audit.parse(target[:-24],"FM4")


@unittest.skipUnless(HELPER.exists() and c.FM3_DEFAULT.exists(),"CPU model helper or source unavailable")
class HelperTests(unittest.TestCase):
    def test_real_brake_conversion_has_fm4_name_and_verified_geometry(self):
        with zipfile.ZipFile(c.FM3_DEFAULT.parents[1]/"Cars/CHE_Cobalt_05.zip") as z:
            data=integration.archive_read(z,"che_cobalt_05_caliperlf.carbin")
        path=Path("Media/Cars/CHE_Cobalt_05/che_cobalt_05_caliperlf.carbin")
        converted,report=assets.convert_payloads({path:data},HELPER)
        expected=path.with_name("che_cobalt_05_caliperlf_lod0.carbin")
        self.assertEqual(set(converted),{expected})
        self.assertTrue(report["assets"][0]["geometry"]["passed"])


class OriginalInstructionTests(unittest.TestCase):
    def test_camera_part_selectors_match_original_bytes(self):
        for family,offset,opcode in (("fm3",0x8246230C,0x38A00004),
                                     ("fm4",0x8267CEBC,0x38A00009)):
            path=ROOT/f"outputs/fm-car-converter/code-semantics-v1/{family}/loaded-image.bin"
            if not path.exists():
                self.skipTest("Local executable evidence unavailable")
            data=path.read_bytes()
            self.assertEqual(assets.sha(data),camera.EVIDENCE[family+"_reference_selector"]["image_sha256"])
            self.assertEqual(struct.unpack_from(">I",data,offset-0x82000000)[0],opcode)


if __name__=="__main__":
    unittest.main()
