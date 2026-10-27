"""Static, read-only extraction of FM4 mass/CG instruction evidence.

Generated C++ comments are indexed as one PPC instruction each. Branch labels
and link-register assignments are cross-checks; no game code is executed.
"""
import argparse
import hashlib
import json
import re
import struct
import subprocess
from pathlib import Path
from ..paths import PROJECT_ROOT

ROOT = PROJECT_ROOT
GEN = ROOT / "work/fm4-rex/generated/default"
IMAGE = ROOT / "work/fm4/loaded-image.bin"
BASE = 0x82000000


def functions():
    for path in sorted(GEN.glob("*.cpp")):
        current = None
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            m = re.match(r"DEFINE_REX_FUNC\(sub_([0-9A-F]+)\)", line)
            if m:
                if current:
                    yield current
                pc = int(m[1], 16)
                current = {"start": f"0x{pc:08X}", "file": str(path),
                           "line": number, "instructions": [], "crosscheck_errors": []}
            if current is None:
                continue
            m = re.match(r"loc_([0-9A-F]+):", line)
            if m and int(m[1], 16) != pc:
                current["crosscheck_errors"].append(f"label {m[1]} != {pc:08X}")
                pc = int(m[1], 16)
            m = re.match(r"\s*// (.*)", line)
            if m:
                current["instructions"].append(
                    {"address": f"0x{pc:08X}", "asm": m[1], "line": number})
                pc += 4
            m = re.match(r"\s*ctx.lr = 0x([0-9A-F]+);", line)
            if m and int(m[1], 16) != pc:
                current["crosscheck_errors"].append(f"lr {m[1]} != {pc:08X}")
        if current:
            yield current


def annotate(fn, data):
    regs = {}
    for inst in fn["instructions"]:
        a = inst["asm"]
        m = re.fullmatch(r"lis r(\d+),(-?\d+)", a)
        if m:
            regs[int(m[1])] = (int(m[2]) << 16) & 0xFFFFFFFF
            continue
        m = re.fullmatch(r"addi r(\d+),r(\d+),(-?\d+)", a)
        if m and int(m[2]) in regs:
            value = (regs[int(m[2])] + int(m[3])) & 0xFFFFFFFF
            regs[int(m[1])] = value
            offset = value - BASE
            if 0 <= offset < len(data):
                raw = data[offset:offset + 200].split(b"\0", 1)[0]
                if raw and all(32 <= c < 127 for c in raw):
                    inst["literal"] = raw.decode("ascii")
                    inst["literal_address"] = f"0x{value:08X}"
            continue
        m = re.fullmatch(r"lfs f\d+,(-?\d+)\(r(\d+)\)", a)
        if m and int(m[2]) in regs:
            value = (regs[int(m[2])] + int(m[1])) & 0xFFFFFFFF
            offset = value - BASE
            if 0 <= offset <= len(data) - 4:
                inst["float_address"] = f"0x{value:08X}"
                inst["float_value"] = struct.unpack_from(">f", data, offset)[0]
        m = re.match(r"\w+\.? r(\d+),", a)
        if m:
            regs.pop(int(m[1]), None)
        if a.startswith(("bl ", "bctrl")):
            for r in range(0, 13):
                regs.pop(r, None)
    return fn


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--functions", nargs="+", required=True)
    p.add_argument("--verify-raw", action="store_true",
                   help="Cross-check every comment against disassembly of the loaded image.")
    args = p.parse_args()
    names = {f"0x{int(x, 16):08X}" for x in args.functions}
    data = IMAGE.read_bytes()
    picked = [annotate(fn, data) for fn in functions() if fn["start"] in names]
    if {f["start"] for f in picked} != names:
        raise ValueError("some requested functions not found")
    args.out.mkdir(parents=True, exist_ok=True)
    for fn in picked:
        text = [f'{fn["start"]} {fn["file"]}:{fn["line"]}']
        for i in fn["instructions"]:
            suffix = ""
            if "literal" in i:
                suffix = f' ; {i["literal_address"]} "{i["literal"]}"'
            if "float_value" in i:
                suffix = f' ; {i["float_address"]} float={i["float_value"]!r}'
            text.append(f'{i["address"]}: {i["asm"]}{suffix}')
        (args.out / (fn["start"] + ".asm.txt")).write_text("\n".join(text), encoding="utf-8")
    raw_verification = None
    if args.verify_raw:
        addresses = args.out / "verify-addresses.txt"
        centers = []
        for fn in picked:
            insts = fn["instructions"]
            centers.extend(range(int(insts[0]["address"], 16) + 96,
                                 int(insts[-1]["address"], 16) + 100, 160))
        addresses.write_text("\n".join(f"{x:08X}" for x in centers), encoding="ascii")
        disassembler = ROOT / "work/fm4/disassemble.exe"
        proc = subprocess.run([str(disassembler), str(IMAGE), str(addresses)],
                              capture_output=True, text=True, check=True)
        (args.out / "raw-disassembly.txt").write_text(proc.stdout, encoding="utf-8")
        raw = {}
        for line in proc.stdout.splitlines():
            m = re.fullmatch(r"([0-9A-F]{8}) (.*)", line)
            if m:
                raw["0x" + m[1]] = m[2].strip()
        mismatches = [
            {"address": i["address"], "generated": i["asm"], "raw": raw.get(i["address"])}
            for fn in picked for i in fn["instructions"]
            if raw.get(i["address"]) != i["asm"].strip()
        ]
        raw_verification = {
            "method": "Static disassembler.exe; no game instructions executed.",
            "disassembler_sha256": hashlib.sha256(disassembler.read_bytes()).hexdigest(),
            "instruction_count": sum(len(f["instructions"]) for f in picked),
            "mismatches": mismatches,
        }
    result = {"image": str(IMAGE), "image_sha256": hashlib.sha256(data).hexdigest(),
              "image_base": hex(BASE), "functions": picked,
              "raw_verification": raw_verification,
              "method": "Static generated PPC comments; addresses cross-checked against loc labels and LR.",
              "limitations": "A literal annotation is local constant propagation, not proof of data-flow across calls."}
    (args.out / "functions.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({"functions": len(picked), "crosscheck_errors": [
        [f["start"], f["crosscheck_errors"]] for f in picked if f["crosscheck_errors"]],
        "raw_verification": raw_verification}))


if __name__ == "__main__":
    main()
