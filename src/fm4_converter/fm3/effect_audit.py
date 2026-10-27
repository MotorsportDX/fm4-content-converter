"""Read Xbox D3DX effect technique/constant metadata without executing shaders.

Format reference: ForzaEditor ShaderTextures.cs, revision
8807c7d137646dab8d9eecab7e8d5a6602ef58aa. This bounded reader retains pass
provenance and all samplers, including resources provided by the engine.
SPDX-License-Identifier: GPL-3.0-only
"""
import struct


class EffectError(ValueError):
    pass


class Reader:
    def __init__(self, data):
        self.data = data

    def number(self, offset, fmt=">I"):
        size = struct.calcsize(fmt)
        if offset < 0 or offset + size > len(self.data):
            raise EffectError("Effect reference outside file")
        return struct.unpack_from(fmt, self.data, offset)[0]

    def string(self, offset, maximum=256):
        if not 0 <= offset < len(self.data):
            raise EffectError("Effect string outside file")
        end = self.data.find(b"\0", offset, offset + maximum + 1)
        if end < 0 or end == offset:
            raise EffectError("Missing or unterminated effect name")
        raw = self.data[offset:end]
        if any(b < 33 or b > 126 for b in raw):
            raise EffectError("Invalid effect name")
        return raw.decode("ascii")


def read_effect(data):
    """Return named techniques with their actual pass shader constant tables."""
    r = Reader(data)
    markers = [o for o in range(16, min(0x4000, len(data)-3), 4)
               if r.number(o) == 0xA3D70141]
    if len(markers) != 1:
        raise EffectError("Expected one Xbox effect metadata marker")
    marker = markers[0]
    names, blocks = marker + 12, marker + 28
    shaders = {"vertex": [], "pixel": []}
    for at in range(0, len(data)-40, 4):
        magic = r.number(at)
        if magic not in (0x102A1100, 0x102A1101):
            continue
        table = at + r.number(at+16) + 4
        if table+28 > len(data) or r.number(table+8) >> 16 < 0xFFFE:
            continue
        count = r.number(table+12)
        info = table + r.number(table+16)
        if count > 4096 or info+count*20 > len(data):
            raise EffectError("Invalid shader constant table")
        constants = []
        for i in range(count):
            entry = info + i*20
            name = r.string(table+r.number(entry))
            register_set = r.number(entry+4, ">H")
            constants.append({
                "name": name, "register_set": register_set,
                "register": r.number(entry+6, ">H"),
                "register_count": r.number(entry+8, ">H"),
                "sampler": (register_set & 3) == 3,
            })
        kind = "vertex" if magic == 0x102A1101 else "pixel"
        shaders[kind].append({"offset": at, "constants": constants})
    if not shaders["vertex"] or not shaders["pixel"]:
        raise EffectError("Effect has no recognized shader tables")
    stop = min(s["offset"] for kind in shaders.values() for s in kind)

    def name_at(reference):
        at = reference+names
        if at <= 0 or at >= len(data) or data[at-1] != 0:
            return None
        try:
            return r.string(at, 64)
        except EffectError:
            return None

    def shader_at(kind, reference):
        address = reference+blocks
        return next((s for s in shaders[kind] if s["offset"] <= address < s["offset"]+16), None)

    def pass_at(reference):
        start = reference+blocks
        if not reference or start < 0 or start+0x108 > len(data):
            return None
        for at in range(start, start+0x100, 4):
            if r.number(at) != 0xFFFFFFFF:
                continue
            vertex = shader_at("vertex", r.number(at+4))
            pixel = shader_at("pixel", r.number(at+8))
            if vertex is not None or pixel is not None:
                return {"block_offset": start, "vertex": vertex, "pixel": pixel}
        return None

    techniques = {}
    at = marker
    while at+20 <= stop:
        name = name_at(r.number(at))
        count = r.number(at+4)
        first = r.number(at+16)+names
        if not name or not 1 <= count <= 8 or not marker <= first <= stop-count*20:
            at += 4
            continue
        passes = []
        for i in range(count):
            entry = first+i*20
            pass_name = name_at(r.number(entry))
            block = pass_at(r.number(entry+8)) if r.number(entry+4) == 0 else None
            if pass_name is None or block is None:
                break
            passes.append({"name": pass_name, **block})
        if len(passes) != count:
            at += 4
            continue
        if name in techniques:
            raise EffectError("Duplicate technique record")
        constants = {v["name"] for p in passes for kind in ("vertex", "pixel")
                     if p[kind] for v in p[kind]["constants"]}
        samplers = {v["name"] for p in passes for kind in ("vertex", "pixel")
                    if p[kind] for v in p[kind]["constants"] if v["sampler"]}
        techniques[name] = {
            "record_offset": at, "passes": passes,
            "constants": sorted(constants), "samplers": sorted(samplers),
        }
        at += 20
    if not techniques:
        raise EffectError("Effect has no recognized techniques")
    return techniques
