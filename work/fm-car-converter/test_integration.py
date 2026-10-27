"""Import boundaries and FM3-only conversion regression tests."""
from contextlib import closing
import json
import io
from pathlib import Path
import sqlite3
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile

import converter as c
import integration as m


class ArchivePathTests(unittest.TestCase):
    def test_rejects_escape_and_windows_drive_paths(self):
        for path in ("../car.bin", "/car.bin", "a/../../car.bin",
                     "C:/car.bin", "a\\..\\car.bin", "a./car.bin"):
            with self.subTest(path=path), self.assertRaises(c.MappingError):
                m.safe_member(path)
        self.assertEqual(m.safe_member("physics\\maxdata.xml").as_posix(), "physics/maxdata.xml")

    def test_zip_mount_directory_offsets_and_payload_roundtrip(self):
        payloads = {Path("Media/Cars/TEST/physics/maxdata.xml"):b"<MAXData/>",
                    Path("Media/Wheels/WHEEL/wheel.xds"):b"wheel",
                    Path("Media/UI/Textures/Thumbnails/Thumbnail_305.xds"):b"thumbnail"}
        archives = m.asset_archives(payloads,"TEST","WHEEL")
        result = m.extend_zip_manifest(b'<ZipFiles version="3"/>',archives)
        entries = ET.fromstring(result).findall("Zip")
        self.assertEqual(len(entries),3)
        for entry, (path,data) in zip(entries,sorted(archives.items())):
            start = int(entry.attrib["dirstart"])
            self.assertEqual(data[start:start+4],b"PK\x01\x02")
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                self.assertEqual(len(archive.infolist()),int(entry.attrib["direntries"]))
                self.assertIsNone(archive.testzip())
        with self.assertRaisesRegex(c.MappingError,"already exists"):
            m.extend_zip_manifest(result,archives)
        with self.assertRaises(c.MappingError):
            m.extend_zip_manifest(b'<ZipFiles version="3"/>',
                                 {Path("Media/Cars/TEST.zip"):next(iter(archives.values()))[:-1]})


@unittest.skipUnless(c.FM3_DEFAULT.exists() and c.FM4_DEFAULT.exists(), "Local source databases unavailable")
class ImportTests(unittest.TestCase):
    def test_fm3_only_conversion_has_no_fake_native_comparison(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)/"new"
            result = c.run(c.FM3_DEFAULT,c.FM4_DEFAULT,out,"CHE_Cobalt_05",code_semantics=True)
            self.assertTrue(result["validation_passed"])
            comparison = json.loads((out/"comparison.json").read_text())
            self.assertFalse(comparison["reference_available"])
            self.assertEqual(comparison["status"],"not_available")
            self.assertEqual(comparison["counts"],{})
            self.assertFalse((out/"reference_fm4_ir.json").exists())
            effective = json.loads((out/"effective_comparison.json").read_text())
            self.assertIsNone(effective["suspension_vs_native_fm4"])
            self.assertTrue((out/"code_semantics.json").exists())

    def test_existing_car_is_not_replaced(self):
        with closing(c.connect(c.FM3_DEFAULT)) as a, closing(c.connect(c.FM4_DEFAULT)) as b:
            with self.assertRaisesRegex(c.MappingError,"already exists"):
                m.build_plan(a,b,c.MEDIA)

    def test_new_ordinal_all_edges_and_stock_graph_survive_merge(self):
        with closing(c.connect(c.FM3_DEFAULT)) as a, closing(c.connect(c.FM4_DEFAULT)) as b:
            source,result = m.build_plan(a,b,"CHE_Cobalt_05")
            graph = result["candidate"]
            self.assertEqual(graph["nodes"]["car"]["row"]["Id"],305)
            names = result["integration"]["localized_names"]
            for field in ("DisplayName", "ModelShort"):
                self.assertEqual(graph["nodes"]["car"]["row"][field],
                                 source["nodes"]["car"]["row"][field])
                self.assertEqual(names[field]["reference"],source["nodes"]["car"]["row"][field])
                self.assertTrue(names[field]["text"].strip())
            for edge in graph["edges"]:
                target = graph["nodes"][edge["to"]]
                self.assertEqual(graph["nodes"][edge["from"]]["row"][edge["column"]],
                                 target["row"][target["pk"]])
            with closing(sqlite3.connect(":memory:")) as merged:
                merged.row_factory=sqlite3.Row
                b.backup(merged)
                before = merged.execute("SELECT COUNT(*) FROM Data_Car").fetchone()[0]
                m.insert_rows(merged,list(graph["nodes"].values())+result["integration"]["presentation_rows"])
                self.assertEqual(merged.execute("SELECT COUNT(*) FROM Data_Car").fetchone()[0],before+1)
                actual = c.extract_stock(merged,"CHE_Cobalt_05")
                for role,node in graph["nodes"].items():
                    self.assertEqual(node,actual["nodes"][role])
                self.assertEqual(merged.execute("PRAGMA integrity_check").fetchone()[0],"ok")
            self.assertTrue(result["code_semantics"])
            self.assertFalse(result["integration"]["accepted"])

    def test_presentation_conflict_aborts_the_plan(self):
        with closing(c.connect(c.FM3_DEFAULT)) as a, closing(c.connect(c.FM4_DEFAULT)) as b:
            with closing(sqlite3.connect(":memory:")) as changed:
                changed.row_factory=sqlite3.Row
                b.backup(changed)
                changed.execute("UPDATE ArcadeCarList SET Level=Level+1 WHERE CarId=305")
                with self.assertRaisesRegex(c.MappingError,"Conflicting target presentation"):
                    m.build_plan(a,changed,"CHE_Cobalt_05")

    def test_original_disc_cannot_be_used_for_staging(self):
        with tempfile.TemporaryDirectory() as temp:
            for root in (c.FM3_DEFAULT.parents[2],c.FM4_DEFAULT.parents[2]):
                with self.assertRaisesRegex(c.MappingError,"separate"):
                    m.stage_probe(c.FM3_DEFAULT,c.FM4_DEFAULT,root,Path(temp)/"out","CHE_Cobalt_05")


if __name__ == "__main__":
    unittest.main()
