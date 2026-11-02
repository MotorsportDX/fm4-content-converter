import io
import math
import struct
import unittest
import zipfile

from fm4_converter.fm3 import track_env, track_grid, track_pvs


def circle(n=400, radius=100.0):
    """AI centreline of a circle, counter-clockwise from (radius, 0)."""
    angles = [2 * math.pi * i / n for i in range(n)]
    return {"fWaypointX": [radius * math.cos(a) for a in angles],
            "fWaypointY": [radius * math.sin(a) for a in angles]}


def grid_row(points):
    """An FM3 StartGridPositions row: id, then 12 x (x, y, z, hx, hy, hz)."""
    row = [1]
    for x, z, hx, hz in points:
        row += [x, 0.0, z, hx, 0.0, hz]
    return row


def on_circle(back, start=0.0, radius=100.0, lateral=0.0):
    """World position and heading of a slot `back` metres behind the start fraction."""
    a = 2 * math.pi * start - back / radius
    r = radius - lateral
    return r * math.cos(a), r * math.sin(a), -math.sin(a), math.cos(a)


def minimal_pvs():
    cell = {"u0": 0xFFFF, "u4": 0, "u8": 0, "u12": 0xFFFFFFFF, "v16": (0.5,), "u32": 0xFFFF,
            "u34_38": (0, 0, 0), "f40": (0.0, 0.0, 0.0), "u52": (0,) * 9}
    obj = {"refs": [1], "ids": [], "mat": (0.0,) * 16, "vec": (-1.0, -1.0, -1.0, 0.0)}
    return {"ver": 24, "w2": 7, "w3": None, "h0": 0, "h2": 25, "l4": [([0], [0], [0], [0])],
            "l20": [(1, 2, 1.0, 1.0, 0.0, 0.0, 4)], "l172": ["a"], "l36": [dict(cell)], "l52": [dict(obj)],
            "legacy_cell": dict(cell), "legacy_obj": dict(obj), "l68": [], "s132": "tout",
            "b160": 1, "b196": 0, "l200": [], "l192": [[1]]}


class TrackEnvTests(unittest.TestCase):
    def test_ai_names_follow_fm4_lookup(self):
        self.assertEqual(track_env.canonical_ai_name("newyork_03_r.seg", "NewYork"), "NewYork_03_R.seg")
        self.assertEqual(track_env.canonical_ai_name("Level1/newyork_01.bin", "NewYork"), "Level1/NewYork_01.bin")
        self.assertEqual(track_env.canonical_ai_name("SegmentProfiles/newyork_02_r/Default.bin", "NewYork"),
                         "SegmentProfiles/NewYork_02_R/Default.bin")

    def test_short_mlp_files_are_padded(self):
        short = b"MLPDataStart:\nx:int32:1:1:  20\nMLPDataEnd:\n" + b"\0\0\0\1"
        self.assertEqual(len(track_env.pad_mlp(short)), track_env.MLP_READ)
        self.assertTrue(track_env.pad_mlp(short).startswith(short))
        self.assertEqual(track_env.pad_mlp(b"x" * 10), b"x" * 10)
        long = b"MLPDataStart:" + bytes(2000)
        self.assertEqual(track_env.pad_mlp(long), long)

    def test_track_files_convert_pvs_and_settings(self):
        data = track_pvs.write(minimal_pvs())
        out = track_pvs.parse(track_env.convert_track_file("Ribbon_00/t_00.pvs", data, None))
        self.assertEqual(out["ver"], 27)
        self.assertEqual(out["a84"], [1])  # no l68 cells: special cell at slot 0, as FM4's AmalfiGP 01
        self.assertEqual(track_env.convert_track_file("TrackSettings.xml", b"fm3", b"fm4"), b"fm4")
        self.assertEqual(track_env.convert_track_file("Ribbon_00/CollObjs.xml", b"x", b"fm4"), b"x")

    def test_zip_directory_uses_fm4_dirsize(self):
        data = track_env.zip_bytes({"a.bin": b"1", "b.bin": b"22"})
        start, size, count = track_env.zip_directory(data[-22:])
        self.assertEqual(count, 2)
        self.assertEqual(start + size, len(data))
        with self.assertRaises(ValueError):
            track_env.zip_directory(data[-21:] + b"x")


class TrackGridTests(unittest.TestCase):
    def test_slots_measure_from_start_fraction(self):
        line = circle()
        backs = [6.0 * (k + 1) for k in range(12)]
        rows = track_grid.convert(9, grid_row([on_circle(b, start=0.25) for b in backs]), line, start=0.25)
        self.assertEqual(len(rows), 16)
        for (gid, k, back, right, yaw), want in zip(rows, backs):
            self.assertAlmostEqual(back, want, delta=0.2)
        self.assertTrue(all(b[2] > a[2] for a, b in zip(rows, rows[1:])))

    def test_eight_car_grid_is_extended(self):
        line = circle()
        backs = [6.0 * (k + 1) for k in range(8)]
        points = [on_circle(b) for b in backs] + [on_circle(40.0)] + [(500.0, 500.0, 0.0, 1.0)] + [on_circle(40.0)] * 2
        rows = track_grid.convert(3, grid_row(points), line)
        self.assertEqual([r[1] for r in rows], list(range(16)))
        self.assertAlmostEqual(rows[8][2], rows[4][2] + rows[7][2] - rows[3][2], places=6)
        self.assertTrue(all(b[2] > a[2] for a, b in zip(rows, rows[1:])))

    def test_projection_prefers_the_stretch_at_the_start(self):
        # A line that returns 3 m beside its own start (like Amalfi's coast road).
        xs = [float(i) for i in range(0, 200)] + [200.0] * 3 + [float(i) for i in range(200, -1, -1)]
        ys = [0.0] * 200 + [1.0, 2.0, 3.0] + [3.0] * 201
        line = {"fWaypointX": xs, "fWaypointY": ys}
        dist, back, right, yaw = track_grid.slot(line, 50.0, 0.5, 1.0, 0.0, start=60 / 405)
        self.assertLess(abs(back), 20)


if __name__ == "__main__":
    unittest.main()
