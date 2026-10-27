"""CPU-only, bounds-checked FM3/FM4 carbin audit.

Format reference: FMdangaina/ForzaEditor at 8807c7d137646dab8d9eecab7e8d5a6602ef58aa,
CarbinModel.cs and CarbinModelMotorsport3.cs. This separate reader checks the
external converter's output; structural success is not a rendering test.
SPDX-License-Identifier: GPL-3.0-only
"""
from collections import Counter
import hashlib
import math
import struct


class FormatError(ValueError):
    pass


class Reader:
    def __init__(self, data):
        self.data, self.offset = data, 0

    def take(self, size):
        if size < 0 or size > len(self.data)-self.offset:
            raise FormatError(f"Read outside carbin at {self.offset:#x} (+{size})")
        start = self.offset
        self.offset += size
        return self.data[start:self.offset]

    def u32(self):
        return struct.unpack(">I", self.take(4))[0]

    def count(self, limit=1_000_000):
        n = self.u32()
        if n > limit:
            raise FormatError(f"Unreasonable count {n} at {self.offset-4:#x}")
        return n

    def floats(self, n):
        values = struct.unpack(">"+str(n)+"f", self.take(4*n))
        if not all(math.isfinite(v) for v in values):
            raise FormatError("Nonfinite carbin float")
        return values

    def name(self, wide=False):
        size = self.count(256) if wide else self.take(1)[0]
        try:
            return self.take(size).decode("ascii")
        except UnicodeError as e:
            raise FormatError("Invalid carbin name") from e

    def buffer(self, strides):
        count, stride = self.count(), self.count(256)
        if count and stride not in strides:
            raise FormatError(f"Unsupported buffer stride {stride}")
        return {"count":count, "stride":stride, "data":self.take(count*stride)}


def u32(data, offset):
    if offset < 0 or offset+4 > len(data):
        raise FormatError("Truncated carbin header")
    return struct.unpack_from(">I", data, offset)[0]


def parse(data, family):
    """Read a complete known-family file, never guess after a parsing failure."""
    r = Reader(data)
    kind = u32(data,0)
    if family == "FM3":
        if kind not in (1,2):
            raise FormatError("Unsupported FM3 carbin type")
        fmt = 4 if u32(data,4)==13 else (0x104 if kind==1 else 0x18)
        if (u32(data,fmt),u32(data,fmt+4)) != (13,11):
            raise FormatError("FM3 format signature mismatch")
        records = u32(data,fmt+12)
        if records > 10000:
            raise FormatError("Header record count exceeds bound")
        header_size = fmt+16+records*140+0x1ac
    elif family == "FM4":
        if kind == 2:
            fmt = 0x154
            records = u32(data,0x160)
            if records > 10000:
                raise FormatError("Header record count exceeds bound")
            header_size = 0x4a8+records*140
        elif kind in (1,3):
            fmt = 4 if kind==1 else 0x48
            header_size = 0x358 if kind==1 else 0x39c
        else:
            raise FormatError("Unsupported FM4 carbin type")
        if (u32(data,fmt),u32(data,fmt+4)) != (16,16):
            raise FormatError("FM4 format signature mismatch")
    else:
        raise FormatError("Select FM3 or FM4 explicitly")
    header = r.take(header_size)
    lists = []
    for _ in range(r.count(16)*2):
        lists.append([r.u32() for _ in range(r.count(100000))])
    r.take(4)
    sections = []
    for _ in range(r.count(1024)):
        marker = r.u32()
        if marker not in (2,5):
            raise FormatError(f"Unknown section marker {marker}")
        bounds = r.floats(9)
        r.take(28)
        glass_vertices = r.take(r.count()*16)
        r.take(4)
        glass_indices = r.take(r.count()*2)
        if family=="FM4":
            r.take(4)
        r.take(8)
        name = r.name()
        r.take(4)
        strides = (16,40,44) if family=="FM3" else (32,)
        lod = r.buffer(strides)
        r.take(4)
        meshes = []
        for _ in range(r.count(4096)):
            r.take(9 if family=="FM3" else 5)
            uv = None if family=="FM3" else r.floats(8)
            if family=="FM4":
                r.take(36)
            material = r.name(True)
            level, primitive = r.u32(), r.u32()
            if level > 5 or primitive not in (4,6):
                raise FormatError("Unknown LOD or primitive type")
            r.take(56)
            index_version = r.u32()
            if index_version != 3:
                raise FormatError("Unsupported index buffer version")
            indices = r.buffer((2,4))
            r.take(4)
            meshes.append({"name":material, "lod":level, "primitive":primitive,
                           "uv":uv, "indices":indices})
        r.take(4)
        lod0 = r.buffer(strides)
        deformation, damage, damage0 = False, None, None
        if family=="FM4":
            post = r.take(9)
            deformation = bool(post[4])
            damage = r.buffer((4,16))
            r.take(4)
            damage0 = r.buffer((4,16))
        section = {"name":name,"bounds":bounds,"lod":lod,"lod0":lod0,"meshes":meshes,
                   "glass_vertices":glass_vertices,"glass_indices":glass_indices,
                   "deformation":deformation,"damage":damage,"damage0":damage0}
        for mesh in meshes:
            pool = lod0 if mesh["lod"]==0 else lod
            outside = [i for i in index_values(mesh) if i >= pool["count"]]
            if outside:
                raise FormatError(f"Index outside pool: {name}/{mesh['name']}, "
                                  f"LOD={mesh['lod']}, primitive={mesh['primitive']}, "
                                  f"count={pool['count']}, stride={mesh['indices']['stride']}, "
                                  f"invalid={outside[:8]}")
        sections.append(section)
    trailer = r.take(len(data)-r.offset)
    if len(trailer) != 24:
        raise FormatError(f"Unconsumed data / unexpected trailer: {len(trailer)} bytes")
    expected = Counter((s<<16)|m for s,sec in enumerate(sections) for m in range(len(sec["meshes"])))
    if Counter(i for values in lists for i in values) != expected:
        raise FormatError("Draw lists do not cover each mesh exactly once")
    return {"family":family,"type":kind,"header":header,"lists":lists,
            "sections":sections,"trailer":trailer}


def index_values(mesh):
    b = mesh["indices"]
    sentinel = (1 << (8*b["stride"]))-1
    code = ">H" if b["stride"]==2 else ">I"
    for (value,) in struct.iter_unpack(code,b["data"]):
        # Xenos' 32-bit index buffers also use the 24-bit restart token.
        if mesh["primitive"]==6 and value in (sentinel,0x00ffffff):
            continue
        yield value


def positions(section, pool, family):
    b = section["bounds"]
    center = [b[j]+(b[j+3]+b[j+6])/2 for j in range(3)]
    scale = math.sqrt(sum(((b[j+6]-b[j+3])/2)**2 for j in range(3)))
    result = []
    for i in range(pool["count"]):
        o = i*pool["stride"]
        if family=="FM3":
            x,y,z,w = struct.unpack_from(">4e",pool["data"],o)
        else:
            x,y,z,w = (v/32767 for v in struct.unpack_from(">4h",pool["data"],o))
            w *= scale
        p = tuple(center[j]+v*w for j,v in enumerate((x,y,z)))
        if not all(math.isfinite(v) for v in p):
            raise FormatError("Nonfinite vertex position")
        result.append(p)
    return result


def unit(vector):
    length = math.sqrt(sum(v*v for v in vector))
    if not math.isfinite(length) or length < 1e-12:
        raise FormatError("Degenerate/nonfinite vector")
    return tuple(v/length for v in vector)


def packed111110(data, offset):
    packed = u32(data, offset)
    vals = []
    for shift,bits in ((0,11),(11,11),(22,10)):
        v = (packed>>shift)&((1<<bits)-1)
        if v & (1<<(bits-1)):
            v -= 1<<bits
        vals.append(v/((1<<(bits-1))-1))
    return vals


def normal3(pool, i):
    o = i*pool["stride"]+(16 if pool["stride"]==40 else 12)
    return unit(packed111110(pool["data"], o))


def normal4(pool, i):
    x,y,z,w = unit(struct.unpack_from(">4h",pool["data"],i*32+16))
    return (1-2*(y*y+z*z), 2*(x*y+z*w), 2*(x*z-y*w))


def tangent_axis3(pool, i, normal):
    # FM3 40-byte vertices store the frame's Z axis. Project its quantized
    # components onto the normal plane before comparing the FM4 rotation.
    axis = packed111110(pool["data"], i*40+36)
    dot = sum(x*y for x,y in zip(normal, axis))
    return unit([x-dot*y for x,y in zip(axis, normal)])


def tangent_axis4(pool, i):
    x,y,z,w = unit(struct.unpack_from(">4h",pool["data"],i*32+16))
    return (2*(x*z+y*w), 2*(y*z-x*w), 1-2*(x*x+y*y))


def audit_header(source, target):
    """Preserve the opaque records, driver rig and four legacy gauge frames.

    The source/target header offsets differ by family. Do not validate driver
    preservation by comparing vertices alone: a damaged pivot can leave every
    vertex unchanged while moving the animated steering wheel.
    """
    a, b = source["header"], target["header"]
    source_fmt = 4 if u32(a, 4) == 13 else (0x104 if source["type"] == 1 else 0x18)
    target_fmt = 4 if target["type"] == 1 else (0x154 if target["type"] == 2 else 0x48)
    expected_type = 1 if source_fmt == 4 else (3 if source["type"] == 2 else 2)
    if target["type"] != expected_type:
        raise FormatError("Converted model kind changed")
    records = u32(a, source_fmt+12)
    if records != u32(b, target_fmt+12):
        raise FormatError("Model header record count changed")
    # The shared area ends after the fourth legacy gauge frame. The extra
    # eleven FM4 frames follow it, before two scalar end values.
    length = 8+records*140+0x19c
    if a[source_fmt+8:source_fmt+8+length] != b[target_fmt+8:target_fmt+8+length]:
        raise FormatError("Header records, driver rig, or legacy gauge frames changed")
    start = target_fmt+16+records*140+0x19c
    neutral = struct.pack(">9f", 0, 0, 0, 0, 0, 1, 0, 0, 1)
    if b[start:start+11*36] != neutral*11:
        raise FormatError("New FM4 gauge frames are not neutral")
    return {"shared_header_records_preserved": records, "driver_rig_preserved": True,
            "legacy_gauge_frames_preserved": 4, "new_gauge_frames_neutral": 11}


def audit_conversion(source, target, position_tolerance=0.001):
    """Validate each vertex and mesh against its source, without rendering."""
    a,b = parse(source,"FM3"),parse(target,"FM4")
    header = audit_header(a, b)
    if len(a["sections"])!=len(b["sections"]) or a["lists"]!=b["lists"] or a["trailer"]!=b["trailer"]:
        raise FormatError("Sections, draw lists, or trailer changed")
    maxima = {"position_error_m":0.0,"normal_error_degrees":0.0,
              "tangent_axis_error_degrees":0.0,"uv_error":0.0}
    vertices, meshes, damage_words, uv_checks, tangent_checks = 0,0,0,0,0
    for s,t in zip(a["sections"],b["sections"]):
        if s["name"]!=t["name"] or len(s["meshes"])!=len(t["meshes"]):
            raise FormatError("Section identity or mesh count changed")
        if any(s[k]!=t[k] for k in ("glass_vertices","glass_indices")):
            raise FormatError("Glass particle data changed")
        for key,damagekey in (("lod","damage"),("lod0","damage0")):
            p,q = s[key],t[key]
            if p["count"]!=q["count"]:
                raise FormatError("Vertex count changed")
            pa,pb = positions(s,p,"FM3"),positions(t,q,"FM4")
            for i,(x,y) in enumerate(zip(pa,pb)):
                error = math.dist(x,y)
                maxima["position_error_m"] = max(maxima["position_error_m"],error)
                if error > position_tolerance:
                    raise FormatError(f"{s['name']}/{key}/{i}: position drift {error:.6g} m")
                na,nb = normal3(p,i),normal4(q,i)
                angle = math.degrees(math.acos(max(-1,min(1,sum(x*y for x,y in zip(na,nb))))))
                maxima["normal_error_degrees"] = max(maxima["normal_error_degrees"],angle)
                if angle > 0.02:
                    raise FormatError(f"{s['name']}/{key}/{i}: normal drift {angle} degrees")
                if p["stride"] == 40:
                    ta,tb = tangent_axis3(p,i,na),tangent_axis4(q,i)
                    tangent_angle = math.degrees(math.acos(max(-1,min(1,sum(x*y for x,y in zip(ta,tb))))))
                    maxima["tangent_axis_error_degrees"] = max(maxima["tangent_axis_error_degrees"],tangent_angle)
                    if tangent_angle > 0.02:
                        raise FormatError(f"{s['name']}/{key}/{i}: tangent frame drift {tangent_angle} degrees")
                    tangent_checks += 1
                if p["stride"] in (40,44):
                    start = i*p["stride"]+(20 if p["stride"]==40 else 16)
                    if p["data"][start:start+8] != q["data"][i*32+24:i*32+32]:
                        raise FormatError("Extra vertex channels changed")
                vertices += 1
            if p["stride"]==40 and p["count"]:
                words = b"".join(p["data"][i*p["stride"]+28:i*p["stride"]+32] for i in range(p["count"]))
                if t[damagekey]["count"]:
                    if t[damagekey]["data"]!=words or t[damagekey]["stride"]!=4:
                        raise FormatError("Deformation words changed")
                    damage_words += p["count"]
                elif words != b"\0\0\3\xff"*p["count"]:
                    raise FormatError("Nontrivial source deformation was dropped")
        for m,n in zip(s["meshes"],t["meshes"]):
            if any(m[k]!=n[k] for k in ("name","lod","primitive","indices")):
                raise FormatError("Mesh name, topology or LOD changed")
            key = "lod0" if m["lod"]==0 else "lod"
            p,q = s[key],t[key]
            channels = 4 if p["stride"]==40 else 2
            for i in set(index_values(m)):
                uv3 = struct.unpack_from(">"+str(channels)+"e",p["data"],i*p["stride"]+8)
                uv4 = struct.unpack_from(">"+str(channels)+"H",q["data"],i*32+8)
                for channel,(v,raw) in enumerate(zip(uv3,uv4)):
                    offset,scale = n["uv"][2*channel:2*channel+2]
                    actual = offset+scale*raw/65535
                    error = abs(v-actual)
                    maxima["uv_error"] = max(maxima["uv_error"],error)
                    if not math.isfinite(error) or error > abs(scale)/65535+2e-6:
                        raise FormatError("UV drift exceeds quantization bound")
                    uv_checks += 1
            meshes += 1
    return {"passed":True,"vertices":vertices,"meshes":meshes,"sections":len(a["sections"]),
            "header":header,
            "damage_words":damage_words,"uv_checks":uv_checks,
            "stored_tangent_axes_checked":tangent_checks,**maxima,
            "position_tolerance_m":position_tolerance,
            "source_sha256":hashlib.sha256(source).hexdigest(),
            "target_sha256":hashlib.sha256(target).hexdigest(),
            "runtime_tested":False,
            "limits":["No material/render validation", "No wheel morph or driver animation proof",
                      "No source tangent axis in 16/44-byte vertices; their reconstructed frames need rendering review"]}
