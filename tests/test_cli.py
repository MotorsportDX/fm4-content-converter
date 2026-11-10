"""Disc images, disc identity, frozen data and the mod package format of the one-command converter."""
import json
from pathlib import Path
import struct
import tempfile
import unittest

from fm4_converter import data, items
from fm4_converter.archives.xiso import SECTOR, MAGIC, XISO, FormatError
from fm4_converter.discs import Disc, DiscError, execution_info, FM3, FM4


def xex(title, number, count=2, media=0x1234):
    """A XEX2 header with only the execution info optional header."""
    head = bytearray(0x18 + 8)
    head[:4] = b"XEX2"
    struct.pack_into(">I", head, 0x14, 1)
    struct.pack_into(">II", head, 0x18, 0x00040006, len(head))
    return bytes(head) + struct.pack(">IIIIBBBB", media, 0, 0, title, 0, 0, number, count)


def directory(entries, next_sector):
    """One directory table: entries chained through their right subtree offsets. `entries`:
    [(name, data bytes or a nested dict)]; returns (table, [(sector, payload)])."""
    table, placed, offsets = bytearray(), [], []
    for name, _ in entries:
        offsets.append(len(table))
        table += bytes(14 + len(name))
        table += b"\xff" * (-len(table) % 4)
    for i, (name, payload) in enumerate(entries):
        right = offsets[i + 1] // 4 if i + 1 < len(entries) else 0xFFFF
        if isinstance(payload, dict):
            sub, sub_placed = directory(list(payload.items()), next_sector + 1)
            start, size, attributes = next_sector, len(sub), 0x10
            placed.append((next_sector, sub))
            placed += sub_placed
            next_sector = max(s for s, _ in placed) + max(1, -(-len(placed[-1][1]) // SECTOR))
        else:
            start, size, attributes = next_sector, len(payload), 0x80
            placed.append((next_sector, payload))
            next_sector += max(1, -(-len(payload) // SECTOR))
        struct.pack_into("<HHIIBB", table, offsets[i], 0xFFFF, right, start, size, attributes, len(name))
        table[offsets[i] + 14:offsets[i] + 14 + len(name)] = name.encode()
    return bytes(table), placed


def image(tree, base=0):
    """An XDVDFS image whose game partition starts at `base`."""
    root, placed = directory(list(tree.items()), 34)
    sectors = {33: root, **dict(placed)}
    end = max(s + max(1, -(-len(d) // SECTOR)) for s, d in sectors.items())
    out = bytearray(base + end * SECTOR)
    descriptor = bytearray(SECTOR)
    descriptor[:len(MAGIC)] = MAGIC
    struct.pack_into("<II", descriptor, len(MAGIC), 33, len(root))
    descriptor[0x7EC:0x7EC + len(MAGIC)] = MAGIC
    out[base + 32 * SECTOR:base + 33 * SECTOR] = descriptor
    for sector, payload in sectors.items():
        out[base + sector * SECTOR:base + sector * SECTOR + len(payload)] = payload
    return bytes(out)


TREE = {"default.xex": xex(FM3, 1), "Media": {
    "DB": {"gamedb.slt": b"db" * 3000}, "Cars": {"A.zip": b"a", "B.zip": b"bb"}, "Wheels": {"W.zip": b"w"},
    "StringTables": {"EN.zip": b"en"}, "UI": {"Textures.zip": b"ui"}, "Other.bin": b"x"}}


class XisoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, payload):
        path = self.root / name
        path.write_bytes(payload)
        return path

    def test_reads_files_case_insensitively_at_each_partition_offset(self):
        for base in (0, 0x2080000):
            with XISO(self.write(f"game{base}.iso", image(TREE, base))) as iso:
                self.assertEqual(iso.base, base)
                self.assertEqual(iso.read("media/db/GAMEDB.slt"), b"db" * 3000)
                self.assertEqual([p.as_posix() for p in iso.files("Media/Cars")],
                                 ["Media/Cars/A.zip", "Media/Cars/B.zip"])

    def test_extracts_only_the_prefixes_and_resumes(self):
        with XISO(self.write("game.iso", image(TREE))) as iso:
            out = self.root / "out"
            self.assertEqual(iso.extract(["Media/Cars", "Media/DB"], out), 3 + 6000)
            self.assertFalse((out / "Media/Wheels").exists())
            self.assertFalse((out / "Media/Other.bin").exists())
            self.assertEqual((out / "Media/Cars/B.zip").read_bytes(), b"bb")
            self.assertEqual(iso.extract(["Media/Cars", "Media/DB"], out), 0)

    def test_rejects_a_file_that_is_not_an_image(self):
        with self.assertRaises(FormatError):
            XISO(self.write("plain.iso", bytes(40 * SECTOR)))

    def test_disc_identity_from_folder_and_image(self):
        iso = self.write("fm3.iso", image(TREE))
        disc = Disc(iso, "fm3-disc1")
        self.assertEqual((disc.title, disc.number, disc.image), (FM3, 1, True))
        self.assertEqual(Disc(iso).role, "fm3-disc1")
        root = disc.root(self.root / "cache")
        self.assertTrue((root / "Media/DB/gamedb.slt").is_file())
        self.assertFalse((root / "Media/Other.bin").exists())
        folder = self.root / "FM4"
        (folder / "Media").mkdir(parents=True)
        (folder / "default.xex").write_bytes(xex(FM4, 1))
        self.assertEqual(Disc(folder / "Media", "fm4-disc1").path, folder)
        with self.assertRaisesRegex(DiscError, "expected Forza Motorsport 3 disc 2"):
            Disc(iso, "fm3-disc2")
        bare = Disc(self.write("fm3b.iso", image({"default.xex": xex(FM3, 1)})), "fm3-disc1")
        with self.assertRaisesRegex(DiscError, "lacks Media/DB"):
            bare.root(self.root / "cache2")

    def test_execution_info(self):
        self.assertEqual(execution_info(xex(FM4, 2, 2, 0x26FF1101)), (FM4, 2, 2, 0x26FF1101))
        with self.assertRaises(DiscError):
            execution_info(b"XEX1" + bytes(40))


class FrozenDataTests(unittest.TestCase):
    def test_every_file_matches_its_recorded_hash(self):
        for name in data.FILES:
            self.assertTrue(data.path(name).is_file())

    def test_fm2_car_list_and_trimmed_rules(self):
        self.assertEqual(len(data.load("fm2/cars.json")["cars"]), 55)
        rules = data.load("fm3/rules.json")
        self.assertNotIn("selection_results", rules["remaining7"])
        self.assertIn("models", rules["remaining7"])


class ModTests(unittest.TestCase):
    def test_write_and_verify(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stage = root / "stage"
            (stage / "Media/Cars").mkdir(parents=True)
            (stage / "Media/DB").mkdir(parents=True)
            (stage / "Media/DB/gamedb.slt").write_bytes(b"package database")
            (stage / "Media/Cars/X.zip").write_bytes(b"car")
            packaged = items.item("car:1", "car", "X", "X (FM3)", identity=items.car_identity(1, "X"))
            packaged["files"]["Media/Cars/X.zip"] = 80
            skipped = items.item("car:Y", "car", "Y", status="skipped", error="needs FM3 Disc 2")
            package = root / "package"
            described = items.write(package, stage, [packaged, skipped], {},
                                    dict(id="fm3-cars", name="FM3 cars", kind="car-overlay", source_game="FM3",
                                         edition="fm3", sources=[], built_against={}, notes=[]))
            # Only the items' files: the package database stays in the stage.
            self.assertEqual(sorted(described["files"]), ["Media/Cars/X.zip"])
            self.assertEqual((described["packaged"], described["failed"], described["skipped"]), (1, 0, 1))
            self.assertEqual((described["format_version"], described["priority"]), (2, 30))
            self.assertEqual(json.loads((package / "mod.json").read_text(encoding="utf-8"))["format"], "fm4-mod")
            self.assertEqual(items.verify(package)["id"], "fm3-cars")
            (package / "files/Media/Cars/X.zip").write_bytes(b"changed")
            with self.assertRaisesRegex(items.ModError, "changed"):
                items.verify(package)
            (package / "files/Media/Cars/X.zip").write_bytes(b"car")
            (package / "files/extra.txt").write_bytes(b"")
            with self.assertRaisesRegex(items.ModError, "not listed"):
                items.verify(package)


if __name__ == "__main__":
    unittest.main()
