"""Read-only FM3 XEX loaded-PE evidence scanner; emits narrow static references."""
from __future__ import annotations
import argparse
import bisect
import hashlib
import json
from pathlib import Path
import struct

FIELDS = (
    "CMHeight", "CMBackFront", "CMLeftRight", "InitialMass", "BlockDimX",
    "BlockDimY", "BlockDimZ", "DefRideHeight", "MinRideHeight", "MaxRideHeight",
    "MaxCompressHeight", "DefSpringRate", "MinSpringRate", "MaxSpringRate",
    "DefDampenBumpRate", "MinDampenBumpRate", "MaxDampenBumpRate",
    "DampenBumpClamp", "DefDampenReboundRate", "MinDampenReboundRate",
    "MaxDampenReboundRate", "DampenReboundClamp", "BumpstopStiffness",
    "BumpstopDamping", "ChassisPivotX", "ChassisPivotY", "TirePivotX",
    "CamberChangeRatioCompression", "CamberChangeRatioExpansion", "StaticToe",
    "StaticCamber", "Caster", "SteerRotAxisTireOffsetX", "YMaxSpringVel",
    "DefSwaybarStiffness", "MinSwaybarStiffness", "MaxSwaybarStiffness",
    "SwaybarDamping", "SuspensionPhysicsTypeID",
)


def signed16(v):
    return v - 65536 if v & 32768 else v


def scan(image: Path, sections_file: Path):
    b = image.read_bytes()
    if b[:2] != b"MZ":
        raise ValueError("not loaded PE")
    pe = struct.unpack_from("<I", b, 0x3C)[0]
    if b[pe:pe + 4] != b"PE\0\0":
        raise ValueError("PE signature")
    base = struct.unpack_from("<I", b, pe + 24 + 28)[0]
    entry_rva = struct.unpack_from("<I", b, pe + 24 + 16)[0]
    sections = []
    for line in sections_file.read_text().splitlines():
        name, address, size, flags = line.split("\t")
        sections.append(dict(name=name, address=int(address), size=int(size), flags=int(flags)))
    pdata = next(s for s in sections if s["name"] == ".pdata")
    function_starts = [
        struct.unpack_from(">I", b, at)[0]
        for at in range(pdata["address"] - base, pdata["address"] - base + pdata["size"], 8)
    ]
    function_starts = sorted(set(x for x in function_starts if base <= x < base + len(b)))
    fields = {}
    addresses = {}
    for name in FIELDS:
        needle = name.encode() + b"\0"
        offset = b.find(b"\0" + needle)
        offset = offset + 1 if offset >= 0 else -1
        if offset >= 0:
            fields[name] = {"string_address": f"0x{base + offset:08X}", "references": []}
            addresses[base + offset] = name
    # Conservative adjacent-window LIS + ADDI/ORI matcher. Record instructions;
    # a human must inspect intervening register definitions / control flow.
    for section in sections:
        if not section["flags"] & 2:
            continue
        lo = section["address"] - base
        hi = min(lo + section["size"], len(b)) & ~3
        for at in range(lo, hi, 4):
            op = struct.unpack_from(">I", b, at)[0]
            if op >> 26 != 15 or (op >> 16) & 31 != 0:  # lis
                continue
            rd = (op >> 21) & 31
            high = (signed16(op & 65535) << 16) & 0xFFFFFFFF
            for at2 in range(at + 4, min(at + 65, hi), 4):
                op2 = struct.unpack_from(">I", b, at2)[0]
                major = op2 >> 26
                ra = (op2 >> 16) & 31
                rs = (op2 >> 21) & 31
                address = None
                if major == 14 and ra == rd:  # addi destination, source, signed
                    address = (high + signed16(op2 & 65535)) & 0xFFFFFFFF
                elif major == 24 and rs == rd:  # ori source, destination
                    address = high | (op2 & 65535)
                if address in addresses:
                    va = base + at2
                    index = bisect.bisect_right(function_starts, va) - 1
                    start = function_starts[index] if index >= 0 else None
                    fields[addresses[address]]["references"].append({
                        "lis_address": f"0x{base + at:08X}",
                        "reference_address": f"0x{va:08X}",
                        "function_pdata_start": f"0x{start:08X}" if start else None,
                        "window_instructions": (at2 - at) // 4,
                        "requires_register_flow_review": True,
                    })
    return {
        "image_sha256": hashlib.sha256(b).hexdigest(),
        "image_size": len(b),
        "image_base_from_pe": f"0x{base:08X}",
        "entry_point_from_pe": f"0x{base + entry_rva:08X}",
        "sections": sections,
        "fields": fields,
        "method": "Big-endian PPC LIS followed within 16 instructions by ADDI/ORI; .pdata 8-byte entries. References require disassembly confirmation.",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--folder", type=Path, required=True)
    args = parser.parse_args()
    result = scan(args.folder / "loaded-image.bin", args.folder / "sections.tsv")
    (args.folder / "references.json").write_text(json.dumps(result, indent=2) + "\n")
    refs = sorted({r["reference_address"][2:] for v in result["fields"].values() for r in v["references"]})
    (args.folder / "addresses.txt").write_text("\n".join(refs) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k not in ("fields", "sections")}, indent=2))
    for name, field in result["fields"].items():
        print(name, field["string_address"], [(r["reference_address"], r["function_pdata_start"]) for r in field["references"]])


if __name__ == "__main__":
    main()
