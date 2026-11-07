"""Stacked installs (fm4_converter.stack): a package built on a disc that already carries others
keeps their members of the shared archives, reads their string override, and takes over their
manifest mounts."""
import argparse
import io
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile

from fm4_converter import cli, mod, stack
from fm4_converter.discs import DiscError
from fm4_converter.fm3 import converter as c
from fm4_converter.fm3 import integration
from fm4_converter.fm3 import ui_names


def stored(members):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as z:
        for name, data in members.items():
            z.writestr(zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0)), data)
    return stream.getvalue()


class StackTests(unittest.TestCase):
    def test_extend_keeps_base_members_and_replaces_same_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            disc = Path(tmp)
            (disc / stack.THUMBNAILS).parent.mkdir(parents=True)
            (disc / stack.THUMBNAILS).write_bytes(stored({"Thumbnail_1.xds": b"a", "Thumbnail_2.xds": b"b"}))
            merged, base = stack.extend(disc, stack.THUMBNAILS, {"thumbnail_2.xds": b"B", "Thumbnail_3.xds": b"c"})
            self.assertTrue(base)
            self.assertEqual(merged, {"Thumbnail_1.xds": b"a", "thumbnail_2.xds": b"B", "Thumbnail_3.xds": b"c"})
            merged, base = stack.extend(disc, stack.CAR_AUDIO, {"x.xml": b"x"})
            self.assertFalse(base)
            self.assertEqual(merged, {"x.xml": b"x"})

    def test_mounted_priority(self):
        manifest = (b'<ZipFiles version="3"><Zip version="1" path="game:\\media\\stringtables.zip" '
                    b'priority="25040" dirstart="0" dirsize="0" direntries="0" /></ZipFiles>')
        self.assertEqual(stack.mounted(manifest, stack.STRINGS), 25040)
        self.assertIsNone(stack.mounted(manifest, stack.THUMBNAILS))

    def test_replaced_mount_takes_the_new_priority(self):
        path = Path("Media/stringtables.zip")
        data = stored({"EN/Data_Car.str": b"x"})
        first = integration.extend_zip_manifest(b'<ZipFiles version="3"/>', {path: data}, (), {path: 100})
        second = integration.extend_zip_manifest(first, {path: stored({"EN/Data_Car.str": b"yy"})}, (path,),
                                                 {path: 101})
        nodes = ET.fromstring(second).findall("Zip")
        self.assertEqual(len(nodes), 1)
        self.assertEqual(nodes[0].attrib["priority"], "101")
        # Without a priority the replaced mount keeps its own.
        third = integration.extend_zip_manifest(second, {path: data}, (path,))
        self.assertEqual(ET.fromstring(third).findall("Zip")[0].attrib["priority"], "101")

    def test_keep_base_tables_copies_what_is_not_rewritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            media = Path(tmp) / "Media"
            media.mkdir()
            (media / "stringtables.zip").write_bytes(stored({"EN/Data_Car.str": b"old", "EN/Tracks.str": b"t",
                                                             "DE/Tracks.str": b"d"}))
            stream = io.BytesIO()
            with zipfile.ZipFile(stream, "w") as output:
                output.writestr("EN/Data_Car.str", b"new")
                kept = ui_names.keep_base_tables(output, media, {"en/data_car.str"}, integration.archive_read)
            self.assertEqual(sorted(kept), ["DE/Tracks.str", "EN/Tracks.str"])
            with zipfile.ZipFile(stream) as z:
                self.assertEqual(z.read("EN/Data_Car.str"), b"new")
                self.assertEqual(z.read("EN/Tracks.str"), b"t")
            # Without an override (a package on FM4 Disc 1 alone) nothing is added.
            (media / "stringtables.zip").unlink()
            with zipfile.ZipFile(io.BytesIO(), "w") as output:
                self.assertEqual(ui_names.keep_base_tables(output, media, set(), integration.archive_read), [])

    def test_cli_reads_base_packages(self):
        with tempfile.TemporaryDirectory() as tmp:
            package = Path(tmp) / "fm3-cars"
            (package / "files/Media/Cars").mkdir(parents=True)
            (package / "files/Media/Cars/A.zip").write_bytes(b"car")
            fm4 = Path(tmp) / "fm4"
            fm4.mkdir()
            cars = [dict(media="CHE_A_01", name="A", status="packaged", requires=[], error=None),
                    dict(media="CHE_B_01", name="B", status="failed", requires=[], error="x")]
            described = mod.describe(package, "fm3-cars", "FM3 cars", "FM3", fm4, cars, [], [], {})
            self.assertEqual(described["base_packages"], [])
            packages = cli.base_packages([package])
            self.assertEqual(cli.stacked_cars(packages), {"che_a_01"})
            stacked = mod.describe(Path(tmp) / "fm3-cars", "fm2-cars", "FM2 cars", "FM2", fm4, cars, [], [], {},
                                   (), [dict(id="fm3-cars", created=described["created"])])
            self.assertEqual(stacked["base_packages"][0]["id"], "fm3-cars")

    def test_track_overlay_lists_its_environments(self):
        with tempfile.TemporaryDirectory() as tmp:
            package = Path(tmp) / "fm3-tracks"
            (package / "files/Media/Tracks").mkdir(parents=True)
            (package / "files/Media/Tracks/NewYork.zip").write_bytes(b"track")
            fm4 = Path(tmp) / "fm4"
            fm4.mkdir()
            tracks = [dict(media="NewYork", name=None, status="packaged", layouts=[22, 23], error=None),
                      dict(media="TestTrackinfield", name=None, status="skipped", error="needs a disc")]
            described = mod.describe(package, "fm3-tracks", "FM3 tracks", "FM3", fm4, tracks, [], [], {}, (),
                                     [dict(id="fm3-cars", created="2026-11-07T00:00:00+00:00")], "track-overlay")
            self.assertEqual(described["kind"], "track-overlay")
            self.assertEqual(described["cars"], [])
            self.assertEqual([t["media"] for t in described["tracks"]], ["NewYork", "TestTrackinfield"])
            self.assertEqual((described["packaged"], described["failed"]), (1, 0))
            # Only FM3's tracks convert.
            helper = Path(tmp) / "carbin-cpu.exe"
            helper.write_bytes(b"")
            a = argparse.Namespace(out=str(Path(tmp) / "out"), helper=str(helper), content_root=None, cache=None,
                                   game="fm2", content="tracks")
            with self.assertRaisesRegex(DiscError, "Only FM3's tracks convert"):
                cli.convert(a, cli.Events(False))


@unittest.skipUnless(c.FM4_DEFAULT.exists(), "Local FM4 disc required")
class StackedStringTests(unittest.TestCase):
    """winning_tables on a disc whose override (a package under this one) holds the table."""

    def test_override_wins_and_keeps_its_keys(self):
        fm4 = c.FM4_DEFAULT.parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            media = Path(tmp) / "Media"
            (media / "StringTables").mkdir(parents=True)
            for path in (fm4 / "StringTables").glob("*.zip"):
                (media / "StringTables" / path.name).write_bytes(path.read_bytes())
            native, _ = ui_names.winning_tables(fm4, None, integration.archive_read, c.sha)
            table = ui_names.StringTable(native["en"][3])
            free = next(k for k in range(65534, 0, -1) if k not in table.texts)
            added = table.add([((0xCD49 << 16) | free, f"IDS_DisplayName_{free}", "Stacked car")])
            (media / "stringtables.zip").write_bytes(stored({"EN/Data_Car.str": added}))
            manifest = ET.fromstring((fm4 / "zipmanifest.xml").read_bytes())
            ET.SubElement(manifest, "Zip", {"version": "1", "path": "game:\\media\\stringtables.zip",
                                            "priority": str(native["en"][0] + 1), "dirstart": "0",
                                            "dirsize": "0", "direntries": "0"})
            (media / "zipmanifest.xml").write_bytes(ET.tostring(manifest))
            stacked, inputs = ui_names.winning_tables(media, None, integration.archive_read, c.sha)
            self.assertIn(str(media / "stringtables.zip"), inputs)
            self.assertEqual(ui_names.StringTable(stacked["en"][3]).texts[free], "Stacked car")
            # Languages the override does not carry keep their native table.
            other = next(k for k in native if k != "en")
            self.assertEqual(stacked[other][3], native[other][3])


if __name__ == "__main__":
    unittest.main()
