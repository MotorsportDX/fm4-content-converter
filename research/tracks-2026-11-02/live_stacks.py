"""Rantai fungsi guest setiap thread fm4_rex.exe yang sedang berjalan (dbghelp StackWalk64).

Thread hanya di-suspend selama stack-nya ditelusuri; memori proses hanya dibaca. Frame di
dalam fm4_rex.exe dipetakan ke `sub_XXXXXXXX` lewat fm4_rex.map (nama fungsi guest hasil
recompile). Dipakai untuk melihat di mana game macet saat memuat track.

    python research/tracks-2026-11-02/live_stacks.py <BuildRoot>\\game-build\\fm4_rex.map
"""
import bisect, ctypes, os, re, struct, sys
from ctypes import wintypes as w

TARGET = os.environ.get("TARGET_EXE", "fm4_rex.exe").lower()
k32 = ctypes.WinDLL("kernel32", use_last_error=True)
dbg = ctypes.WinDLL("dbghelp", use_last_error=True)
k32.OpenProcess.restype = k32.OpenThread.restype = k32.CreateToolhelp32Snapshot.restype = w.HANDLE
k32.SuspendThread.argtypes = k32.ResumeThread.argtypes = k32.CloseHandle.argtypes = [w.HANDLE]
k32.GetThreadContext.argtypes = [w.HANDLE, ctypes.c_void_p]


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [("dwSize", w.DWORD), ("cntUsage", w.DWORD), ("th32ProcessID", w.DWORD),
                ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", w.DWORD), ("cntThreads", w.DWORD),
                ("th32ParentProcessID", w.DWORD), ("pcPriClassBase", ctypes.c_long), ("dwFlags", w.DWORD),
                ("szExeFile", ctypes.c_wchar*260)]


class THREADENTRY32(ctypes.Structure):
    _fields_ = [("dwSize", w.DWORD), ("cntUsage", w.DWORD), ("th32ThreadID", w.DWORD),
                ("th32OwnerProcessID", w.DWORD), ("tpBasePri", ctypes.c_long), ("tpDeltaPri", ctypes.c_long),
                ("dwFlags", w.DWORD)]


class ADDRESS64(ctypes.Structure):
    _fields_ = [("Offset", ctypes.c_uint64), ("Segment", w.WORD), ("Mode", ctypes.c_int)]


class KDHELP64(ctypes.Structure):
    _fields_ = [("data", ctypes.c_uint64*20)]


class STACKFRAME64(ctypes.Structure):
    _fields_ = [("AddrPC", ADDRESS64), ("AddrReturn", ADDRESS64), ("AddrFrame", ADDRESS64),
                ("AddrStack", ADDRESS64), ("AddrBStore", ADDRESS64), ("FuncTableEntry", ctypes.c_void_p),
                ("Params", ctypes.c_uint64*4), ("Far", w.BOOL), ("Virtual", w.BOOL),
                ("Reserved", ctypes.c_uint64*3), ("KdHelp", KDHELP64)]


def find_pid():
    snap = k32.CreateToolhelp32Snapshot(2, 0)
    pe = PROCESSENTRY32W(); pe.dwSize = ctypes.sizeof(pe)
    ok = k32.Process32FirstW(snap, ctypes.byref(pe)); pid = None
    while ok:
        if pe.szExeFile.lower() == TARGET:
            pid = pe.th32ProcessID
        ok = k32.Process32NextW(snap, ctypes.byref(pe))
    k32.CloseHandle(snap)
    return pid


pid = find_pid()
if not pid:
    raise SystemExit(f"{TARGET} not running")
hproc = k32.OpenProcess(0x1F0FFF, False, pid)
dbg.SymInitializeW.argtypes = [w.HANDLE, w.LPCWSTR, w.BOOL]
dbg.SymInitializeW(hproc, None, True)
dbg.SymFunctionTableAccess64.restype = ctypes.c_void_p
dbg.SymFunctionTableAccess64.argtypes = [w.HANDLE, ctypes.c_uint64]
dbg.SymGetModuleBase64.restype = ctypes.c_uint64
dbg.SymGetModuleBase64.argtypes = [w.HANDLE, ctypes.c_uint64]
FTA = ctypes.CFUNCTYPE(ctypes.c_void_p, w.HANDLE, ctypes.c_uint64)(lambda h, a: dbg.SymFunctionTableAccess64(h, a))
GMB = ctypes.CFUNCTYPE(ctypes.c_uint64, w.HANDLE, ctypes.c_uint64)(lambda h, a: dbg.SymGetModuleBase64(h, a))
dbg.StackWalk64.argtypes = [w.DWORD, w.HANDLE, w.HANDLE, ctypes.POINTER(STACKFRAME64), ctypes.c_void_p,
                            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]

syms = []
if len(sys.argv) > 1 and os.path.exists(sys.argv[1]):
    for l in open(sys.argv[1], encoding="utf-8", errors="replace"):
        m = re.match(r"\s*0001:[0-9a-f]+\s+(\S+)\s+([0-9a-f]{16})\s", l)
        if m and not m.group(1).startswith("__imp_"):
            syms.append((int(m.group(2), 16)-0x140000000, m.group(1)))
syms.sort()
exe_base = dbg.SymGetModuleBase64(hproc, 0)  # placeholder


def name(pc):
    base = dbg.SymGetModuleBase64(hproc, pc)
    if syms and base and base == exe_base_real:
        k = bisect.bisect_right(syms, (pc-base, "~"))-1
        return f"{syms[k][1]}+0x{pc-base-syms[k][0]:x}"
    return f"{pc:x}"


# fm4_rex.exe base: module of the main image
psapi = ctypes.WinDLL("psapi")
psapi.EnumProcessModulesEx.argtypes = [w.HANDLE, ctypes.POINTER(w.HMODULE), w.DWORD, ctypes.POINTER(w.DWORD), w.DWORD]
mods = (w.HMODULE*1)(); need = w.DWORD()
psapi.EnumProcessModulesEx(hproc, mods, ctypes.sizeof(mods), ctypes.byref(need), 3)
exe_base_real = mods[0]

snap = k32.CreateToolhelp32Snapshot(4, 0)
te = THREADENTRY32(); te.dwSize = ctypes.sizeof(te)
tids = []; ok = k32.Thread32First(snap, ctypes.byref(te))
while ok:
    if te.th32OwnerProcessID == pid:
        tids.append(te.th32ThreadID)
    ok = k32.Thread32Next(snap, ctypes.byref(te))
k32.CloseHandle(snap)
for tid in tids:
    h = k32.OpenThread(0x1FFFFF, False, tid)
    if not h:
        continue
    buf = (ctypes.c_ubyte*(1232+16))()
    addr = (ctypes.addressof(buf)+15) & ~15
    struct.pack_into("<I", (ctypes.c_ubyte*1232).from_address(addr), 0x30, 0x10000B)
    k32.SuspendThread(h)
    try:
        if not k32.GetThreadContext(h, ctypes.c_void_p(addr)):
            continue
        raw = (ctypes.c_ubyte*1232).from_address(addr)
        sf = STACKFRAME64()
        sf.AddrPC.Offset = struct.unpack_from("<Q", raw, 0xF8)[0]
        sf.AddrStack.Offset = struct.unpack_from("<Q", raw, 0x98)[0]
        sf.AddrFrame.Offset = struct.unpack_from("<Q", raw, 0xA0)[0]
        sf.AddrPC.Mode = sf.AddrStack.Mode = sf.AddrFrame.Mode = 3
        chain = []
        for _ in range(60):
            if not dbg.StackWalk64(0x8664, hproc, h, ctypes.byref(sf), ctypes.c_void_p(addr), None,
                                   ctypes.cast(FTA, ctypes.c_void_p), ctypes.cast(GMB, ctypes.c_void_p), None):
                break
            if sf.AddrPC.Offset == 0:
                break
            chain.append(name(sf.AddrPC.Offset))
        guest = [c for c in chain if c.startswith("sub_")]
        if guest:
            print(tid, " <- ".join(guest[:16]))
    finally:
        k32.ResumeThread(h); k32.CloseHandle(h)
