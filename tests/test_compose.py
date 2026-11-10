"""Independent packages (fm4_converter.items, format 2) and their compose over FM4 Disc 1
(fm4_converter.compose): the newer game's car wins, keys another package took move with the
rows that refer to them, names land on free keys of the tables the game reads, and an item
whose DLC pack is missing lets the older game's stand in."""
import io
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile

from fm4_converter import compose, items
from fm4_converter.fm3 import converter as c
from fm4_converter.fm3 import ui_names

FM4 = Path(c.FM4_DEFAULT).parents[1]


def stored(members):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as z:
        for name, data in members.items():
            z.writestr(zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0)), data)
    return stream.getvalue()


def disc(root):
    """A Disc 1 with FM4's string tables and archive list and a small database."""
    media = root / "Media"
    (media / "DB").mkdir(parents=True)
    shutil.copytree(FM4 / "StringTables", media / "StringTables")
    shutil.copyfile(FM4 / "zipmanifest.xml", media / "zipmanifest.xml")
    db = sqlite3.connect(media / "DB/gamedb.slt")
    db.executescript("""
        CREATE TABLE Data_Car (Id INTEGER PRIMARY KEY, MediaName TEXT, DisplayName TEXT, ModelShort TEXT, EngineID INT);
        CREATE TABLE Data_Engine (EngineID INTEGER PRIMARY KEY, Name TEXT);
        CREATE TABLE CarPartPositions (ID INT, Ordinal INT, PartId INT);
        INSERT INTO Data_Car VALUES (1, 'FM4_CAR', '_&3444047873', '_&3444047874', 1);
        INSERT INTO Data_Engine VALUES (1, 'native');
        INSERT INTO CarPartPositions VALUES (100, 1, 0);
    """)
    db.commit()
    db.close()
    return root


def car(car_id, media, engine, part_id, text, requires=()):
    record = items.item(f"car:{car_id}", "car", media, text, requires=requires,
                        identity=items.car_identity(car_id, media))
    record["rows"] = [
        {"table": "Data_Car", "row": {"Id": car_id, "MediaName": media, "DisplayName": "_&3444047873",
                                      "ModelShort": "_&3444047874", "EngineID": engine}},
        {"table": "Data_Engine", "row": {"EngineID": engine, "Name": media}},
        {"table": "CarPartPositions", "row": {"ID": part_id, "Ordinal": car_id, "PartId": 0}},
    ]
    record["renumber"] = [items.key_spec("Data_Engine", "EngineID", [1], [[0, "EngineID"]]),
                          items.key_spec("CarPartPositions", "ID", [2])]
    record["strings"] = [items.string("Data_Car.str", "_&3444047873", f"IDS_DisplayName_{car_id}", {"*": text},
                                      [[0, "DisplayName"]]),
                         items.string("Data_Car.str", "_&3444047874", f"IDS_ModelShort_{car_id}",
                                      {"*": text + " short"}, [[0, "ModelShort"]])]
    record["files"][f"Media/Cars/{media}.zip"] = 80
    record["members"]["Media/UI/Textures/Thumbnails.zip"] = [f"Thumbnail_{car_id}.xds"]
    return record


def package(root, mod_id, game, records):
    stage = root / f"{mod_id}.stage/files"
    for record in records:
        (stage / "Media/Cars").mkdir(parents=True, exist_ok=True)
        (stage / f"Media/Cars/{record['media']}.zip").write_bytes(stored({"model.carbin": record["media"].encode()}))
    thumbs = {f"Thumbnail_{r['identity']['cars'][0]}.xds": game.encode() for r in records}
    (stage / "Media/UI/Textures").mkdir(parents=True, exist_ok=True)
    (stage / "Media/UI/Textures/Thumbnails.zip").write_bytes(stored(thumbs))
    archives = {"Media/UI/Textures/Thumbnails.zip": {"priority": 80, "root": "Media/UI/Textures/Thumbnails"}}
    out = root / mod_id
    items.write(out, stage, records, archives, dict(id=mod_id, name=mod_id, kind="car-overlay", source_game=game,
                                                    edition=game.lower(), sources=[], built_against={}, notes=[]))
    return out


class ComposeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.disc = disc(self.root / "disc")

    def tearDown(self):
        self.tmp.cleanup()

    def test_newer_game_wins_and_taken_keys_move(self):
        fm2 = package(self.root, "fm2-cars", "FM2", [car(10, "CAR_A", 2000, 101, "A (FM2)"),
                                                     car(11, "CAR_B", 2001, 101, "B (FM2)")])
        fm3 = package(self.root, "fm3-cars", "FM3", [car(10, "CAR_A", 2000, 101, "A (FM3)")])
        report = compose.compose(self.disc, [fm3, fm2], self.root / "out")
        self.assertEqual([(w["key"], w["package"]) for w in report["winners"]],
                         [("car:11", "fm2-cars"), ("car:10", "fm3-cars")])
        self.assertEqual(report["left_out"], [{"key": "car:10", "package": "fm2-cars", "reason": "replaced by fm3-cars"}])
        db = sqlite3.connect(self.root / "out/Media/DB/gamedb.slt")
        engines = dict(db.execute("SELECT Id, EngineID FROM Data_Car").fetchall())
        self.assertEqual(engines[11], 2001)
        self.assertEqual(dict(db.execute("SELECT EngineID, Name FROM Data_Engine").fetchall())[engines[10]], "CAR_A")
        self.assertEqual(sorted(r[0] for r in db.execute("SELECT ID FROM CarPartPositions")), [100, 101, 102])
        names = {r[0]: (r[1], r[2]) for r in db.execute("SELECT Id, DisplayName, ModelShort FROM Data_Car")}
        db.close()
        with zipfile.ZipFile(self.root / "out/Media/stringtables.zip") as override:
            english = next(n for n in override.namelist() if n.casefold() == "en/data_car.str")
            table = ui_names.StringTable(override.read(english))
        self.assertEqual(table.texts[ui_names.reference(names[10][0]) & 65535], "A (FM3)")
        self.assertEqual(table.texts[ui_names.reference(names[11][1]) & 65535], "B (FM2) short")
        self.assertEqual(names[1], ("_&3444047873", "_&3444047874"))   # FM4's own car keeps its names
        with zipfile.ZipFile(self.root / "out/Media/UI/Textures/Thumbnails.zip") as z:
            self.assertEqual({n: z.read(n) for n in z.namelist()},
                             {"Thumbnail_10.xds": b"FM3", "Thumbnail_11.xds": b"FM2"})
        mounts = {n.attrib["path"]: n.attrib for n in
                  ET.parse(self.root / "out/Media/zipmanifest.xml").getroot().findall("Zip")}
        for path in ("game:\\media\\cars\\car_a.zip", "game:\\media\\cars\\car_b.zip",
                     "game:\\media\\ui\\textures\\thumbnails.zip", "game:\\media\\stringtables.zip"):
            self.assertIn(path, mounts)
        self.assertEqual(Path(self.root / "out/Media/Cars/CAR_A.zip").read_bytes(),
                         (fm3 / "files/Media/Cars/CAR_A.zip").read_bytes())

    def test_missing_pack_lets_the_older_game_stand_in(self):
        fm2 = package(self.root, "fm2-cars", "FM2", [car(10, "CAR_A", 2000, 101, "A (FM2)")])
        fm3 = package(self.root, "fm3-cars", "FM3", [car(10, "CAR_A", 2000, 101, "A (FM3)", requires=["pack/x.zip"])])
        report = compose.compose(self.disc, [fm2, fm3], self.root / "out")
        self.assertEqual([(w["key"], w["package"]) for w in report["winners"]], [("car:10", "fm2-cars")])
        self.assertIn("needs the DLC pack pack/x.zip", report["left_out"][0]["reason"])

    def test_a_changed_package_is_refused(self):
        fm3 = package(self.root, "fm3-cars", "FM3", [car(10, "CAR_A", 2000, 101, "A")])
        (fm3 / "files/Media/Cars/CAR_A.zip").write_bytes(b"changed")
        with self.assertRaises(items.ModError):
            compose.compose(self.disc, [fm3], self.root / "out")

    def test_recorder_lists_inserted_and_changed_rows(self):
        db = sqlite3.connect(":memory:")
        db.executescript("CREATE TABLE T (Id INTEGER PRIMARY KEY, V TEXT); INSERT INTO T VALUES (1, 'a');")
        recorder = items.Recorder(db)
        db.execute("INSERT INTO T VALUES (5, 'b')")
        db.execute("UPDATE T SET V='c' WHERE Id=1")
        db.execute("UPDATE T SET V='d' WHERE Id=5")
        added, changed = recorder.take()
        self.assertEqual(added, [{"table": "T", "row": {"Id": 5, "V": "d"}}])
        self.assertEqual(changed, [{"table": "T", "row": {"Id": 1, "V": "c"}}])
        recorder.close()


if __name__ == "__main__":
    unittest.main()
