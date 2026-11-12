"""Where an FM2 track draw's textures read their coordinates, from its own Xenos shaders.

FM2's track shaders (Maya `place2dTexture` networks compiled for Xenos) do not read every
texture at the vertex coordinates as stored: the vertex shader fetches the coordinate words
as raw integers and passes them on scaled by a literal (`1/32767` for the lightmap and the
masks) or through a `c_place2d_N_Mtx` matrix the draw program loads (op `0x5`; the colour
maps' tiling, 1 to 8,192 a unit), and the pixel shader samples each texture at one of those
interpolators, the lightmap after its atlas transform (`c_uvAtlas`). Which vertex word feeds
which sampler differs by shader. This module follows the two shaders of a draw by evaluating
their microcode as affine functions of the vertex words, and returns per sampler the vertex
word and the affine map from its two raw integer halves to the texture coordinates; for a
sampler read after a constant the program does not set (the lightmap's atlas), the map up to
that constant.

Formats (big-endian, microcode layout as Xenia's `ucode.h`): a shader in the render graph is
a header `102A11xx` (+4 header size, +8 microcode size, +0x18 offset of the code descriptor
(code offset, code size) in the microcode, +0x28 the length of its PDB path, then the path,
whose `xxxxxxxx-xxxxxxxx.updb` GUID ends the microcode in the model's `.gpu` chunk). Before
the code, the microcode holds its literal constants (float4s, the last at `c255`). The code
starts with control flow (two 48-bit instructions per 96 bits); `exec` clauses run fetch and
ALU instructions of 96 bits. Op `0x2e` of the draw program sets a shader (+8 type: 1 pixel,
0 vertex, not always set: the header tells); +16 the end of its header in the graph).
"""
import re
import struct

import numpy as np

VERTEX_FETCH, TEXTURE_FETCH = 0, 1
EXEC_OPS = {1, 2, 3, 4, 5, 6, 13, 14}      # exec, exec_end, cond_exec(_end), cond_exec_pred(...)
END_OPS = {2, 4, 6, 14}
ADD, MUL, MAX, MIN, MAD, DP4, DP3, DP2ADD = 0, 1, 2, 3, 11, 15, 16, 17
CND = {12, 13, 14}                          # cndeq, cndge, cndgt
KILL_VECTOR, KILL_SCALAR = {24, 25, 26, 27}, {35, 36, 37, 38, 39}
RETAIN_PREV = 50
# Vertex formats: components and whether they are integers read as stored.
FORMATS = {25: 2, 26: 4, 57: 3, 38: 4, 37: 2, 36: 1}
FLOATS = {57, 38, 37, 36}


class ShaderError(ValueError):
    pass


# --- affine values ---------------------------------------------------------------------------
# A value is {symbol: coefficient} with the key 1 for the constant term; symbols are
# (word, component, signed) of the vertex (a `16_16` word's x its high 16 bits: FM2's vertex
# fetch constants swap within 16 bits), or None when it is not affine in them.
# `Value` pairs that with its base: the affine part before an unknown constant scaled it.

class Value:
    __slots__ = ("affine", "base")

    def __init__(self, affine, base=None):
        self.affine = affine
        self.base = base if base is not None else affine


def const(x):
    return Value({1: float(x)})


UNKNOWN = Value(None, None)


def _scale(a, k):
    return {s: c * k for s, c in a.items()}


def _sum(*terms):
    out = {}
    for t in terms:
        for s, c in t.items():
            out[s] = out.get(s, 0.0) + c
    return {s: c for s, c in out.items() if c != 0.0 or s == 1}


def _constant(a):
    return a is not None and set(a) <= {1}


def _carrier(v):
    """The vertex-dependent part a value carries: its affine map, or its base once unknown."""
    if v.affine is not None:
        return None if _constant(v.affine) else v.affine
    return v.base


def _unknown(a, b):
    # Scaled or offset by a constant the program does not set: the base is the one side that
    # depends on the vertex.
    ca, cb = _carrier(a), _carrier(b)
    return Value(None, ca if cb is None else cb if ca is None else None)


def mul(a, b):
    if a.affine is not None and b.affine is not None:
        if _constant(a.affine):
            return Value(_scale(b.affine, a.affine.get(1, 0.0)))
        if _constant(b.affine):
            return Value(_scale(a.affine, b.affine.get(1, 0.0)))
        return UNKNOWN
    return _unknown(a, b)


def add(a, b):
    if a.affine is not None and b.affine is not None:
        return Value(_sum(a.affine, b.affine))
    return _unknown(a, b)


def _same(a, b):
    return a is b or (a.affine == b.affine and a.base == b.base and (a.affine is not None or a.base is not None))


def negate(a):
    return Value(None if a.affine is None else _scale(a.affine, -1.0),
                 None if a.base is None else _scale(a.base, -1.0))


# --- microcode -----------------------------------------------------------------------------

class Shader:
    """One shader of a render graph: its literal constants and its instructions in order."""

    def __init__(self, kind, literals, instructions):
        self.kind, self.literals, self.instructions = kind, literals, instructions
        self.vertex = bool(kind & 1)        # header `102A1100` a pixel shader, `..01`/`..41` vertex
        # A pixel shader that discards pixels (kill*): FM2's alpha test, done in the shader.
        self.kills = any(not f and ((d2 >> 24) & 31 in KILL_VECTOR or (d0 >> 26) & 63 in KILL_SCALAR)
                         for f, (d0, d1, d2) in instructions)


def graph_shaders(model):
    """{graph offset of a header's end: Shader} of an FM2 model (track_models.Model)."""
    g = model.graph
    gpu = [body for s, c, body in model.chunks if s == ".gpu"]
    out = {}
    for m in re.finditer(rb"\x10\x2a\x11[\x00-\xff]", g):
        h = m.start()
        if h % 4 or h + 0x2c > len(g):
            continue
        magic, header, size = struct.unpack_from(">3I", g, h)
        desc = struct.unpack_from(">I", g, h + 0x18)[0]
        path_len = struct.unpack_from(">I", g, h + 0x28)[0]
        if not 0x2c <= header < 0x10000 or not 0 < size < 0x100000 or desc >= header or path_len > 0x200:
            continue
        path = g[h + 0x2c:h + 0x2c + path_len]
        guid = re.findall(rb"([0-9a-f]{8})-([0-9a-f]{8})\.updb", path)
        if not guid:
            continue
        key = bytes.fromhex(guid[-1][0].decode()) + bytes.fromhex(guid[-1][1].decode())
        blob = None
        for body in gpu:
            at = body.find(key)
            if at >= 0 and at + 8 >= size:
                blob = body[at + 8 - size:at + 8]
                break
        if blob is None:
            continue
        code_off, code_size = struct.unpack_from(">II", g, h + desc)
        if code_off % 16 or code_off + code_size > size:
            continue
        n = code_off // 16
        literals = {256 - n + i: struct.unpack_from(">4f", blob, 16 * i) for i in range(n)}
        try:
            instructions = _instructions(blob[code_off:code_off + code_size])
        except ShaderError:
            continue
        out[h + header] = Shader(magic & 0xFF, literals, instructions)
    return out


def _instructions(code):
    """[(is_fetch, dwords)] in the order the control flow's exec clauses run them."""
    words = struct.unpack(f">{len(code) // 4}I", code[:len(code) // 4 * 4])
    out, i, done = [], 0, False
    while not done and 3 * i + 2 < len(words):
        a, b, c = words[3 * i:3 * i + 3]
        for d0, d1 in ((a, b & 0xFFFF), ((b >> 16) | (c << 16) & 0xFFFFFFFF, c >> 16)):
            op = (d1 >> 12) & 15
            if op in EXEC_OPS:
                address, count, sequence = d0 & 0xFFF, (d0 >> 12) & 7, (d0 >> 16) & 0xFFF
                for k in range(count):
                    at = 3 * (address + k)
                    if at + 3 > len(words):
                        raise ShaderError("exec past the code")
                    out.append(((sequence >> (2 * k)) & 1 == 1, words[at:at + 3]))
                if op in END_OPS:
                    done = True
                    break
        i += 1
    if not done:
        raise ShaderError("no exec_end")
    return out


def _swizzle(s, i):
    return ((s >> (2 * i)) + i) & 3


class _Machine:
    def __init__(self, constants):
        self.r = {}
        self.constants = constants         # {register: (x, y, z, w)} known
        self.exports = {}

    def reg(self, n):
        return self.r.setdefault(n, [UNKNOWN] * 4)

    def operand(self, reg, is_temp, swz, neg):
        if is_temp:
            src = self.reg(reg & 63)
            vals = [src[_swizzle(swz, i)] for i in range(4)]
        else:
            c = self.constants.get(reg)
            vals = [const(c[_swizzle(swz, i)]) if c is not None else UNKNOWN for i in range(4)]
        return [negate(v) for v in vals] if neg else vals

    def alu(self, d0, d1, d2):
        opc = (d2 >> 24) & 31
        srcs = [self.operand((d2 >> 16) & 255, (d2 >> 31) & 1, (d1 >> 16) & 255, (d1 >> 26) & 1),
                self.operand((d2 >> 8) & 255, (d2 >> 30) & 1, (d1 >> 8) & 255, (d1 >> 25) & 1),
                self.operand(d2 & 255, (d2 >> 29) & 1, d1 & 255, (d1 >> 24) & 1)]
        a, b, c = srcs
        if opc == ADD:
            res = [add(a[i], b[i]) for i in range(4)]
        elif opc == MUL:
            res = [mul(a[i], b[i]) for i in range(4)]
        elif opc == MAD:
            res = [add(mul(a[i], b[i]), c[i]) for i in range(4)]
        elif opc in (MAX, MIN) and (d2 >> 16) & 255 == (d2 >> 8) & 255 and (d2 >> 31) & 1 == (d2 >> 30) & 1 \
                and (d1 >> 16) & 255 == (d1 >> 8) & 255 and (d1 >> 26) & 1 == (d1 >> 25) & 1:
            res = a                                     # max(x, x): a move
        elif opc in CND:
            # A select: known when both choices are the same value (the lightmap's atlas tests
            # the sign of its unknown scale and picks equal swizzles either way).
            res = [b[i] if _same(b[i], c[i]) else UNKNOWN for i in range(4)]
        elif opc in (DP4, DP3, DP2ADD):
            n = {DP4: 4, DP3: 3, DP2ADD: 2}[opc]
            t = mul(a[0], b[0])
            for i in range(1, n):
                t = add(t, mul(a[i], b[i]))
            if opc == DP2ADD:
                t = add(t, c[0])
            res = [t] * 4
        else:
            res = [UNKNOWN] * 4
        dest, mask = d0 & 63, (d0 >> 16) & 15
        export = (d0 >> 15) & 1
        target = self.exports.setdefault(dest, [UNKNOWN] * 4) if export else self.reg(dest)
        for i in range(4):
            if mask >> i & 1:
                target[i] = res[i]
        scalar_op, scalar_mask = (d0 >> 26) & 63, (d0 >> 20) & 15
        if scalar_mask and scalar_op != RETAIN_PREV:
            starget = target if export else self.reg((d0 >> 8) & 63)
            for i in range(4):
                if scalar_mask >> i & 1:
                    starget[i] = UNKNOWN


def vertex_outputs(shader, constants):
    """{interpolator: [Value x4]} of a vertex shader with `constants` set."""
    m = _Machine({**shader.literals, **constants})
    for is_fetch, (d0, d1, d2) in shader.instructions:
        if is_fetch:
            if d0 & 31 != VERTEX_FETCH:
                continue
            dst, fmt = (d0 >> 12) & 63, (d1 >> 16) & 63
            offset = (d2 >> 8) & 0x7FFFFF
            normalized, signed = not (d1 >> 13) & 1, (d1 >> 12) & 1
            exp = (d1 >> 24) & 63
            exp = exp - 64 if exp >= 32 else exp
            comps = FORMATS.get(fmt)
            fetched = []
            for k in range(4):
                if comps is None:
                    fetched.append(UNKNOWN)
                elif k >= comps:
                    fetched.append(const(1.0 if k == 3 else 0.0))
                elif fmt in FLOATS:
                    fetched.append(UNKNOWN)
                else:
                    word, half = (offset + k // 2, k % 2) if fmt in (25, 26) else (offset, k)
                    scale = 2.0 ** exp
                    if normalized:
                        scale /= 32767.0 if signed else 65535.0
                    fetched.append(Value({(word, half, bool(signed)): scale}))
            reg = m.reg(dst)
            for k in range(4):
                sel = (d1 >> (3 * k)) & 7
                if sel < 4:
                    reg[k] = fetched[sel]
                elif sel in (4, 5):
                    reg[k] = const(sel - 4)
        else:
            m.alu(d0, d1, d2)
    return m.exports


def sampler_coordinates(shader, interpolators):
    """{sampler: (u Value, v Value)} of a pixel shader whose inputs are `interpolators`."""
    m = _Machine(shader.literals)
    for i, vals in interpolators.items():
        if i < 16:
            m.r[i] = list(vals)
    out = {}
    for is_fetch, (d0, d1, d2) in shader.instructions:
        if is_fetch:
            if d0 & 31 != TEXTURE_FETCH:
                continue
            # Texture fetch source swizzles are absolute, two bits a component.
            sampler, src, swz = (d0 >> 20) & 31, (d0 >> 5) & 63, (d0 >> 26) & 63
            reg = m.reg(src)
            out.setdefault(sampler, (reg[swz & 3], reg[(swz >> 2) & 3]))
            dest = m.reg((d0 >> 12) & 63)
            for k in range(4):
                if (d1 >> (3 * k)) & 7 != 7:        # 7: the component is kept
                    dest[k] = UNKNOWN
        else:
            m.alu(d0, d1, d2)
    return out


def choose(candidates, constants, samplers):
    """({sampler: (u, v)}, pixel shader) of the vertex and pixel shader pair among `candidates`
    that reads the most of the bound `samplers` at coordinates it can follow (then the longest
    pixel shader, the full material rather than a simpler pass), or None."""
    best = None
    for vs in (c for c in candidates if c.vertex):
        outputs = vertex_outputs(vs, constants)
        for ps in (c for c in candidates if not c.vertex):
            coords = sampler_coordinates(ps, outputs)
            known = sum(1 for s, (u, v) in coords.items() if s in samplers
                        and (u.affine is not None or u.base is not None))
            score = (known, len(ps.instructions))
            if best is None or score > best[0]:
                best = (score, (coords, ps))
    return best[1] if best is not None else None


def evaluate(value, words, use_base=False):
    """(n,) float coordinates of an affine `value` over raw vertex `words` (n, stride/4) u32,
    or None."""
    a = value.base if use_base else value.affine
    if a is None:
        return None
    out = np.full(len(words), a.get(1, 0.0))
    for s, c in a.items():
        if s == 1:
            continue
        word, half, signed = s
        if word >= words.shape[1]:
            return None
        w = words[:, word].astype(np.uint32)
        raw = ((w >> 16) if half == 0 else (w & 0xFFFF)).astype(np.uint16)
        if signed:
            raw = raw.view(np.int16)
        out = out + c * raw.astype(np.float64)
    return out
