"""FM2 track models (render graph `CAFF21.11.05.0034`) -> FM4 track models and FPVS v27.

FM2 draws each track model through a render graph of its own: a draw program (`.stream`),
vertex and index buffers (`.gpu`), Xenos shaders FM2's renderer feeds, and a PVS of version 11
with one record (`CMesh`) a model. FM4 draws a track model through command buffers recorded
for its own shaders (RMB v5/v6) and a PVS of version 27 with model instances. The two do not
map field by field, so each FM2 draw becomes one FM4 model of one mesh, written from an FM4
model of the player's FM4 Disc 1 with the right technique (`TEMPLATES`): its command buffers,
material and shader file are kept, its geometry, index counts, primitive and texture
coordinate unpacking are replaced. The techniques chosen read only the diffuse texture
(sampler 0) and the lightmap (sampler 7, the second texture of the PVS model), as the FM2
track shaders do for a track's look; FM4's lighting then lights them as its own tracks
(research: FM4-PC docs/analysis/independent-mods.md, section 5).

Formats (big-endian):

- FM2 model: the `.stream` draw program of records `00 LL OP 00` up to op `0x1d`: op 1 draws
  (primitive, index count, index buffer object), op `0x2d` with type 0 binds the model's PVS
  textures to samplers (pairs of list index and sampler << 16), op `0x0c` sets a render state
  (`0x38` cull mode, 0 none; `0x60` alpha test). The render graph ends with its GPU buffers:
  vertex buffers as (object, offset, size), then index buffers as (object, offset, size, 1);
  a draw uses the last vertex buffer that starts before its index buffer. Positions are world
  space floats; texture coordinates are signed 1.14 fixed point; normals `2_10_10_10`.
- FM4 model (`CTrackModel`, template field names from Forza-X360-IO `FM3_rmb_bin.bt`, GPL-3.0,
  a format reference only): bounds, world transform, ordered sub-models, one sub-model with
  its vertex buffer and one mesh (LOD, primitive, material, `UnpackingData` with
  `UVOffsetScale`, index buffer), materials, names and the `CommandBufferGroup`, whose slots
  carry the vertex shader constant `c0` (the mesh's `UVOffsetScale`) and `DRAW_INDX`.
"""
import struct
import zipfile

import numpy as np

from ..fm3 import track_rmb
from ..fm3.integration import archive_read

MAGIC = b"CAFF21.11.05.0034"
END = 0x1D
DRAW, BIND, STATE = 0x01, 0x2D, 0x0C
CULL, ALPHA_TEST = 0x38, 0x60
LIGHTMAP_FLAG = 0x8        # texture table flags of a lightmap atlas entry (FM2 0x8/0xc, FM4 0x9/0xc)
COLOUR_FLAG = 0x4
DRAW_INDX = 0x22


class FormatError(ValueError):
    pass


# --- FM2 -------------------------------------------------------------------------------------

class Model:
    """One FM2 track model (`<media>out.NNNNN.rmb.bin`)."""

    def __init__(self, data):
        if not data.startswith(MAGIC):
            raise FormatError("not a CAFF21.11.05.0034 container")
        self.data = data
        n_names, n_chunks = struct.unpack_from(">II", data, 0x18)
        names_at, header = struct.unpack_from(">II", data, 0x44)
        sections, at = [], 0x50
        while at + 0x28 <= header:
            name = data[at:at + 8].rstrip(b"\0")
            if not name.startswith(b"."):
                break
            sections.append((name.decode(), struct.unpack_from(">I", data, at + 0x10)[0]))
            at += 0x28
        base, cursor = {}, header
        for name, size in sections:
            base[name] = cursor
            cursor += size
        blob = base[".data"] + names_at
        size = struct.unpack_from(">I", data, blob)[0]
        chunk_at = blob + 4 + 4 * n_names + size + 4
        self.chunks = []
        for i in range(n_chunks):
            cid, off, sz = struct.unpack_from(">III", data, chunk_at + 14 * i)
            section = sections[data[chunk_at + 14 * i + 12] - 1][0]
            self.chunks.append((section, cid, data[base[section] + off:base[section] + off + sz]))

    def chunk(self, section, cid):
        for s, c, body in self.chunks:
            if s == section and c == cid:
                return body
        raise FormatError(f"no {section} chunk {cid}")

    @property
    def graph(self):
        return self.chunk(".data", 1)

    def program(self):
        """[(op, body words)] of the `.stream` draw program."""
        found = [body for s, c, body in self.chunks if s == ".stream"]
        if not found:
            return []
        st = found[0]
        o, out = struct.unpack_from(">I", st, 0)[0], []
        while o + 4 <= len(st):
            w = struct.unpack_from(">I", st, o)[0]
            length, op = (w >> 16) & 0xFF, (w >> 8) & 0xFF
            if w >> 24 or w & 0xFF or length < 4 or o + length > len(st):
                raise FormatError(f"bad draw program record at {o:#x}")
            out.append((op, struct.unpack_from(f">{(length - 4) // 4}I", st, o + 4)))
            o += length
            if op == END:
                break
        return out

    def resources(self, first_ib):
        """(vertex buffers, index buffers) of the render graph's resource table, found from the
        first draw's index buffer object: [(object, GPU offset, size)] each."""
        g = self.graph
        gpu = len(self.chunk(".gpu", 1))
        words = struct.unpack(f">{len(g) // 4}I", g[:len(g) // 4 * 4])
        at = next((i for i in range(len(words) - 3) if words[i] == first_ib and words[i + 3] == 1
                   and words[i + 1] + words[i + 2] <= gpu), None)
        if at is None:
            raise FormatError("no resource table")
        ibs, i = [], at
        while i + 3 < len(words) and words[i + 3] == 1 and words[i] < len(g):
            ibs.append(words[i:i + 3])
            i += 4
        # Vertex buffers come before, in ascending GPU order: read back while offsets fall.
        vbs, i, below = [], at - 3, gpu + 1
        while i >= 0 and words[i] < len(g) and words[i + 2] and words[i + 1] < below \
                and words[i + 1] + words[i + 2] <= gpu:
            vbs.insert(0, words[i:i + 3])
            below = words[i + 1]
            if below == 0:
                break
            i -= 3
        return vbs, ibs

    def strides(self):
        """Vertex strides the model's vertex shaders fetch a float3 position at offset 0 with."""
        code = b"".join(b for s, c, b in self.chunks if s == ".gpu")
        found = set()
        for o in range(0, len(code) - 12, 4):
            w0, w1, w2 = struct.unpack_from(">3I", code, o)
            if w0 & 31 == 0 and (w0 >> 19) & 1 and (w1 >> 16) & 63 == 57 and (w2 >> 8) & 0x7FFFFF == 0:
                found.add((w2 & 255) * 4)
        return found - {0}


class Draw:
    """One FM2 draw as FM4 needs it: positions (n, 3) float, normals (n) `2_10_10_10`, texture
    coordinates uv0 and uv1 (n, 2) in texture units (uv1 None without a lightmap layout),
    triangle indices, the PVS list indices bound per sampler, and the render state."""

    def __init__(self, model, number, positions, normals, uv0, uv1, indices, samplers, alpha_test, two_sided):
        self.model, self.number = model, number
        self.positions, self.normals, self.uv0, self.uv1 = positions, normals, uv0, uv1
        self.indices, self.samplers = indices, samplers
        self.alpha_test, self.two_sided = alpha_test, two_sided


def unpack101010(w):
    w = np.asarray(w, dtype=np.int64)
    out = []
    for shift in (0, 10, 20):
        q = (w >> shift) & 0x3FF
        out.append(np.where(q >= 512, q - 1024, q) / 511.0)
    return np.stack(out, -1)


def pack101010(v):
    v = np.clip(np.asarray(v, dtype=np.float64), -1, 1)
    q = np.round(v * 511).astype(np.int64) & 0x3FF
    return (q[..., 0] | (q[..., 1] << 10) | (q[..., 2] << 20)).astype(np.uint32)


def _unit(words):
    """Share of the words that decode as unit `2_10_10_10` vectors."""
    n = np.linalg.norm(unpack101010(words), axis=-1)
    return float(np.mean(np.abs(n - 1) < 0.05)) if len(words) else 0.0


def _fixed(words):
    """Two signed 1.14 coordinates of each `16_16` word, (n, 2)."""
    w = np.asarray(words, dtype=np.uint32)
    return np.stack([(w >> 16).astype(np.uint16).view(np.int16), (w & 0xFFFF).astype(np.uint16).view(np.int16)],
                    -1).astype(np.float64) / 16384.0


def layout(raw, stride):
    """(normal word, uv0 word, uv1 word) columns of a vertex of `stride` bytes (None where
    absent): FM2's layouts are a float3 position and then, by stride, a normal and texture
    coordinates (16: normal or uv; 20: normal and uv, or two uvs; 24 and up: normal and two
    uvs, or uvs only), told apart by whether the word after the position is a unit normal."""
    words = raw.view(">u4") if raw.size else np.zeros((0, stride // 4), ">u4")
    extra = stride // 4 - 3
    if extra < 1:
        return None, None, None
    normal = _unit(words[:, 3]) > 0.9
    rest = list(range(4, 3 + extra)) if normal else list(range(3, 3 + extra))
    uv0 = rest[0] if rest else None
    uv1 = rest[1] if len(rest) > 1 else None
    return 3 if normal else None, uv0, uv1


def face_normals(pos, tris):
    n = np.zeros_like(pos)
    for a, b, c in tris:
        f = np.cross(pos[b] - pos[a], pos[c] - pos[a])
        n[[a, b, c]] += f
    length = np.linalg.norm(n, axis=-1, keepdims=True)
    return np.where(length > 1e-12, n / np.maximum(length, 1e-12), [0.0, 1.0, 0.0])


def draws(model, number=0):
    """Every draw of an FM2 model (op 1 of its draw program) as `Draw`s."""
    program = model.program()
    first = [body for op, body in program if op == DRAW]
    if not first:
        return []
    vbs, ibs = model.resources(first[0][2])
    gpu = model.chunk(".gpu", 1)
    strides = sorted(model.strides())
    out, bound, state = [], {}, {}
    for op, body in program:
        if op == STATE:
            state[body[0]] = body[1]
        elif op == BIND and body[1] & 0xFFFF == 0:
            for k in range(body[1] >> 16):
                bound[body[3 + 2 * k] >> 16] = body[2 + 2 * k]
        elif op == DRAW:
            prim, count, obj = body
            samplers = dict(bound)
            if prim != 4:
                raise FormatError(f"primitive {prim}")
            ib = next(i for i in ibs if i[0] == obj)
            idx = np.frombuffer(gpu, ">u2", count, ib[1]).astype(np.int64)
            vb = max((v for v in vbs if v[1] < ib[1]), key=lambda v: v[1])
            best = None
            for stride in strides:
                n = vb[2] // stride
                if vb[2] % stride or idx.max() >= n:
                    continue
                pos = np.frombuffer(gpu, np.uint8, n * stride, vb[1]).reshape(n, stride)[:, :12].copy()
                pos = pos.view(">f4").reshape(n, 3)[idx]
                if not np.isfinite(pos).all():
                    continue
                size = float(np.ptp(pos, axis=0).max())
                if best is None or size < best[0]:
                    best = (size, stride)
            if best is None:
                out.append(None)    # a vertex layout without a float3 position at its start
                continue
            stride = best[1]
            n = vb[2] // stride
            raw = np.frombuffer(gpu, np.uint8, n * stride, vb[1]).reshape(n, stride)
            used = np.unique(idx)
            remap = np.full(n, -1, np.int64)
            remap[used] = np.arange(len(used))
            raw = raw[used].copy()
            tris = remap[idx][:len(idx) // 3 * 3]
            pos = raw[:, :12].view(">f4").reshape(-1, 3).astype(np.float64)
            ncol, u0, u1 = layout(raw, stride)
            words = raw.view(">u4")
            normals = words[:, ncol].astype(np.uint32) if ncol is not None else \
                pack101010(face_normals(pos, tris.reshape(-1, 3)))
            uv0 = _fixed(words[:, u0]) if u0 is not None else np.zeros((len(pos), 2))
            uv1 = _fixed(words[:, u1]) if u1 is not None else None
            out.append(Draw(number, len(out), pos, normals, uv0, uv1, tris, samplers,
                            bool(state.get(ALPHA_TEST)), state.get(CULL, 2) == 0))
    return out


# --- textures ---------------------------------------------------------------------------------

GAMMA_SIGNS = 0x7E00      # D3DFORMAT SignX, SignY, SignZ = 3 (gamma): FM4's colour and lightmap textures


def texture_records(data):
    """Absolute offsets of the `texture` records (`.data` chunks) of a CAFF container, in order."""
    if not data.startswith(MAGIC):
        raise FormatError("not a CAFF21.11.05.0034 container")
    n_names, n_chunks = struct.unpack_from(">II", data, 0x18)
    names_at, header = struct.unpack_from(">II", data, 0x44)
    sections, at = [], 0x50
    while at + 0x28 <= header:
        name = data[at:at + 8].rstrip(b"\0")
        if not name.startswith(b"."):
            break
        sections.append((name.decode(), struct.unpack_from(">I", data, at + 0x10)[0]))
        at += 0x28
    base, cursor = {}, header
    for name, size in sections:
        base[name] = cursor
        cursor += size
    blob = base[".data"] + names_at
    chunk_at = blob + 4 + 4 * n_names + struct.unpack_from(">I", data, blob)[0] + 4
    out = []
    for i in range(n_chunks):
        cid, off, size = struct.unpack_from(">III", data, chunk_at + 14 * i)
        if sections[data[chunk_at + 14 * i + 12] - 1][0] == ".data":
            start = base[".data"] + off
            if data[start:start + 8] == b"texture\0":
                out.append(start)
    return out


def with_gamma(data, records=None):
    """The container with the gamma signs set in the `D3DFORMAT` (+0x18) of its texture records
    (`records`: their indexes; None for all). FM2's track textures are linear (`0x1A200152`);
    FM4's track shaders read colour and lightmap textures through the hardware's gamma
    (`0x1A207F52`), so FM2's read linear look washed out, a mid grey near white."""
    buf = bytearray(data)
    for k, at in enumerate(texture_records(data)):
        if records is None or k in records:
            fmt = struct.unpack_from(">I", buf, at + 0x18)[0]
            struct.pack_into(">I", buf, at + 0x18, fmt | GAMMA_SIGNS)
    return bytes(buf)


# --- FPVS version 11 ------------------------------------------------------------------------

class _Reader:
    def __init__(self, data):
        self.d, self.o = data, 0

    def take(self, fmt):
        v = struct.unpack_from(">" + fmt, self.d, self.o)
        self.o += struct.calcsize(">" + fmt)
        return v if len(v) > 1 else v[0]

    def many(self, n, kind):
        v = struct.unpack_from(f">{n}{kind}", self.d, self.o)
        self.o += struct.calcsize(f">{n}{kind}")
        return list(v)


def _cmesh(r):
    return {"textures": r.many(r.take("I"), "I"), "u": r.take("I"), "v": [r.take("4f") for _ in range(3)]}


def pvs11(data):
    """FM2's FPVS v11: header, zones (models u16, textures u32, a flag a texture), the texture
    table (as v24's `l20`), one `CMesh` a model (its textures, the lightmap among them, and
    three vectors), two more `CMesh` (the sky) and the name."""
    r = _Reader(data)
    magic, ver, cpu = r.take("4sII")
    if magic != b"FPVS" or ver != 11:
        raise FormatError("not FPVS version 11")
    p = {"cpu": cpu, "h0": r.take("H"), "h2": r.take("H"), "zones": []}
    for _ in range(r.take("I")):
        models = r.many(r.take("I"), "H")
        textures = r.many(r.take("I"), "I")
        flags = r.many(r.take("I"), "B")
        p["zones"].append({"models": models, "textures": textures, "flags": flags})
    p["textures"] = [r.take("IIffffI") for _ in range(r.take("I"))]
    p["models"] = [_cmesh(r) for _ in range(r.take("I"))]
    p["sky"] = [_cmesh(r), _cmesh(r)]
    n = r.take("I")
    p["name"] = r.d[r.o:r.o + n].decode("latin1")
    r.o += n
    p["flag"] = r.take("B")
    if r.o != len(data):
        raise FormatError(f"FPVS v11 read to {r.o:#x} of {len(data):#x}")
    return p


# --- FM4 models -----------------------------------------------------------------------------

class _R:
    def __init__(self, d):
        self.d, self.o = d, 0

    def u(self):
        v = struct.unpack_from(">I", self.d, self.o)[0]
        self.o += 4
        return v

    def skip(self, n):
        self.o += n

    def s(self):
        self.o += 4 + struct.unpack_from(">I", self.d, self.o)[0]


class Template:
    """An FM4 track model of one sub-model and one mesh (RMB v5/v6), whose geometry is replaced."""

    def __init__(self, data, technique, stride):
        self.d, self.technique = data, technique
        r = _R(data)
        self.version = r.u()
        self.bounds_at = r.o
        r.skip(32 + 64)
        r.u()                                   # TBaseModel version
        r.u()
        if r.u() != 0:
            raise FormatError("template has LODs")
        r.u()
        if r.u() != 1:
            raise FormatError("template is not one sub-model")
        r.u()
        self.sub_bounds_at = r.o
        r.skip(48)
        r.u()
        r.s()
        r.u()
        self.vb_at = r.o
        self.vcount, self.stride = r.u(), r.u()
        if self.stride != stride:
            raise FormatError(f"template stride {self.stride}, expected {stride}")
        r.skip(self.vcount * self.stride)
        self.vb_end = r.o
        r.u()
        if r.u() != 1:
            raise FormatError("template is not one mesh")
        r.u()
        r.u()
        r.s()
        r.u()
        self.prim_at = r.o
        r.u()
        r.u()
        r.u()                                   # UnpackingData version
        self.uvos_at = r.o + 32
        self.uvos = struct.unpack_from(">4f", data, self.uvos_at)
        r.skip(48)
        r.u()
        self.icount, istride = r.u(), r.u()
        if istride != 2:
            raise FormatError("template indices are not 16-bit")
        r.skip(self.icount * 2)
        self.ib_end = r.o
        self.group = track_rmb.group(data)
        pattern = struct.pack(">4f", *self.uvos)
        for k, part in enumerate(self.group.parts):
            if part[1] and part[1].count(pattern) != 1:
                raise FormatError(f"slot {k}: UVOffsetScale not found once in the command buffer")

    def build(self, vertices, indices, bounds, uvos):
        """The model with these vertices (the template's stride), 16-bit triangle-list indices,
        bounds ((min xyz), (max xyz)) and `UVOffsetScale` (offset u, v, scale u, v)."""
        if len(vertices) % self.stride:
            raise FormatError("vertex data is not of the template's stride")
        lo, hi = bounds
        head = bytearray(self.d[:self.vb_at])
        struct.pack_into(">8f", head, self.bounds_at, *lo, 0.0, *hi, 0.0)
        centre = [(a + b) / 2 for a, b in zip(lo, hi)]
        struct.pack_into(">12f", head, self.sub_bounds_at, *centre, 0.0, *lo, 0.0, *hi, 0.0)
        mesh = bytearray(self.d[self.vb_end:self.ib_end - self.icount * 2 - 12])
        struct.pack_into(">I", mesh, self.prim_at - self.vb_end, 4)
        struct.pack_into(">4f", mesh, self.uvos_at - self.vb_end, *uvos)
        out = (bytes(head) + struct.pack(">II", len(vertices) // self.stride, self.stride) + vertices
               + bytes(mesh) + struct.pack(">III", 3, len(indices), 2)
               + np.asarray(indices, ">u2").tobytes() + self.d[self.ib_end:self.group.at])
        g = track_rmb.group(self.d)
        old, new = struct.pack(">4f", *self.uvos), struct.pack(">4f", *uvos)
        for part in g.parts:
            if part[1]:
                part[1] = patch_draws(part[1].replace(old, new), len(indices))
        return out + g.encode()


def patch_draws(physical, count, prim=4):
    """Every DRAW_INDX of a slot's physical part drawing `count` indices as primitive `prim`."""
    buf = bytearray(physical)
    o = 0
    while o + 4 <= len(buf):
        h = struct.unpack_from(">I", buf, o)[0]
        kind, n = h >> 30, ((h >> 16) & 0x3FFF) + 1
        if kind == 3 and (h >> 8) & 0x7F == DRAW_INDX:
            # [viz query, VGT_DRAW_INITIATOR (count << 16 | flags | primitive), index base, size]
            init = struct.unpack_from(">I", buf, o + 8)[0]
            struct.pack_into(">I", buf, o + 8, (count << 16) | (init & 0xFFC0) | prim)
            size = struct.unpack_from(">I", buf, o + 16)[0]
            struct.pack_into(">I", buf, o + 16, (size & 0xFF000000) | count)
            o += 4 + 4 * n
        elif kind in (0, 3):
            o += 4 + 4 * n
        else:
            o += 4
    return bytes(buf)


# The FM4 models each kind of FM2 draw is written from: (track, model, technique, stride). All
# read the diffuse texture at sampler 0; the lightmap ones the lightmap at sampler 7.
TEMPLATES = {
    "opaque": ("Indi", "indiout.00034.rmb.bin", "diff_1_nocube", 24),
    "two_sided": ("Catalunya", "Catalunyaout.01771.rmb.bin", "diff_spec_1_2sd_nocube", 24),
    "alpha_test": ("Alps", "alpsout.00065.rmb.bin", "diff_opac_2_2sd_nocube", 24),
    "unlit": ("LeMans", "LeMansout.00189.rmb.bin", "diff_nolm_vclr_1", 20),
    "unlit_alpha_test": ("Autopark", "autoparkout.01075.rmb.bin", "diff_opac_nolm_vclr_1", 20),
}
UNLIT_COLOUR = 0xFFB4B4B4     # the vertex colour of FM2 draws without a lightmap (RGBA)


def _find(folder, name):
    return next(p for p in folder.iterdir() if p.name.lower() == name.lower())


def load_templates(fm4_tracks):
    """{kind: Template} and {shader path in bin.zip: .fxobj bytes} from FM4 Disc 1's tracks."""
    templates, shaders = {}, {}
    for kind, (track, name, technique, stride) in TEMPLATES.items():
        z = zipfile.ZipFile(_find(_find(fm4_tracks, track), "bin.zip"))
        templates[kind] = Template(archive_read(z, name), technique, stride)
        member = next(n for n in z.namelist() if n.lower() == f"shaders/track/{technique}.fxobj")
        shaders[member] = archive_read(z, member)
    return templates, shaders


def kind_of(draw, lightmap):
    if lightmap is None:
        return "unlit_alpha_test" if draw.alpha_test else "unlit"
    if draw.alpha_test:
        return "alpha_test"
    return "two_sided" if draw.two_sided else "opaque"


def uv_words(uv):
    """(`16_16` words of uv in [0, 1] after the offset and scale, UVOffsetScale)."""
    lo, hi = uv.min(0), uv.max(0)
    span = np.where(hi - lo > 1e-9, hi - lo, 1.0)
    q = np.clip(np.round((uv - lo) / span * 65535), 0, 65535).astype(np.uint32)
    return (q[:, 0] << 16) | q[:, 1], (float(lo[0]), float(lo[1]), float(span[0]), float(span[1]))


def fm4_model(draw, templates, lightmap):
    """(kind, FM4 model bytes, bounds) of one FM2 draw; `lightmap` its lightmap's PVS list index."""
    kind = kind_of(draw, lightmap)
    t = templates[kind]
    pos = draw.positions.astype(">f4")
    words0, uvos = uv_words(draw.uv0)
    if t.stride == 24:
        lm = draw.uv1 if draw.uv1 is not None else draw.uv0
        q = np.clip(np.round(lm * 65535), 0, 65535).astype(np.uint32)
        v = np.zeros((len(pos), 6), ">u4")
        v[:, 3], v[:, 4], v[:, 5] = draw.normals, words0, (q[:, 0] << 16) | q[:, 1]
    else:
        v = np.zeros((len(pos), 5), ">u4")
        v[:, 3], v[:, 4] = words0, UNLIT_COLOUR
    v[:, 0:3] = pos.view(">u4")
    lo, hi = tuple(map(float, draw.positions.min(0))), tuple(map(float, draw.positions.max(0)))
    return kind, t.build(v.tobytes(), draw.indices, (lo, hi), uvos), (lo, hi)
