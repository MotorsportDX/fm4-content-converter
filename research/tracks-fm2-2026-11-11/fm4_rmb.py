"""Pembaca lengkap model track FM4 (RMB v5/v6): sub-model, mesh, set material, nama, command buffer.

Urutan field mengikuti `CTrackModel` (template 010 Editor `FM3_rmb_bin.bt` dari Forza-X360-IO,
GPL-3.0, dipakai sebagai rujukan format). `parse` membaca sampai `CommandBufferGroup` dan
memeriksa bahwa grup itu mulai tepat di akhir bagian yang dibaca.

    python research/tracks-fm2-2026-11-11/fm4_rmb.py <bin.zip FM4>            # survei teknik
    python research/tracks-fm2-2026-11-11/fm4_rmb.py <bin.zip FM4> <model>    # satu model
"""
import collections
import struct
import sys
import zipfile

from fm4_converter.fm3 import track_rmb
from fm4_converter.fm3.integration import archive_read


class R:
    def __init__(self, d, o=0):
        self.d, self.o = d, o

    def u(self):
        v = struct.unpack_from(">I", self.d, self.o)[0]
        self.o += 4
        return v

    def f(self, n):
        v = struct.unpack_from(f">{n}f", self.d, self.o)
        self.o += 4 * n
        return v

    def s(self):
        n = self.u()
        v = self.d[self.o:self.o + n]
        self.o += n
        return v.decode("latin1")

    def raw(self, n):
        v = self.d[self.o:self.o + n]
        self.o += n
        return v


def parse(d):
    r = R(d)
    m = {"version": r.u(), "bounds": (r.f(4), r.f(4)), "world": r.f(16), "base_version": r.u()}
    m["ordered"] = (r.u(), r.u())
    m["container_version"] = r.u()
    m["submodels"] = []
    for _ in range(r.u()):
        sm = {"version": r.u(), "offset": r.f(4), "min": r.f(4), "max": r.f(4)}
        sm["ts_version"] = r.u()
        sm["name"] = r.s()
        sm["vb_version"] = r.u()
        sm["vcount"], sm["stride"] = r.u(), r.u()
        sm["vb_at"] = r.o
        sm["vertices"] = r.raw(sm["vcount"] * sm["stride"])
        sm["mc_version"] = r.u()
        sm["meshes"] = []
        for _ in range(r.u()):
            me = {"tm_version": r.u(), "version": r.u(), "name": r.s(), "lod": r.u(), "prim": r.u(), "material": r.u()}
            me["unpack_version"] = r.u()
            me["position_offset"], me["position_scale"], me["uv_offset_scale"] = r.f(4), r.f(4), r.f(4)
            me["ib_version"] = r.u()
            me["icount"], me["istride"] = r.u(), r.u()
            me["indices"] = r.raw(me["icount"] * me["istride"])
            me["flags"] = r.u() if me["version"] >= 2 else None
            sm["meshes"].append(me)
        m["submodels"].append(sm)
    m["msc_version"] = r.u()
    m["material_sets"] = []
    for _ in range(r.u()):
        s = {"version": r.u(), "mc_version": r.u(), "materials": []}
        for _ in range(r.u()):
            mat = {"version": r.u(), "fx": r.u(), "technique": r.u()}
            for key in ("vs", "ps"):
                ver, n = r.u(), r.u()
                mat[key] = [r.f(4) for _ in range(n)]
            ver, n = r.u(), r.u()
            mat["samplers"] = [r.u() for _ in range(n)]
            s["materials"].append(mat)
        m["material_sets"].append(s)
    for key in ("fx_names", "mesh_names"):
        ver, n = r.u(), r.u()
        m[key] = [r.s() for _ in range(n)]
    m["tail_at"] = r.o
    g = track_rmb.group(d)
    if g.at != r.o:
        raise ValueError(f"command buffer group at {g.at:#x}, read to {r.o:#x}")
    m["group"] = g
    return m


def kind(m):
    """(fx, technique, stride, submodels, meshes) of a model."""
    mats = [x for s in m["material_sets"] for x in s["materials"]]
    fx = sorted({m["fx_names"][x["fx"]] for x in mats})
    return (tuple(fx), tuple(sorted({x["technique"] for x in mats})),
            tuple(sorted({s["stride"] for s in m["submodels"]})), len(m["submodels"]),
            sum(len(s["meshes"]) for s in m["submodels"]))


if __name__ == "__main__":
    z = zipfile.ZipFile(sys.argv[1])
    if len(sys.argv) > 2:
        m = parse(archive_read(z, sys.argv[2]))
        for sm in m["submodels"]:
            print("submodel", sm["name"], sm["vcount"], "x", sm["stride"])
            for me in sm["meshes"]:
                print("  mesh", me["name"], "lod", me["lod"], "prim", me["prim"], "material", me["material"],
                      "indices", me["icount"], "uvos", me["uv_offset_scale"], "pos", me["position_offset"], me["position_scale"])
        for i, s in enumerate(m["material_sets"]):
            for x in s["materials"]:
                print("set", i, m["fx_names"][x["fx"]], "tech", x["technique"], "vs", x["vs"], "ps", x["ps"], "samplers", x["samplers"])
        print("fx", m["fx_names"], "mesh names", m["mesh_names"])
        print("slots", [(i, s["sizes"]) for i, s in enumerate(m["group"].slots) if s["sizes"] != (0, 0, 0)])
    else:
        kinds, bad = collections.Counter(), 0
        examples = {}
        for info in z.infolist():
            if not info.filename.lower().endswith(".rmb.bin"):
                continue
            try:
                m = parse(archive_read(z, info))
            except Exception as e:
                bad += 1
                if bad < 4:
                    print("fail", info.filename, e)
                continue
            k = kind(m)
            kinds[k] += 1
            if k[4] == 1:
                examples.setdefault(k, info.filename)
        for k, n in kinds.most_common():
            print(n, k, examples.get(k, ""))
        print("failed", bad)
