import struct
import unittest

from fm4_converter.fm3 import track_rmb


def pm4_tiled_pass():
    """A small recorded pass shaped like FM3 pass 4: MSAA surface, tiling blocks, a draw."""
    w = [0x00002000, 0x14020500, 0x00002301, 0x0000C003]          # type-0: 0x2000, 0x2301
    for offset in (0, 0x7F000000):
        w += [0xC0006000, 3 if not offset else 0xC]               # SET_BIN_SELECT
        w += [0xC0032D01, 0x40080, offset, 0, 0x01000100]         # predicated window SET_CONSTANT
    w += [0xC0006100, 0]                                          # SET_BIN_MASK
    w += [0xC0032201, 0, 0xAA0006, 0xFFFFFFFF]                    # predicated DRAW_INDX
    return struct.pack(f">{len(w)}I", *w)


def model(version=4, slots=15, filled=(3, 6, 9, 12)):
    body = struct.pack(">I", version) + b"\x3f\x80\0\0" * 30
    streams, pools = b"", [b"", b"", b""]
    first = second = 0
    for i in range(slots):
        if i in filled:
            header, physical, init = bytes([i]) * 12, pm4_tiled_pass() + bytes([i]) * 4, bytes([i]) * 16
            streams += struct.pack(">IIIIIIIII", 2, 1, 0x10, 0x20, 1, 0x30, 0x40, len(header), len(physical))
            streams += struct.pack(">I", len(init))
            for k, part in enumerate((header, physical, init)):
                step = 32 if k == 1 else 4
                pad = (-len(pools[k])) % step if part and pools[k] else 0
                pools[k] += b"\0" * pad + part
            first, second = first + 1, second + 1
        else:
            streams += struct.pack(">IIIIII", 2, 0, 0, 0, 0, 0)
    head = struct.pack(">6I", 1, len(pools[0]), len(pools[1]), len(pools[2]), 8 * second, 8 * first)
    return body + head + streams + pools[0] + pools[1] + pools[2]


class TrackRmbTests(unittest.TestCase):
    def test_group_round_trip(self):
        data = model()
        g = track_rmb.group(data)
        self.assertEqual(len(g.slots), 15)
        self.assertEqual(data[g.at:], g.encode())
        self.assertEqual([i for i, p in enumerate(g.parts) if p[1]], [3, 6, 9, 12])

    def test_to_v5_adds_untiled_single_sample_pass_5(self):
        data = model()
        out = track_rmb.to_v5(data)
        self.assertEqual(track_rmb.model_version(out), 5)
        g = track_rmb.group(out)
        self.assertEqual(len(g.slots), 18)
        old = track_rmb.group(data)
        self.assertEqual(g.parts[:15], old.parts)
        self.assertEqual(g.slots[15]["stream"], old.slots[12]["stream"])
        pass5 = g.parts[15][1]
        self.assertEqual(len(pass5), len(old.parts[12][1]))
        w = struct.unpack(f">{len(pass5) // 4}I", pass5)
        self.assertEqual(w[1], 0x14000500)
        self.assertEqual(w[3], 0)
        self.assertNotIn(0xC0006000, w)
        self.assertNotIn(0xC0006100, w)
        windows = [i for i, x in enumerate(w) if x >> 30 == 3 and (x >> 8) & 0x7F == 0x2D]
        self.assertEqual(len(windows), 1)
        self.assertEqual(w[windows[0]] & 1, 0)
        self.assertEqual(w[windows[0] + 2:windows[0] + 5], (0, 0, 720 << 16 | 1280))
        self.assertIn(0xC0032201, w)
        self.assertEqual(out[4:old.at], data[4:old.at])

    def test_rejects_other_versions_and_broken_groups(self):
        with self.assertRaises(ValueError):
            track_rmb.to_v5(model(version=6, slots=21))
        with self.assertRaises(ValueError):
            track_rmb.group(model()[:-3])


if __name__ == "__main__":
    unittest.main()
