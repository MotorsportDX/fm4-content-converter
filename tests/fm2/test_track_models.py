import struct
import unittest

import numpy as np

from fm4_converter.fm2 import track_env, track_models as tm
from fm4_converter.fm3 import track_rmb

UVOS = (0.25, -0.5, 2.0, 1.5)


def physical(count=36, prim=6):
    """A slot's recorded pass: the vertex shader constants c0.. (UVOffsetScale first) and a DRAW_INDX."""
    w = [0x000F4000] + list(struct.unpack(">4I", struct.pack(">4f", *UVOS))) + [0] * 12
    w += [0xC0032200 | 1, 0, (count << 16) | 0x0800 | prim, 0, 0x40000000 | count]
    return struct.pack(f">{len(w)}I", *w)


def group(slots=21, filled=(3, 9, 15)):
    streams, pools = b"", [b"", b"", b""]
    n = 0
    for i in range(slots):
        if i in filled:
            header, phys, init = bytes([i]) * 12, physical(), bytes([i]) * 16
            streams += struct.pack(">IIIIIIIII", 2, 1, 0x10, 0x20, 1, 0x30, 0x40, len(header), len(phys))
            streams += struct.pack(">I", len(init))
            for k, part in enumerate((header, phys, init)):
                step = 32 if k == 1 else 4
                pad = (-len(pools[k])) % step if part and pools[k] else 0
                pools[k] += b"\0" * pad + part
            n += 1
        else:
            streams += struct.pack(">IIIIII", 2, 0, 0, 0, 0, 0)
    head = struct.pack(">6I", 1, len(pools[0]), len(pools[1]), len(pools[2]), 8 * n, 8 * n)
    return head + streams + pools[0] + pools[1] + pools[2]


def template(stride=24, vertices=3, indices=(0, 1, 2)):
    """An FM4 track model of one sub-model and one mesh (RMB v6)."""
    out = struct.pack(">I", 6) + struct.pack(">8f", *([0.0] * 8)) + struct.pack(">16f", *([1.0] * 16))
    out += struct.pack(">IIIII", 4, 4, 0, 1, 1)                     # TBaseModel, ordered, container
    out += struct.pack(">I", 1) + struct.pack(">12f", *([0.0] * 12))  # sub-model: offset, min, max
    out += struct.pack(">II", 1, 4) + b"name"
    out += struct.pack(">III", 2, vertices, stride) + bytes(vertices * stride)
    out += struct.pack(">II", 1, 1)                                 # mesh container
    out += struct.pack(">II", 1, 2) + struct.pack(">I", 4) + b"mesh"
    out += struct.pack(">III", 0, 6, 0)                             # LOD, primitive, material
    out += struct.pack(">I", 1) + struct.pack(">8f", *([0.0] * 4 + [1.0] * 4)) + struct.pack(">4f", *UVOS)
    out += struct.pack(">III", 3, len(indices), 2) + struct.pack(f">{len(indices)}H", *indices)
    out += struct.pack(">I", 0) + b"\x3f\x80\0\0" * 8               # mesh flags, materials and names
    return out + group()


class TemplateTests(unittest.TestCase):
    def test_build_replaces_geometry_unpacking_and_draws(self):
        t = tm.Template(template(), "diff_1_nocube", 24)
        verts = bytes(range(24)) * 4
        out = t.build(verts, [0, 1, 2, 2, 1, 3], ((-1.0, -2.0, -3.0), (1.0, 2.0, 3.0)), (0.0, 0.1, 0.5, 0.25))
        again = tm.Template(out, "diff_1_nocube", 24)
        self.assertEqual((again.vcount, again.icount), (4, 6))
        self.assertEqual(again.uvos, struct.unpack(">4f", struct.pack(">4f", 0.0, 0.1, 0.5, 0.25)))
        self.assertEqual(struct.unpack_from(">I", out, again.prim_at)[0], 4)
        g = track_rmb.group(out)
        for part in g.parts:
            if part[1]:
                w = struct.unpack(f">{len(part[1]) // 4}I", part[1])
                init = w[w.index(0xC0032201) + 2]
                self.assertEqual((init >> 16, init & 0x3F, init & 0xFFC0), (6, 4, 0x0800))
                self.assertEqual(w[w.index(0xC0032201) + 4] & 0xFFFFFF, 6)

    def test_template_needs_its_stride(self):
        with self.assertRaises(tm.FormatError):
            tm.Template(template(), "diff_nolm_vclr_1", 20)


class VertexTests(unittest.TestCase):
    def test_uv_words_span_the_range(self):
        uv = np.array([[-1.0, 0.5], [1.0, 0.5], [0.0, 1.5]])
        words, uvos = tm.uv_words(uv)
        self.assertEqual(uvos, (-1.0, 0.5, 2.0, 1.0))
        self.assertEqual([int(w >> 16) for w in words], [0, 65535, 32768])
        self.assertEqual([int(w & 0xFFFF) for w in words], [0, 0, 65535])

    def test_layout_tells_normals_from_texture_coordinates(self):
        n = tm.pack101010(np.array([[0.0, 1.0, 0.0]] * 4))
        with_normal = np.zeros((4, 5), ">u4")
        with_normal[:, 3] = n
        self.assertEqual(tm.layout(with_normal.view(np.uint8).reshape(4, 20), 20), (3, 4, None))
        uvs = np.zeros((4, 5), ">u4")
        uvs[:, 3] = 0x12345678
        self.assertEqual(tm.layout(uvs.view(np.uint8).reshape(4, 20), 20), (None, 3, 4))

    def test_fixed_point_coordinates(self):
        self.assertEqual(tm._fixed([0x4000C000]).tolist(), [[1.0, -1.0]])


class PvsTests(unittest.TestCase):
    def test_version_11_reads_to_its_end(self):
        def cmesh(textures):
            return struct.pack(f">I{len(textures)}I", len(textures), *textures) + struct.pack(">I12f", 0, *([0.0] * 12))
        data = b"FPVS" + struct.pack(">IIHH", 11, 13_000_000, 0, 25)
        data += struct.pack(">I", 1) + struct.pack(">IH", 1, 0) + struct.pack(">II", 1, 5) + struct.pack(">IB", 1, 1)
        data += struct.pack(">I", 1) + struct.pack(">IIffffI", 1, 0, -0.0625, 0.0625, 0.0156, 0.0156, 0xC)
        data += struct.pack(">I", 1) + cmesh([0])
        data += cmesh([]) + cmesh([3, 4]) + struct.pack(">I", 10) + b"newyorkout" + b"\x01"
        p = tm.pvs11(data)
        self.assertEqual(p["name"], "newyorkout")
        self.assertEqual(p["zones"][0], {"models": [0], "textures": [5], "flags": [1]})
        self.assertEqual(p["sky"][1]["textures"], [3, 4])
        with self.assertRaises(tm.FormatError):
            tm.pvs11(data + b"\0")


class RoleTests(unittest.TestCase):
    def test_diffuse_and_lightmap(self):
        textures = [(1, 0, 1.0, 1.0, 0.0, 0.0, 0x4), (2, 1, -0.0625, 0.0625, 0.0, 0.0, 0xC),
                    (3, 2, 1.0, 1.0, 0.0, 0.0, 0x0)]
        draw = tm.Draw(0, 0, None, None, None, None, None, {0: 1, 1: 2, 2: 0}, False, False)
        self.assertEqual(track_env.roles(draw, textures, [0, 1, 2]), (0, 1))
        draw.samplers = {}
        self.assertEqual(track_env.roles(draw, textures, [1, 2]), (1, None))


class CameraAndAudioTests(unittest.TestCase):
    DONOR_CAMS = (b'<Cams CutQueueType="TrackSeg" NumCams="1"><Cam Version="3" Type="Animateable" StartCut="0">'
                  b'<Anim PosAnimType="WorldSpace" RotAnimType="TargetCar" NumKeys="1"><Key Time="0"/></Anim>'
                  b'<PostEffectsAnim NumKeys="0"/></Cam></Cams>')

    def test_segment_cams_take_fm4s_format(self):
        fm2 = (b'<TrackSegCams><Cam Type="Animateable" CameraManShakeOn="true" StartCut="-0.25">'
               b'<Anim PosAnimType="CarSpace" CamRotType="TargetCar" PlaybackTime="4.0" EaseInPos="0.2" EaseOutPos="0.9">'
               b'<Keys><Key PosX="1" PosY="2" PosZ="3"/><Key PosX="4" PosY="5" PosZ="6"/></Keys></Anim></Cam>'
               b'<Cam Type="Hood" StartCut="0.5"/></TrackSegCams>')
        import xml.etree.ElementTree as ET
        out = ET.fromstring(track_env.segment_cams(fm2, self.DONOR_CAMS))
        self.assertEqual(out.get("NumCams"), "1")
        cam = out.find("Cam")
        self.assertEqual((cam.get("StartCut"), cam.get("CameraManShakeOn")), ("0.750000", "1"))
        self.assertIsNotNone(cam.find("PostEffectsAnim"))
        anim = cam.find("Anim")
        self.assertEqual((anim.get("PosAnimType"), anim.get("NumKeys")), ("CarSpace", "2"))
        self.assertEqual([k.get("Time") for k in anim], ["0.000000", "4.000000"])

    def test_audio_keeps_fm2_crowds_on_fm4_events(self):
        self.assertEqual(track_env.shared_event("CRWD_SML_5"), ("dynamic", "CRWD_SMALL_2"))
        self.assertEqual(track_env.shared_event("REF_OVERPASS_3"), ("static", "REF_OVERPASS_1"))
        self.assertIsNone(track_env.shared_event("WAMB_SUBWAY"))
        donor = (b'<TrackAudio soundbank="Tsukuba"><Track3D><Object eventName="WAMB_ANNOUNCE"/></Track3D>'
                 b'<SharedAudio soundbank="S"><Shared3D><Object eventName="REF_MED_1"/></Shared3D></SharedAudio>'
                 b'<SharedAudioDynamic soundbank="D"><Shared3D/></SharedAudioDynamic></TrackAudio>')
        fm2 = (b'<TrackAudio soundbank="newyork"><Track3D>'
               b'<Object objectname="c" eventname="CRWD_LRG_2"><Position1 x="1"/></Object>'
               b'<Object objectname="s" eventname="WAMB_SIREN"/></Track3D></TrackAudio>')
        import xml.etree.ElementTree as ET
        out = ET.fromstring(track_env.audio_xml(fm2, donor))
        self.assertEqual(out.get("soundbank"), "Tsukuba")
        self.assertEqual(len(out.find("Track3D")), 0)
        self.assertEqual(len(out.find("SharedAudio/Shared3D")), 0)
        crowd = out.find("SharedAudioDynamic/Shared3D/Object")
        self.assertEqual((crowd.get("eventName"), crowd.find("Position1").get("x")), ("CRWD_LRG_2", "1"))


if __name__ == "__main__":
    unittest.main()
