"""Geometry-sharing FM3 layouts: Tracks row, ribbon provenance and AI selection."""
from pathlib import Path
import sqlite3
import tempfile
import unittest

from fm4_converter.fm3 import converter as c
from fm4_converter.fm3 import track_package as tp


def database(fm4):
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    extra = ", IsReverse, MiniRibbonPath, RichPresence, QuickRaceLapCountKinect" if fm4 else ", TrackType"
    db.execute("CREATE TABLE Tracks (id, DisplayName, ShortDisplayName, MediaName, RibbonIndex, ReverseIndex, "
               "Length, DefaultStartGridPositionsId, FlyingStartPosId, MPSortOrder, WinningsScalar, "
               "QuickRaceLapCount, EnvironmentId" + extra + ")")
    db.execute("CREATE TABLE StartGridPositions (id, StartIndex)")
    db.execute("CREATE TABLE TrackStartingMerges (Tracks_id, WaypointsToFirstMerge)")
    db.execute("CREATE TABLE TrackPittingZones (Tracks_id, SpeedLimit)")
    db.execute(f"CREATE TABLE SplitPoints ({'ID, ' if fm4 else ''}TrackId, Split)")
    db.execute(f"CREATE TABLE GraffitiPoints ({'ID, ' if fm4 else ''}TrackId, Split)")
    return db


class TrackPackageTests(unittest.TestCase):
    def setUp(self):
        self.fm3, self.fm4 = database(False), database(True)
        base = ("CrownJewel", 9, 9, 6952, 160, 160, 306, 0.64, 1, 4)
        self.fm3.execute("INSERT INTO Tracks VALUES (160,'_&1','_&2',?,?,?,?,?,?,?,?,?,?,1)", base)
        self.fm3.execute("INSERT INTO Tracks VALUES (170,'_&3','_&4','CrownJewel',19,9,6952,170,6,307,0.63,1,4,2)")
        self.fm4.execute("INSERT INTO Tracks VALUES (160,'_&1','_&2',?,?,?,?,?,?,?,?,?,?,0,'RIB10',70,1)", base)
        for db in (self.fm3, self.fm4):
            db.execute("INSERT INTO TrackStartingMerges VALUES (170, 5)")
            db.execute("INSERT INTO TrackPittingZones VALUES (170, 20.0)")
        self.fm3.execute("INSERT INTO SplitPoints VALUES (170, 0.5)")
        self.fm4.execute("INSERT INTO SplitPoints VALUES (333, 170, 0.5)")
        self.fm4.executemany("INSERT INTO StartGridPositions VALUES (?, 0)", [(170,), (6,)])

    def test_row_takes_identity_from_fm3_and_presentation_from_fm4(self):
        row, evidence = tp.plan_row(self.fm3, self.fm4, 170)
        self.assertEqual((row["id"], row["RibbonIndex"], row["ReverseIndex"], row["IsReverse"]), (170, 19, 9, 1))
        self.assertEqual((row["DisplayName"], row["MPSortOrder"], row["FlyingStartPosId"]), ("_&3", 307, 6))
        self.assertEqual((row["MiniRibbonPath"], row["RichPresence"]), ("RIB10", 70))
        self.assertEqual(evidence["template_id"], 160)
        self.assertTrue(evidence["dependents"]["SplitPoints"]["fm4_equals_fm3"])
        self.assertNotIn("TrackType", row)

    def test_missing_dependent_rows_or_grid_are_refused(self):
        self.fm4.execute("DELETE FROM TrackPittingZones")
        with self.assertRaises(c.MappingError):
            tp.plan_row(self.fm3, self.fm4, 170)
        self.fm4.execute("INSERT INTO TrackPittingZones VALUES (170, 20.0)")
        self.fm4.execute("DELETE FROM StartGridPositions WHERE id=6")
        with self.assertRaises(c.MappingError):
            tp.plan_row(self.fm3, self.fm4, 170)

    def test_existing_or_own_geometry_layouts_are_refused(self):
        with self.assertRaises(c.MappingError):
            tp.plan_row(self.fm3, self.fm4, 160)
        self.fm3.execute("UPDATE Tracks SET ReverseIndex=19 WHERE id=170")
        with self.assertRaises(c.MappingError):
            tp.plan_row(self.fm3, self.fm4, 170)


class TrackFileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.fm3, self.fm4 = self.root/"fm3/Tracks", self.root/"fm4/tracks"
        for path, data in {
            "fm3/Tracks/CrownJewel/Ribbon_09/PreRaceCams.xml": b"shared",
            "fm3/Tracks/CrownJewel/Ribbon_19/PreRaceCams.xml": b"shared",
            "fm3/Tracks/CrownJewel/Ribbon_19/TrackSegCams.xml": b"fm3 cams",
            "fm4/tracks/CrownJewel/Ribbon_09/preracecams.xml": b"fm4 cams",
            "fm4/tracks/CrownJewel/Ribbon_09/crownjewel_track_09.col": b"col",
            "fm4/tracks/CrownJewel/Ribbon_09/crownjewel_09.pvs": b"pvs",
            "fm4/tracks/CrownJewel/Ribbon_09/crownjewel_track_09.crowd": b"crowd",
            "fm3/AI/Tracks/CrownJewel_19_R.geo": b"g", "fm3/AI/Tracks/CrownJewel_19_R.irt": b"i",
            "fm3/AI/Tracks/CrownJewel_19_R.seg": b"s", "fm3/AI/Tracks/Level1/CrownJewel_19_R.bin": b"l",
            "fm3/AI/Tracks/SegmentProfiles/CrownJewel_19_R/Default.bin": b"p",
            "fm3/AI/Tracks/CrownJewel_09.geo": b"other", "fm3/AI/Tracks/CrownJewel_190.geo": b"other",
        }.items():
            (self.root/path).parent.mkdir(parents=True, exist_ok=True)
            (self.root/path).write_bytes(data)
        (self.root/"fm4/AI/Tracks").mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_shared_ribbon_file_comes_from_fm4_geometry_ribbon(self):
        payloads, records = tp.ribbon_files(self.fm3, self.fm4, "CrownJewel", 19, 9)
        origin = {Path(r["path"]).name: r["origin"] for r in records}
        self.assertEqual(origin, {"PreRaceCams.xml": "fm4_geometry_ribbon", "TrackSegCams.xml": "fm3"})
        self.assertIn(b"fm4 cams", payloads.values())

    def test_collobjs_get_fm4_graphics_indices_and_drop_unproven_objects(self):
        def collobjs(*objects):
            body = b"".join(b'\t<Obj%d PhysicsType="Cone" GraphicsName="#%d">\r\n\t\t<Pos x="%s" y="0" z="0"/>\r\n'
                            b'\t</Obj%d>\r\n' % (n, g, x, n) for n, (g, x) in enumerate(objects))
            return b'<?xml version="1.0" ?>\r\n<CollObjs>\r\n' + body + b"</CollObjs>\r\n"
        for path, data in {"fm3/Tracks/CrownJewel/Ribbon_00/CollObjs.xml": collobjs((5, b"1"), (7, b"2")),
                           "fm4/tracks/CrownJewel/Ribbon_00/collobjs.xml": collobjs((5, b"1"), (6, b"2")),
                           "fm3/Tracks/CrownJewel/Ribbon_19/CollObjs.xml": collobjs((6, b"9"), (7, b"2"))}.items():
            (self.root/path).parent.mkdir(parents=True, exist_ok=True)
            (self.root/path).write_bytes(data)
        mapping = tp.graphics_mapping(self.fm3/"CrownJewel", self.fm4/"CrownJewel")
        self.assertEqual(mapping, {5: 5, 7: 6})
        data, report = tp.remap_collobjs(self.fm3/"CrownJewel/Ribbon_19/CollObjs.xml", mapping)
        self.assertEqual(data, collobjs((6, b"2")))
        self.assertEqual([d["fm3_graphics"] for d in report["dropped"]], [6])

    def test_missing_fm4_geometry_or_existing_ribbon_is_refused(self):
        (self.fm4/"CrownJewel/Ribbon_09/crownjewel_09.pvs").unlink()
        with self.assertRaises(c.MappingError):
            tp.ribbon_files(self.fm3, self.fm4, "CrownJewel", 19, 9)
        (self.fm4/"CrownJewel/Ribbon_09/crownjewel_09.pvs").write_bytes(b"pvs")
        (self.fm4/"CrownJewel/Ribbon_19").mkdir()
        with self.assertRaises(c.MappingError):
            tp.ribbon_files(self.fm3, self.fm4, "CrownJewel", 19, 9)

    def test_audio_adds_only_missing_kinds_from_geometry_ribbon(self):
        audio = self.root/"fm4/audio/tracks/CrownJewel"
        for path, data in {"ribbon_09/crownjewelribbon_09.xml": b"9", "ribbon_09/crownjewelribbon_09reverb.xml": b"r9",
                           "ribbon_09/crownjewelribbon_09decisionzones.xml": b"zones",
                           "ribbon_19/crownjewelribbon_19.xml": b"19",
                           "ribbon_19/crownjewelribbon_19reverb.xml": b"r19"}.items():
            (audio/path).parent.mkdir(parents=True, exist_ok=True)
            (audio/path).write_bytes(data)
        payloads, _ = tp.audio_files(audio, "CrownJewel", 19, 9)
        self.assertEqual({p.as_posix(): d for p, d in payloads.items()}, {
            "Media/audio/tracks/CrownJewel/ribbon_19/crownjewelribbon_19decisionzones.xml": b"zones"})
        (audio/"ribbon_19").rename(audio/"gone")
        with self.assertRaises(c.MappingError):
            tp.audio_files(audio, "CrownJewel", 19, 9)

    def test_new_files_ship_in_a_zip_mounted_at_their_folder(self):
        import io, zipfile
        folder = Path("Media/AI/Tracks")
        archive, data = tp.mounted_archive(folder, {folder/"CrownJewel_19_R.geo": b"g",
                                                    folder/"Level1/CrownJewel_19_R.bin": b"l"})
        self.assertEqual(archive, Path("Media/AI/Tracks.zip"))
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            self.assertEqual(z.namelist(), ["CrownJewel_19_R.geo", "Level1/CrownJewel_19_R.bin"])
            self.assertEqual({i.compress_type for i in z.infolist()}, {zipfile.ZIP_STORED})

    def test_ai_selects_only_the_layout_ribbon(self):
        payloads, _ = tp.ai_files(self.root/"fm3/AI/Tracks", self.root/"fm4/AI/Tracks", "CrownJewel", 19)
        self.assertEqual(sorted(p.as_posix() for p in payloads), [
            "Media/AI/Tracks/CrownJewel_19_R.geo", "Media/AI/Tracks/CrownJewel_19_R.irt",
            "Media/AI/Tracks/CrownJewel_19_R.seg", "Media/AI/Tracks/Level1/CrownJewel_19_R.bin",
            "Media/AI/Tracks/SegmentProfiles/CrownJewel_19_R/Default.bin"])
        (self.root/"fm4/AI/Tracks/CrownJewel_19_R.geo").write_bytes(b"native")
        with self.assertRaises(c.MappingError):
            tp.ai_files(self.root/"fm3/AI/Tracks", self.root/"fm4/AI/Tracks", "CrownJewel", 19)


if __name__ == "__main__":
    unittest.main()
