"""The disposable test disc links the original and never writes through a link."""
from pathlib import Path
import tempfile
import unittest

from fm4_converter.fm3 import test_disc as td


class TestDiscTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.disc = root/"disc"
        (self.disc/"Media/DB").mkdir(parents=True)
        (self.disc/"default.xex").write_bytes(b"xex")
        (self.disc/"Media/DB/gamedb.slt").write_bytes(b"original db")
        (self.disc/"Media/zipmanifest.xml").write_bytes(b"original manifest")
        self.package = root/"package"
        (self.package/"files/Media/db").mkdir(parents=True)
        (self.package/"files/Media/Cars").mkdir(parents=True)
        (self.package/"files/Media/db/gamedb.slt").write_bytes(b"candidate db")
        (self.package/"files/Media/Cars/NEW.zip").write_bytes(b"car")
        self.out = root/"test/disc"

    def tearDown(self):
        self.tmp.cleanup()

    def test_overlay_replaces_links_without_touching_original(self):
        record = td.build(self.disc,self.package,self.out)
        self.assertEqual((self.disc/"Media/DB/gamedb.slt").read_bytes(),b"original db")
        self.assertEqual((self.out/"Media/DB/gamedb.slt").read_bytes(),b"candidate db")
        self.assertEqual((self.out/"Media/Cars/NEW.zip").read_bytes(),b"car")
        self.assertEqual(record["replaced"],["Media/DB/gamedb.slt"])
        self.assertEqual(record["added"],["Media/Cars/NEW.zip"])
        self.assertTrue((self.out/"default.xex").samefile(self.disc/"default.xex"))
        self.assertFalse((self.out/"Media/DB/gamedb.slt").samefile(self.disc/"Media/DB/gamedb.slt"))

    def test_existing_or_nested_output_rejected(self):
        self.out.mkdir(parents=True)
        with self.assertRaises(td.TestDiscError):
            td.build(self.disc,self.package,self.out)
        with self.assertRaises(td.TestDiscError):
            td.build(self.disc,self.package,self.disc/"copy")


if __name__=="__main__":
    unittest.main()
