"""Stack guest saat fm4_rex.exe crash karena exception yang tidak tertangani.

Menunggu proses muncul, menempel sebagai debugger (`DebugActiveProcess`), dan meneruskan
setiap exception ke proses itu sendiri. Runtime memakai access violation untuk memori
fisik guest, jadi exception kesempatan pertama dibiarkan. Pada kesempatan kedua (crash),
thread yang crash ditelusuri dengan dbghelp `StackWalk64`. Frame fm4_rex.exe dipetakan
ke `sub_XXXXXXXX` lewat fm4_rex.map, lalu `r13` (LR guest) dan alamat fault dicetak.
Debugger dilepas tanpa mematikan proses.

    python research/tracks-2026-11-02/crash_stack.py <BuildRoot>\\game-build\\fm4_rex.map [--timeout detik]
"""
import argparse, bisect, ctypes, re, struct, sys, time
from ctypes import wintypes as w

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
dbg = ctypes.WinDLL("dbghelp", use_last_error=True)
psapi = ctypes.WinDLL("psapi")
k32.OpenProcess.restype = k32.OpenThread.restype = k32.CreateToolhelp32Snapshot.restype = w.HANDLE
k32.GetThreadContext.argtypes = [w.HANDLE, ctypes.c_void_p]
k32.ContinueDebugEvent.argtypes = [w.DWORD, w.DWORD, w.DWORD]
k32.WaitForDebugEvent.argtypes = [ctypes.c_void_p, w.DWORD]
dbg.SymInitializeW.argtypes = [w.HANDLE, w.LPCWSTR, w.BOOL]
dbg.SymFunctionTableAccess64.restype = ctypes.c_void_p
dbg.SymFunctionTableAccess64.argtypes = [w.HANDLE, ctypes.c_uint64]
dbg.SymGetModuleBase64.restype = ctypes.c_uint64
dbg.SymGetModuleBase64.argtypes = [w.HANDLE, ctypes.c_uint64]
psapi.EnumProcessModulesEx.argtypes = [w.HANDLE, ctypes.POINTER(w.HMODULE), w.DWORD, ctypes.POINTER(w.DWORD), w.DWORD]


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [("dwSize", w.DWORD), ("cntUsage", w.DWORD), ("pid", w.DWORD), ("heap", ctypes.c_size_t),
                ("module", w.DWORD), ("threads", w.DWORD), ("parent", w.DWORD), ("pri", ctypes.c_long),
                ("flags", w.DWORD), ("exe", ctypes.c_wchar * 260)]


class ADDRESS64(ctypes.Structure):
    _fields_ = [("Offset", ctypes.c_uint64), ("Segment", w.WORD), ("Mode", ctypes.c_int)]


class STACKFRAME64(ctypes.Structure):
    _fields_ = [("AddrPC", ADDRESS64), ("AddrReturn", ADDRESS64), ("AddrFrame", ADDRESS64),
                ("AddrStack", ADDRESS64), ("AddrBStore", ADDRESS64), ("FuncTableEntry", ctypes.c_void_p),
                ("Params", ctypes.c_uint64 * 4), ("Far", w.BOOL), ("Virtual", w.BOOL),
                ("Reserved", ctypes.c_uint64 * 3), ("KdHelp", ctypes.c_uint64 * 20)]


dbg.StackWalk64.argtypes = [w.DWORD, w.HANDLE, w.HANDLE, ctypes.POINTER(STACKFRAME64), ctypes.c_void_p,
                            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
FTA = ctypes.CFUNCTYPE(ctypes.c_void_p, w.HANDLE, ctypes.c_uint64)(lambda h, a: dbg.SymFunctionTableAccess64(h, a))
GMB = ctypes.CFUNCTYPE(ctypes.c_uint64, w.HANDLE, ctypes.c_uint64)(lambda h, a: dbg.SymGetModuleBase64(h, a))


def find_pid(target="fm4_rex.exe"):
    snap = k32.CreateToolhelp32Snapshot(2, 0)
    pe = PROCESSENTRY32W(); pe.dwSize = ctypes.sizeof(pe)
    ok, pid = k32.Process32FirstW(snap, ctypes.byref(pe)), None
    while ok:
        pid = pe.pid if pe.exe.lower() == target else pid
        ok = k32.Process32NextW(snap, ctypes.byref(pe))
    k32.CloseHandle(snap)
    return pid


def load_map(path):
    syms = []
    for line in open(path, encoding="utf-8", errors="replace"):
        m = re.match(r"\s*0001:[0-9a-f]+\s+(\S+)\s+([0-9a-f]{16})\s", line)
        if m and not m.group(1).startswith("__imp_"):
            syms.append((int(m.group(2), 16) - 0x140000000, m.group(1)))
    return sorted(syms)


def stack(hproc, hthread, exe_base, syms):
    buf = (ctypes.c_ubyte * (1232 + 16))()
    addr = (ctypes.addressof(buf) + 15) & ~15
    raw = (ctypes.c_ubyte * 1232).from_address(addr)
    struct.pack_into("<I", raw, 0x30, 0x10000B)
    if not k32.GetThreadContext(hthread, ctypes.c_void_p(addr)):
        return {}, []
    reg = {n: struct.unpack_from("<Q", raw, o)[0] for n, o in
           (("rip", 0xF8), ("rsp", 0x98), ("rbp", 0xA0), ("r13", 0xE0), ("rcx", 0x80), ("rdx", 0x88),
            ("rdi", 0xB0), ("rsi", 0xA8))}
    sf = STACKFRAME64()
    sf.AddrPC.Offset, sf.AddrStack.Offset, sf.AddrFrame.Offset = reg["rip"], reg["rsp"], reg["rbp"]
    sf.AddrPC.Mode = sf.AddrStack.Mode = sf.AddrFrame.Mode = 3
    chain = []
    for _ in range(64):
        if not dbg.StackWalk64(0x8664, hproc, hthread, ctypes.byref(sf), ctypes.c_void_p(addr), None,
                               ctypes.cast(FTA, ctypes.c_void_p), ctypes.cast(GMB, ctypes.c_void_p), None):
            break
        pc = sf.AddrPC.Offset
        if not pc:
            break
        if exe_base <= pc < exe_base + 0x10000000 and syms:
            k = bisect.bisect_right(syms, (pc - exe_base, "~")) - 1
            chain.append(f"{syms[k][1]}+0x{pc - exe_base - syms[k][0]:x}")
        else:
            chain.append(f"{pc:x}")
    return reg, chain


def read(hproc, address, size):
    buf, got = ctypes.create_string_buffer(size), ctypes.c_size_t()
    k32.ReadProcessMemory.argtypes = [w.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t,
                                      ctypes.POINTER(ctypes.c_size_t)]
    ok = k32.ReadProcessMemory(hproc, ctypes.c_void_p(address), buf, size, ctypes.byref(got))
    return buf.raw[:got.value] if ok else b""


def guest_state(hproc, ctx_address, dump):
    """Guest GPRs r0..r31 of the recompiled PPC context (host rdi, 8 bytes per register),
    then `dump` bytes of guest memory at each register that looks like a guest pointer."""
    raw = read(hproc, ctx_address, 32 * 8)
    if len(raw) < 256:
        return
    gpr = struct.unpack("<32Q", raw)
    print("  guest", " ".join(f"r{i}={v & 0xFFFFFFFF:x}" for i, v in enumerate(gpr)))
    for i, v in enumerate(gpr):
        v &= 0xFFFFFFFF
        if dump and 0x20000000 <= v < 0xA0000000 and i not in (1, 2, 13):
            mem = read(hproc, 0x100000000 + v, dump)
            print(f"  [r{i}={v:x}]", mem.hex(" ", 4))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("map")
    ap.add_argument("--timeout", type=float, default=1800)
    ap.add_argument("--dump", type=lambda x: int(x, 0), default=0x100, help="guest bytes at each pointer register")
    a = ap.parse_args()
    syms = load_map(a.map)
    end = time.time() + a.timeout
    pid = None
    while not pid and time.time() < end:
        pid = find_pid()
        time.sleep(0.5)
    if not pid or not k32.DebugActiveProcess(pid):
        raise SystemExit(f"cannot attach ({ctypes.get_last_error()})")
    k32.DebugSetProcessKillOnExit(False)
    hproc = k32.OpenProcess(0x1F0FFF, False, pid)
    dbg.SymInitializeW(hproc, None, True)
    mods = (w.HMODULE * 1)(); need = w.DWORD()
    psapi.EnumProcessModulesEx(hproc, mods, ctypes.sizeof(mods), ctypes.byref(need), 3)
    exe_base = mods[0] or 0
    print("attached", pid, hex(exe_base), flush=True)
    event = (ctypes.c_ubyte * 176)()
    while time.time() < end:
        if not k32.WaitForDebugEvent(event, 1000):
            continue
        code, epid, tid = struct.unpack_from("<III", event, 0)
        status = 0x00010002  # DBG_CONTINUE
        if code == 1:  # EXCEPTION_DEBUG_EVENT
            status = 0x80010001  # DBG_EXCEPTION_NOT_HANDLED
            exc, _, _, at, nparams = struct.unpack_from("<IIQQI", event, 16)
            info = struct.unpack_from("<15Q", event, 48)
            first = struct.unpack_from("<I", event, 168)[0]
            if not first:
                h = k32.OpenThread(0x1FFFFF, False, tid)
                reg, chain = stack(hproc, h, exe_base, syms)
                print(f"crash thread {tid} code {exc:#x} at {at:#x} fault {info[1]:#x} (guest {info[1] - 0x100000000:#x})")
                print("  regs", {k: hex(v) for k, v in reg.items()}, "rip-rva", hex(reg.get("rip", 0) - exe_base))
                print("  stack", " <- ".join(chain[:24]), flush=True)
                guest_state(hproc, reg.get("rdi", 0), a.dump)
                sys.stdout.flush()
                k32.ContinueDebugEvent(epid, tid, status)
                k32.DebugActiveProcessStop(pid)
                return
        elif code == 5:  # EXIT_PROCESS_DEBUG_EVENT
            print("process exited", struct.unpack_from("<I", event, 16)[0], flush=True)
            k32.ContinueDebugEvent(epid, tid, status)
            return
        k32.ContinueDebugEvent(epid, tid, status)
    k32.DebugActiveProcessStop(pid)


if __name__ == "__main__":
    main()
