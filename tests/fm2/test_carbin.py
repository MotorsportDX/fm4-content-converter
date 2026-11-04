"""FM2 .carbin reader and FM2 -> FM3 transcoder on a synthetic wheel."""
import struct
import unittest

from fm4_converter.fm2 import carbin, transcode
from fm4_converter.fm3 import carbin_audit

from . import samples


class ReaderTests(unittest.TestCase):
    def test_uv_words_are_fixed_point(self):
        self.assertEqual(carbin.uv_word(32768), 0.0)
        self.assertEqual(carbin.uv_word(0), -25.0)
        self.assertAlmostEqual(carbin.uv_word(32768 + 1311), 1.0, places=3)

    def test_normals_are_signed_11_11_10(self):
        self.assertEqual(carbin.unpack_normal(511 << 22), (0.0, 0.0, 1.0))
        self.assertEqual(carbin.unpack_normal(0x401), (-1.0, 0.0, 0.0))

    def test_fm2_detection_needs_marker_and_size(self):
        data = samples.wheel()
        self.assertTrue(carbin.is_fm2(data))
        self.assertFalse(carbin.is_fm2(data[:0x200]))
        self.assertFalse(carbin.is_fm2(struct.pack('>I', 3) + data[4:]))

    def test_strip_faces_drop_restarts_and_degenerates(self):
        # Winding alternates per strip position and resets after a restart, as in Forza Studio.
        strip = carbin.SubSection('x', carbin.TRI_STRIP, 1, 2, [0, 1, 2, 3, -1, 4, 4, 5, 6, 7], 0)
        self.assertEqual(carbin.faces(strip), [(0, 1, 2), (2, 1, 3), (5, 4, 6), (5, 6, 7)])

    def test_wheel_sections_and_shared_buffer(self):
        model = carbin.parse(samples.wheel())
        self.assertEqual(model.type_id, 1)
        section, = model.sections
        self.assertEqual((section.name, section.buffer, len(model.glass), len(model.body)), ('rim', 'glass', 4, 0))
        self.assertEqual(carbin.faces(section.subsections[0]), [(0, 1, 2), (0, 2, 3)])
        self.assertEqual(model.glass[2][0], (1.0, 1.0, 0.0))

    def test_index_outside_buffer_is_rejected(self):
        with self.assertRaisesRegex(carbin.FormatError, 'index 4 >= glass buffer 4'):
            carbin.parse(samples.wheel(indices=(0, 1, 4)))

    def test_unknown_vertex_size_is_rejected(self):
        data = samples.wheel()
        glass = data.index(samples.u32(4) + samples.u32(60))
        data = data[:glass + 4] + samples.u32(40) + data[glass + 8:]
        with self.assertRaisesRegex(carbin.FormatError, 'vertex size 40'):
            carbin.parse(data)


class TranscodeTests(unittest.TestCase):
    def test_wheel_becomes_a_readable_fm3_wheel(self):
        data, summary = transcode.convert(samples.wheel())
        self.assertEqual((summary['sections'], summary['vertices'], summary['subsections']), (1, 4, 1))
        model = carbin_audit.parse(data, 'FM3')
        self.assertEqual(model['type'], 2)
        section, = model['sections']
        self.assertEqual([(m['name'], m['lod'], m['primitive']) for m in section['meshes']], [('rim', 1, 4)])
        self.assertEqual((section['lod']['count'], section['lod']['stride']), (4, 40))
        self.assertEqual(model['lists'], [[0], []])

    def test_vertices_keep_position_and_normal_and_convert_uv(self):
        data, _ = transcode.convert(samples.wheel())
        pool = carbin_audit.parse(data, 'FM3')['sections'][0]['lod']['data']
        x, y, z, w, u, v = struct.unpack_from('>6e', pool, 40 * 2)
        self.assertEqual((x * w, y * w, z * w), (1.0, 1.0, 0.0))
        self.assertAlmostEqual(u, 1.0, places=3)
        self.assertAlmostEqual(v, 1.0, places=3)
        self.assertEqual(pool[40 * 2 + 16:40 * 2 + 20], struct.pack('>I', 511 << 22))

    def test_tangent_axis_packs_back_to_unit_vectors(self):
        import numpy as np
        words = transcode.pack111110(np.array([[0.0, 0.0, 1.0], [-1.0, 0.0, 0.0]]))
        self.assertEqual([carbin.unpack_normal(int(w)) for w in words], [(0.0, 0.0, 1.0), (-1.0, 0.0, 0.0)])

    def test_asymmetric_section_bounds_are_rejected(self):
        data = bytearray(samples.wheel())
        bounds = data.index(struct.pack('>3f', 1, 1, 1))
        data[bounds:bounds + 4] = struct.pack('>f', 2)
        with self.assertRaisesRegex(transcode.FormatError, 'asymmetric bounds'):
            transcode.convert(bytes(data))


if __name__ == '__main__':
    unittest.main()
