"""Pembaca FPVS versi 11 (FM2), dibandingkan dengan urutan versi 24 (`fm3.track_pvs.parse`).

Header: magic, versi 11, ukuran data CPU (13,000,000 di New York, sama dengan `cpudatasize`
PVSGen di laporan build), h0, h2. Lalu per zona (58 di New York ribbon 1): ID model u16, ID
tekstur u32 (indeks build `_0x%08X`), dan satu flag u8 per tekstur. Versi 24 menambah satu daftar
u16 di zona. Bagian berikutnya dicoba berurutan; `walk` berhenti di field yang belum cocok.

    python research/tracks-fm2-2026-11-11/pvs11.py <newyork_01.pvs>
"""
import struct
import sys

from fm4_converter.fm3.track_pvs import Reader


def zones(r):
    out = []
    for _ in range(r.take("I")):
        models = r.u16list()
        textures = r.u32list()
        flags = r.many(r.take("I"), "B")
        if len(flags) != len(textures):
            raise ValueError("zone flags do not match its textures")
        out.append({"models": models, "textures": textures, "flags": flags})
    return out


def walk(data):
    r = Reader(data)
    magic, ver, cpu = r.take("4sII")
    if magic != b"FPVS" or ver != 11:
        raise ValueError("not FPVS 11")
    p = {"ver": ver, "cpu": cpu, "h0": r.take("H"), "h2": r.take("H")}
    p["zones"] = zones(r)
    # The track's textures, as version 24's l20: (build ID `_0x%08X`, record of `<track>.stx.bin`,
    # four floats, flags); New York ribbon 1 lists 2,920, the stx 1,513 records.
    p["textures"] = [r.take("IIffffI") for _ in range(r.take("I"))]
    # Per model (1,555): the textures it uses (indexes into `textures`), two u16, its scale and
    # translation (float3 and float4), five u32 (flags and an LOD distance); the second texture is
    # the model's own lightmap (`s_lightMap`). Version 24 has strings here.
    p["models"] = []
    for _ in range(r.take("I")):
        uses = r.u32list()
        a, b = r.take("H"), r.take("H")
        scale, move = r.take("3f"), r.take("4f")
        tail = r.take("5I")
        p["models"].append({"textures": uses, "u16": (a, b), "scale": scale, "move": move, "tail": tail})
    p["after_models"] = r.o
    return p, r


if __name__ == "__main__":
    data = open(sys.argv[1], "rb").read()
    p, r = walk(data)
    z = p["zones"]
    print("zones", len(z), "models", sum(len(x["models"]) for x in z), "max model",
          max(max(x["models"], default=0) for x in z), "max texture", max(max(x["textures"], default=0) for x in z))
    print("textures", len(p["textures"]), "models", len(p["models"]), p["models"][:2])
    print("after models at", hex(r.o), "of", hex(len(data)))
    for k in range(8):
        print(f"  {r.o + 16 * k:06x}", data[r.o + 16 * k:r.o + 16 * k + 16].hex(" "))
