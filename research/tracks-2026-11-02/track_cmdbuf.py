"""Dua pengukuran untuk tampilan utama track FM3 yang kosong.

    track_cmdbuf.py hashes <bin.zip>... --out hashes.json
        Hash ucode (XXH3-64, 32 bit bawah, seperti REX_DRAW_LIST_TRACE) setiap shader
        di `*.fxobj` arsip track, dengan nama berkasnya.
    track_cmdbuf.py draws <draws.txt> hashes.json
        Per frame yang direkam REX_DRAW_LIST_TRACE: jumlah draw shader track per
        (render target, depth target). Pass utama dan spion terpisah di sini.
    track_cmdbuf.py models
        Dari fm4_rex.exe yang sedang berjalan (baca memori saja): setiap CTrackModel
        (vtable 0x82002488), jumlah slot command buffer (+64) dan slot yang berisi
        (dword pertama entri 128 byte di +68). `DrawObject` (82314BC8) hanya
        menggambar indeks pass*3 + varian yang < jumlah slot dan berisi.

Memakai `material_atlas.py` FM4-PC (pembaca kontainer shader) dan modul `xxhash`.
"""
import argparse, collections, ctypes, json, struct, sys, zipfile
from ctypes import wintypes as w
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))


def hashes(paths, out, atlas):
    import xxhash
    from fm4_converter.fm3.integration import archive_read
    sys.path.insert(0, atlas)
    from material_atlas import containers, microcode
    table = {}
    for p in paths:
        z = zipfile.ZipFile(p)
        for m in z.namelist():
            if m.lower().endswith(".fxobj"):
                for i, (_, c) in enumerate(containers(archive_read(z, m))):
                    kind = "VS" if struct.unpack_from(">I", c)[0] & 1 else "PS"
                    h = xxhash.xxh3_64_intdigest(microcode(c)) & 0xFFFFFFFF
                    table.setdefault(f"{h:x}", []).append([str(p), m.split("/")[-1], i, kind])
    Path(out).write_text(json.dumps(table))
    print(len(table), "shaders")


def draws(trace, table_path):
    table = json.loads(Path(table_path).read_text())
    frame, count = None, collections.Counter()
    def flush():
        if frame is not None and count:
            print(frame, " ".join(f"rt={rt},ds={ds}:{n}" for (rt, ds), n in sorted(count.items())))
    for line in open(trace):
        p = line.split()
        if p and p[0] == "F":
            flush()
            frame, count = p[1], collections.Counter()
        elif len(p) >= 18 and table.get(p[1].lstrip("0") or "0"):
            count[(p[5], p[6])] += 1
    flush()


def models():
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.OpenProcess.restype = k32.CreateToolhelp32Snapshot.restype = w.HANDLE
    k32.ReadProcessMemory.argtypes = [w.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t,
                                      ctypes.POINTER(ctypes.c_size_t)]

    class Entry(ctypes.Structure):
        _fields_ = [("dwSize", w.DWORD), ("cntUsage", w.DWORD), ("pid", w.DWORD), ("heap", ctypes.c_size_t),
                    ("module", w.DWORD), ("threads", w.DWORD), ("parent", w.DWORD), ("pri", ctypes.c_long),
                    ("flags", w.DWORD), ("exe", ctypes.c_wchar * 260)]

    class Region(ctypes.Structure):
        _fields_ = [("base", ctypes.c_uint64), ("alloc", ctypes.c_uint64), ("alloc_protect", w.DWORD),
                    ("partition", w.WORD), ("size", ctypes.c_uint64), ("state", w.DWORD), ("protect", w.DWORD),
                    ("type", w.DWORD)]

    k32.VirtualQueryEx.argtypes = [w.HANDLE, ctypes.c_void_p, ctypes.POINTER(Region), ctypes.c_size_t]
    snap = k32.CreateToolhelp32Snapshot(2, 0)
    e = Entry(); e.dwSize = ctypes.sizeof(e)
    pid, ok = None, k32.Process32FirstW(snap, ctypes.byref(e))
    while ok:
        pid = e.pid if e.exe.lower() == "fm4_rex.exe" else pid
        ok = k32.Process32NextW(snap, ctypes.byref(e))
    if not pid:
        raise SystemExit("fm4_rex.exe not running")
    h = k32.OpenProcess(0x0410, False, pid)
    base = 0x100000000

    def read(guest, n):
        buf, got = ctypes.create_string_buffer(n), ctypes.c_size_t()
        ok = k32.ReadProcessMemory(h, ctypes.c_void_p(base + guest), buf, n, ctypes.byref(got))
        return buf.raw[:got.value] if ok else b""

    def u32(guest):
        d = read(guest, 4)
        return struct.unpack(">I", d)[0] if len(d) == 4 else 0

    hits, r, addr = [], Region(), base
    while addr < 2 * base and k32.VirtualQueryEx(h, ctypes.c_void_p(addr), ctypes.byref(r), ctypes.sizeof(r)):
        if r.state == 0x1000 and r.protect & 0xEE and not r.protect & 0x100:
            for off in range(0, r.size, 1 << 24):
                data = read(r.base - base + off, min(1 << 24, r.size - off))
                i = data.find(bytes.fromhex("82002488"))
                while i >= 0:
                    if i % 4 == 0:
                        hits.append(r.base - base + off + i)
                    i = data.find(bytes.fromhex("82002488"), i + 1)
        addr = r.base + r.size
    seen = collections.Counter()
    for a in hits:
        n, table = u32(a + 64), u32(a + 68)
        if n > 64:
            continue
        filled = "".join("1" if table and u32(table + 128 * i) else "0" for i in range(n))
        seen[(n, read(a + 276, 1)[:1].hex(), filled)] += 1
    print("models", sum(seen.values()))
    for (n, ready, filled), k in seen.most_common(15):
        print(f"{k:5} slots={n} ready={ready} filled={filled}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["hashes", "draws", "models"])
    ap.add_argument("paths", nargs="*")
    ap.add_argument("--out", default="hashes.json")
    ap.add_argument("--atlas", default=r"I:\Workspace\FM4-PC\outputs\FM4-build\e2e")
    a = ap.parse_args()
    if a.mode == "hashes":
        hashes(a.paths, a.out, a.atlas)
    elif a.mode == "draws":
        draws(*a.paths)
    else:
        models()
