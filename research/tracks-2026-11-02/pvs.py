"""Pembaca berkas track `FPVS` (Ribbon_NN/<t>_NN.pvs), mengikuti urutan baca FM4.

Urutan diambil dari parser FM4 `CTrackPresentation::helper_8288EAE8` dan helper-nya
(`82884198` header, `82883E38` record sel, `8288A500` objek, `82889FE0` array u16).
Stream `IOSys::CBinaryStream` big-endian: slot 160/124/136 = 4 byte, 164 = u16,
128/152/168 = 1 byte, 104 = vektor 4 float, 108 = matriks 16 float, 116 = string
(u32 panjang + byte). Versi global dibaca di header; cabang versi dari kode yang sama.

    python research/tracks-2026-11-02/pvs.py <berkas.pvs>...   # parse sampai EOF
"""
import struct, sys


class Reader:
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

    def u16list(self):
        return self.many(self.take("I"), "H")

    def u32list(self):
        return self.many(self.take("I"), "I")

    def string(self):
        n = self.take("I")
        s = self.d[self.o:self.o+n]
        self.o += n
        return s.decode("latin1")


def cell(r, ver):
    """82883E38: one 80-byte record (the +36 and +68 lists)."""
    c = {"u0": r.take("H")}
    if ver < 22:
        raise ValueError("PVS < 22 not handled")
    c["u4"], c["u8"], c["u12"] = r.take("I"), r.take("I"), r.take("I")
    c["v16"] = (r.take("f"),) if ver < 25 else r.take("4f")
    if ver >= 21:
        c["u32"] = r.take("H")
    c["u34_38"] = r.take("3H")
    c["f40"] = r.take("3f")
    c["u52"] = r.take("9H")
    return c


def obj(r):
    """8288A500: one 112-byte object (the +52 list)."""
    return {"refs": r.u32list(), "ids": r.u32list(), "mat": r.take("16f"), "vec": r.take("4f")}


def parse(data):
    r = Reader(data)
    p = {}
    magic, ver, w2 = r.take("4sII")
    if magic != b"FPVS":
        raise ValueError("not FPVS")
    p["ver"], p["w2"] = ver, w2
    p["w3"] = r.take("I") if ver >= 27 else None
    p["h0"], p["h2"] = r.take("H"), r.take("H")
    p["l4"] = [(r.u16list(), r.u16list(), r.u32list(), r.many(r.take("I"), "B"))
               for _ in range(r.take("I"))]
    p["l20"] = [r.take("IIffffI") for _ in range(r.take("I"))]
    p["l172"] = [r.string() for _ in range(r.take("I"))]
    p["l36"] = [cell(r, ver) for _ in range(r.take("I"))]
    p["l52"] = [obj(r) for _ in range(r.take("I"))]
    if ver >= 26:
        p["a84"], p["a100"], p["a116"] = r.u16list(), r.u16list(), r.u16list()
    else:
        p["legacy_cell"], p["legacy_obj"] = cell(r, ver), obj(r)
    p["l68"] = [cell(r, ver) for _ in range(r.take("I"))]
    p["s132"] = r.string()
    p["b160"], p["b196"] = r.take("B"), r.take("B")
    if ver >= 21:
        p["l200"] = [r.string() for _ in range(r.take("I"))]
    if ver >= 23:
        p["l192"] = [r.u16list() for _ in range(r.take("I"))]
    p["end"], p["size"] = r.o, len(data)
    return p


class Writer:
    def __init__(self):
        self.b = bytearray()

    def put(self, fmt, *v):
        self.b += struct.pack(">" + fmt, *v)

    def many(self, kind, items):
        self.put("I", len(items))
        self.b += struct.pack(f">{len(items)}{kind}", *items)

    def string(self, s):
        raw = s.encode("latin1")
        self.put("I", len(raw))
        self.b += raw


def write_cell(w, c, ver):
    w.put("HIII", c["u0"], c["u4"], c["u8"], c["u12"])
    if ver < 25:
        w.put("f", c["v16"][0])
    else:
        w.put("4f", *c["v16"])
    w.put("H", c["u32"])
    w.put("3H", *c["u34_38"])
    w.put("3f", *c["f40"])
    w.put("9H", *c["u52"])


def write_obj(w, o):
    w.many("I", o["refs"])
    w.many("I", o["ids"])
    w.put("16f", *o["mat"])
    w.put("4f", *o["vec"])


def write(p):
    ver = p["ver"]
    w = Writer()
    w.put("4sII", b"FPVS", ver, p["w2"])
    if ver >= 27:
        w.put("I", p["w3"])
    w.put("HH", p["h0"], p["h2"])
    w.put("I", len(p["l4"]))
    for a, b, c, d in p["l4"]:
        w.many("H", a); w.many("H", b); w.many("I", c); w.many("B", d)
    w.put("I", len(p["l20"]))
    for t in p["l20"]:
        w.put("IIffffI", *t)
    w.put("I", len(p["l172"]))
    for s in p["l172"]:
        w.string(s)
    w.put("I", len(p["l36"]))
    for c in p["l36"]:
        write_cell(w, c, ver)
    w.put("I", len(p["l52"]))
    for o in p["l52"]:
        write_obj(w, o)
    if ver >= 26:
        w.many("H", p["a84"]); w.many("H", p["a100"]); w.many("H", p["a116"])
    else:
        write_cell(w, p["legacy_cell"], ver); write_obj(w, p["legacy_obj"])
    w.put("I", len(p["l68"]))
    for c in p["l68"]:
        write_cell(w, c, ver)
    w.string(p["s132"])
    w.put("BB", p["b160"], p["b196"])
    if ver >= 21:
        w.put("I", len(p["l200"]))
        for s in p["l200"]:
            w.string(s)
    if ver >= 23:
        w.put("I", len(p["l192"]))
        for a in p["l192"]:
            w.many("H", a)
    return bytes(w.b)


SPECIAL_CELL_FLAGS = 0x50000204  # FM4 special ("always visible") cells: AmalfiGP, Tsukuba
NONE = 0xFFFF


def to_v27(p, w3):
    """v24 -> v27. Cell vectors become (f, 0, 0, 0) (FM4's v<25 path fills with the constant
    at 0x82000F40 = 0.0); the legacy extra cell/object are appended and indexed by the three
    v26 arrays the way FM4's own v27 tracks hold their special cell (Tsukuba: a84 [65535, c],
    a100 [65535, o], a116 [o], cell.u0 = o, cell.u4 = 0x50000204)."""
    if p["ver"] != 24:
        raise ValueError("expected FPVS v24")
    q = dict(p)
    q["ver"], q["w3"] = 27, w3
    fix = lambda c: {**c, "v16": (c["v16"][0], 0.0, 0.0, 0.0)}
    q["l36"] = [fix(c) for c in p["l36"]]
    q["l68"] = [fix(c) for c in p["l68"]]
    oi, ci = len(p["l52"]), len(p["l36"])
    q["l52"] = p["l52"] + [p["legacy_obj"]]
    q["l36"] = q["l36"] + [{**fix(p["legacy_cell"]), "u0": oi, "u4": SPECIAL_CELL_FLAGS}]
    q["a84"], q["a100"], q["a116"] = [NONE, ci], [NONE, oi], [oi]
    q.pop("legacy_cell"); q.pop("legacy_obj")
    return q


def summary(p):
    out = {k: (len(v) if isinstance(v, list) else v) for k, v in p.items()
           if k not in ("legacy_cell", "legacy_obj")}
    return out


if __name__ == "__main__":
    for path in sys.argv[1:]:
        p = parse(open(path, "rb").read())
        print(path.split("/")[-1].split("\\")[-1], summary(p))
