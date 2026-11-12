import struct
import unittest

import numpy as np

from fm4_converter.fm2 import track_shader as ts


def control(count, sequence):
    """One `exec_end` of `count` instructions from address 1 (the slot after the control flow)."""
    d0 = 1 | count << 12 | sequence << 16
    return [d0, 2 << 12, 0]


def vfetch(dst, word, signed=True):
    # x, y fetched; z = 0, w = 1; `16_16` integers.
    swizzle = 0 | 1 << 3 | 4 << 6 | 5 << 9
    return [dst << 12 | 1 << 19, swizzle | int(signed) << 12 | 1 << 13 | 25 << 16, 6 | word << 8]


def dp4_export(out, mask, temp, constant):
    return [out | 1 << 15 | mask << 16 | ts.RETAIN_PREV << 26, 0,
            temp << 16 | constant << 8 | ts.DP4 << 24 | 1 << 31]


def tfetch(sampler, src):
    return [1 | src << 5 | sampler << 20 | (0 | 1 << 2) << 26, 0o7777, 0]


def shader(kind, words):
    return ts.Shader(kind, {}, ts._instructions(struct.pack(f">{len(words)}I", *words)))


class ShaderTests(unittest.TestCase):
    def test_a_tiling_matrix_reaches_the_sampler(self):
        vs = shader(0x41, control(3, 0b000001) + vfetch(3, 5) + dp4_export(2, 1, 3, 72) + dp4_export(2, 2, 3, 73))
        ps = shader(0x00, control(1, 0b01) + tfetch(1, 2))
        constants = {72: (1 / 1024, 0.0, 0.0, -3.5), 73: (0.0, 1 / 1024, 0.0, -3.5)}
        coords = ts.sampler_coordinates(ps, ts.vertex_outputs(vs, constants))
        words = np.zeros((2, 6), np.uint32)
        words[:, 5] = [(2048 << 16) | 1024, (0xFFFF << 16) | 3072]     # x high, y low
        u, v = coords[1]
        self.assertEqual(ts.evaluate(u, words).tolist(), [-1.5, -3.5 - 1 / 1024])
        self.assertEqual(ts.evaluate(v, words).tolist(), [-2.5, -0.5])

    def test_an_unknown_constant_keeps_the_base(self):
        x = ts.Value({(4, 0, True): 1 / 32767})
        atlas = ts.add(ts.mul(x, ts.UNKNOWN), ts.UNKNOWN)
        self.assertIsNone(atlas.affine)
        self.assertEqual(atlas.base, x.affine)
        self.assertIsNone(ts.mul(ts.UNKNOWN, ts.UNKNOWN).base)

    def test_choose_prefers_the_pair_reading_the_bound_textures(self):
        vs = shader(0x41, control(3, 0b000001) + vfetch(3, 5) + dp4_export(2, 1, 3, 72) + dp4_export(2, 2, 3, 73))
        reads = shader(0x00, control(1, 0b01) + tfetch(1, 2))
        other = shader(0x00, control(1, 0b01) + tfetch(1, 7))
        constants = {72: (1.0, 0.0, 0.0, 0.0), 73: (0.0, 1.0, 0.0, 0.0)}
        coords, ps = ts.choose([other, vs, reads], constants, {1: 4})
        self.assertIs(ps, reads)
        self.assertIsNotNone(coords[1][0].affine)
        self.assertFalse(ps.kills)
