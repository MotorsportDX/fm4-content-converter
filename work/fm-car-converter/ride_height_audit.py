"""Reproduce paired original-byte checks and the stock-suspension benchmark.

No guest process is launched. The scalar evaluator supports only hash-bound
instruction slices and ordinary finite arithmetic; it is not a PPC emulator.
Raw disassembly and game-derived artifacts remain in a new local output folder.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import random
import struct
import subprocess

import benchmark as b
import converter as c
import code_semantics as cs
import suspension_semantics as s


ROOT = Path(__file__).resolve().parents[2]
OLD = ROOT / "outputs/fm-car-converter/code-semantics-v1"
IMAGES = {v: OLD / v / "loaded-image.bin" for v in ("fm3", "fm4")}
SLICES = {
    ("fm3", "extension"): (0x82728010, 0x82728054, "aa914b12625257d392a87ccfec96e68f5211e7cc094a3f1224d52e66a4d27bd9"),
    ("fm4", "extension"): (0x8281AC40, 0x8281AC9C, "e34c66fe06c3e8fd0fb8d4e742ece9ec647a86f3921a72a0184fcb4b81704e9e"),
    ("fm3", "geometry"): (0x827294D8, 0x82729504, "c51d8b2155acb1dafc6200f37ce6d8521f6b205b97f0b3a78f9c4fddf840404b"),
    ("fm4", "geometry"): (0x8281EC20, 0x8281EC50, "3e9afc2b1f3ca096dbb70871e286e10f52d0cfe70dcadd98b21ebd9ad8b7e623"),
    ("fm3", "rest"): (0x82729E84, 0x82729EE8, "2d49270edd0aeaf64a3900872f5bf5c717a439bfdd06f5175af3cd6e52822e22"),
    ("fm4", "rest"): (0x8281F5F4, 0x8281F658, "80f422fefba5a90f35e7d9491f273a090d62fb0b14593026db87c551967dd90f"),
}
IMAGE_HASHES = {
    "fm3": "a1d914cdc4ac837e6ba5cbdf2419d4effbafc160d3c51160a32e6f58e06cb67d",
    "fm4": "7a56b178d856c0dabb6d32120de6b5b6d7182a0c35bff836763d08684e3d5c41",
}


def load_images():
    result = {}
    for version, path in IMAGES.items():
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != IMAGE_HASHES[version]:
            raise c.MappingError("Unsupported retail research image: " + version)
        result[version] = data
    return result


def f32(value):
    return struct.unpack(">f", struct.pack(">f", value))[0]


def signed(value, bits):
    return value - (1 << bits) if value & (1 << (bits - 1)) else value


def scalar_slice(image, version, kind, regs, fp, memory):
    lo, hi, digest = SLICES[version, kind]
    if hashlib.sha256(image[lo - 0x82000000:hi - 0x82000000]).hexdigest() != digest:
        raise c.MappingError("Changed or missing audited instruction slice")
    regs, fp, memory = dict(regs), dict(fp), dict(memory)
    flags, trace = {}, []
    pc = lo
    for _ in range(200):
        if pc == hi:
            break
        if not lo <= pc < hi or pc % 4:
            raise c.MappingError("Branch outside audited slice")
        word = int.from_bytes(image[pc - 0x82000000:pc - 0x82000000 + 4], "big")
        trace.append(hex(pc))
        pc += 4
        op = word >> 26
        d, a, rb, rc = (word >> 21) & 31, (word >> 16) & 31, (word >> 11) & 31, (word >> 6) & 31
        imm, xo = signed(word & 65535, 16), (word >> 1) & 1023
        if word == 0x4E800020:  # blr
            break
        if op in (14, 15):
            regs[d] = ((regs[a] if a else 0) + (imm << (16 if op == 15 else 0))) & 0xFFFFFFFF
        elif op == 31 and xo == 444:  # or / mr
            regs[a] = regs[d] | regs[rb]
        elif op in (48, 52):
            address = ((regs[a] if a else 0) + imm) & 0xFFFFFFFF
            if op == 52:
                memory[address] = f32(fp[d])
            elif address in memory:
                fp[d] = f32(memory[address])
            elif 0 <= address - 0x82000000 <= len(image) - 4:
                fp[d] = struct.unpack_from(">f", image, address - 0x82000000)[0]
            else:
                raise c.MappingError("Unmapped scalar load")
        elif op == 18 and not word & 3:
            pc = pc - 4 + signed(word & 0x03FFFFFC, 26)
        elif op == 16 and d in (4, 12) and not word & 3:
            if bool(flags[a]) == (d == 12):
                pc = pc - 4 + signed(word & 0xFFFC, 16)
        elif op == 63 and xo == 0:  # fcmpu
            field = (word >> 23) & 7
            for bit, value in enumerate((fp[a] < fp[rb], fp[a] > fp[rb], fp[a] == fp[rb], False)):
                flags[4 * field + bit] = value
        elif op == 63 and xo in (12, 40, 72):
            fp[d] = f32(fp[rb]) if xo == 12 else (-fp[rb] if xo == 40 else fp[rb])
        elif op in (59, 63):
            operation = (word >> 1) & 31
            if operation == 20:
                value = fp[a] - fp[rb]
            elif operation == 21:
                value = fp[a] + fp[rb]
            elif operation == 25:
                value = fp[a] * fp[rc]
            elif operation == 18:
                value = fp[a] / fp[rb]
            elif operation == 23 and op == 63:
                value = fp[rc] if fp[a] >= 0 else fp[rb]
            elif operation in (28, 29, 30, 31):
                value = fp[a] * fp[rc] + (fp[rb] if operation in (29, 31) else -fp[rb])
                if operation in (30, 31):
                    value = -value
            else:
                raise c.MappingError("Unsupported scalar floating opcode")
            fp[d] = f32(value) if op == 59 else value
        else:
            raise c.MappingError(f"Unsupported slice opcode at {pc - 4:08X}")
    else:
        raise c.MappingError("Scalar slice exceeded step limit")
    return {"fp": fp, "memory": memory, "trace": trace}


def extension_oracle(image, version, reference_y, rest_y, cap=.5):
    r3, r4 = 0x10000, 0x20000
    reference, rest, output = (1012, 876, 880) if version == "fm3" else (1028, 892, 896)
    result = scalar_slice(image, version, "extension", {3: r3, 4: r4}, {},
                          {r3 + reference: reference_y, r3 + rest: rest_y, r4 + 20: cap})
    return result["memory"][r3 + output]


def geometry_oracle(image, version, *, radius, height, minimum, maximum, slider, stock):
    config = 0x10000
    memory = {config + 2780: minimum, config + 2784: maximum,
              config + (10980 if version == "fm3" else 11328): slider,
              config + 11480: stock}
    result = scalar_slice(image, version, "geometry", {30: config, 18: 0x20000},
                          {1: f32(radius), 24: f32(height)}, memory)
    return {"reference": result["fp"][17], "selected": result["fp"][19]}


def rest_oracle(image, version, *, mass, front_rate, rear_rate, fraction, wheelbase, front_y, rear_y):
    vehicle, front, rear, front2, rear2 = 0x10000, 0x20000, 0x30000, 0x40000, 0x50000
    kf, kr = f32(front_rate * mass), f32(rear_rate * mass)
    zf, zr = f32((1 - fraction) * wheelbase), f32(-fraction * wheelbase)
    if version == "fm3":
        regs = {29: vehicle, 27: front, 24: front2, 26: rear, 23: rear2}
        memory = {vehicle + 224: mass, front + 1016: zf, front + 844: kf}
        fp = {8: f32(kr * rear_y), 9: kr, 10: f32(-zr * kr),
              12: s.HALF_GRAVITY, 18: rear_y, 19: front_y}
        output = 876
    else:
        regs = {28: vehicle, 26: front, 24: front2, 25: rear, 23: rear2}
        memory = {vehicle + 224: mass, front + 1032: zf, front + 860: kf}
        fp = {8: f32(kr * rear_y), 9: kr, 10: f32(-zr * kr),
              12: s.HALF_GRAVITY, 18: rear_y, 19: front_y}
        output = 892
    result = scalar_slice(image, version, "rest", regs, fp, memory)
    return {"front": result["memory"][front + output], "rear": result["memory"][rear + output]}


def micro_checks(images, samples=500):
    rng = random.Random(3042026)
    errors = {"geometry": [], "extension": [], "rest": []}
    for i in range(samples):
        height, radius = rng.uniform(.1, .8), rng.uniform(.15, .6)
        low, high, q = rng.uniform(.03, .12), rng.uniform(.13, .3), rng.random()
        for v in images:
            geometry = geometry_oracle(images[v], v, radius=radius, height=height,
                                       minimum=low, maximum=high, slider=q, stock=high)
            errors["geometry"] += [abs(geometry["reference"] - (radius - height - high)),
                                    abs(geometry["selected"] - (radius - height - low - (high - low) * q))]
        # Both sides of the helper's threshold and active/inactive FM4 caps.
        sag = ([0., -.01, .069999, .07, .070001, .093333, .1, .5][i]
               if i < 8 else rng.uniform(-.05, .8))
        ref, cap = rng.uniform(-.8, .5), rng.choice([.01, .05, .1, .5, 1.])
        rest = ref - sag
        for v in images:
            got = extension_oracle(images[v], v, ref, rest, cap)
            expected = s.extension_bound(f32(ref), f32(rest), f32(cap) if v == "fm4" else None)
            errors["extension"].append(abs(got - expected))
        mass, kf, kr = rng.uniform(3, 30), rng.uniform(20, 150), rng.uniform(20, 150)
        w, wb, yf, yr = rng.uniform(.05, .95), rng.uniform(1.5, 4), rng.uniform(-1, .5), rng.uniform(-1, .5)
        for v in images:
            got = rest_oracle(images[v], v, mass=mass, front_rate=kf, rear_rate=kr,
                              fraction=w, wheelbase=wb, front_y=yf, rear_y=yr)
            errors["rest"] += [abs(got["front"] - (yf - s.HALF_GRAVITY * w / kf)),
                               abs(got["rear"] - (yr - s.HALF_GRAVITY * (1 - w) / kr))]
    result = {k: {"checks": len(v), "maximum_absolute_error": max(v), "passed": max(v) <= 1e-6}
              for k, v in errors.items()}
    if not all(r["passed"] for r in result.values()):
        raise c.MappingError("Original-byte arithmetic check failed: " + str(result))
    return result


def export_evidence(out, images, re_root):
    out.mkdir()
    disassembler = OLD / "fm3/disasm-range.exe"
    sources = {}
    ranges = {
        "fm3": [(0x826B3F98, 0x826B41A8), (0x82729458, 0x8272957C),
                (0x82729E1C, 0x82729F04), (0x82728010, 0x82728054)],
        "fm4": [(0x828A60C0, 0x828A61AC), (0x828A0768, 0x828A09D8),
                (0x8281EC20, 0x8281ECCC), (0x8281F588, 0x8281F678), (0x8281AC40, 0x8281AC9C)],
    }
    for v, items in ranges.items():
        for lo, hi in items:
            data = images[v][lo - 0x82000000:hi - 0x82000000]
            key = f"{v}-{lo:08X}-{hi:08X}"
            text = subprocess.check_output([str(disassembler), str(IMAGES[v]), "0x82000000", hex(lo), hex(hi)], text=True)
            (out / (key + ".asm.txt")).write_text(text, encoding="utf-8")
            sources[key] = {"start": hex(lo), "end_exclusive": hex(hi), "sha256": hashlib.sha256(data).hexdigest()}
    asm_path = re_root / "out/db/asm.json"
    asm = json.loads(asm_path.read_text())
    # Match the RE assembly listing to independent disassembly of original bytes.
    checked = {}
    for addr in (0x828A0768, 0x828A6078, 0x8281EBA0, 0x8281AC40):
        listing = asm[f"sub_{addr:08X}"]
        raw = subprocess.check_output([str(disassembler), str(IMAGES["fm4"]), "0x82000000",
                                       hex(addr), hex(addr + 4 * len(listing))], text=True)
        original = [" ".join(line.split()[1:]).lower() for line in raw.splitlines()]
        expected = [" ".join(line.split()).lower() for line in listing]
        if original != expected:
            raise c.MappingError(f"FM4-re assembly mismatch for {addr:08X}")
        checked[hex(addr)] = len(listing)
    constants = {}
    for v, addresses in {
        "fm3": [0x820D93A4, 0x820D93A8, 0x820D9410],
        "fm4": [0x820CF8C8, 0x820CF8CC, 0x820CFA90],
    }.items():
        values = [struct.unpack_from(">f", images[v], a - 0x82000000)[0] for a in addresses]
        if values != [s.EXTENSION_THRESHOLD, s.EXTENSION_SCALE, s.HALF_GRAVITY]:
            raise c.MappingError("Changed setup constants")
        constants[v] = dict(zip(map(hex, addresses), values))
    c.dump(out / "provenance.json", {
        "images": {v: {"path": str(IMAGES[v]), "sha256": IMAGE_HASHES[v]} for v in images},
        "ranges": sources, "constants": constants, "fm4_re_listing": str(asm_path),
        "fm4_re_listing_sha256": c.sha(asm_path), "matched_instructions_per_function": checked,
        "ghidra_patched_pseudocode_used_as_numeric_evidence": False,
        "guest_code_executed": False})


def run_benchmark(out, rules, previous, images):
    out.mkdir()
    records = []
    for index, (media, _) in enumerate(b.SELECTION + [(c.MEDIA, "Toyota")]):
        dest = out / media
        converted = c.run(c.FM3_DEFAULT, c.FM4_DEFAULT, dest, media=media,
                          id_base=c.ID_BASE + 1000 * index, calibration_rules=rules,
                          calibration_mode="conservative", code_semantics=True)
        load = lambda name: json.loads((dest / name).read_text(encoding="utf-8"))
        source, candidate = load("source_ir.json"), load("candidate_ir.json")
        audit, eff = load("code_semantics.json"), load("effective_comparison.json")
        old = json.loads((previous / media / "candidate_ir.json").read_text())
        old_comparison = json.loads((previous / media / "comparison.json").read_text())
        changes = []
        for m in load("mapping.json")["columns"]:
            if m["action"] in ("allocate_primary_key", "remap_reference"):
                continue
            role, col = m["role"], m["target_column"]
            a, z = old["nodes"][role]["row"][col], candidate["nodes"][role]["row"][col]
            if a != z:
                if (role, col) not in {("car", "FrontStockRideHeight"), ("car", "RearStockRideHeight"),
                                      (cs.WEIGHT, "CMHeight")}:
                    raise c.MappingError("Unexpected benchmark mutation")
                changes.append({"role": role, "column": col, "before": a, "after": z})
        checks = []
        h = s.row(source, cs.WEIGHT)["CMHeight"]
        target_inputs = cs.inputs(candidate, "fm4")
        cg = cs.run_cg_instruction_slice(images["fm4"], 0x82000000,
                                         height=target_inputs["height"], distribution=target_inputs["distribution"],
                                         front=target_inputs["front_height"], rear=target_inputs["rear_height"])
        cg_error = cg["config_cmheight"] - h
        if abs(cg_error) > 1e-6:
            raise c.MappingError("Emitted CMHeight failed original-byte check")
        c.dump(dest / "cg_binary_check.json", {**cg, "source_height": h, "error": cg_error})
        for axle, info in audit["suspension"]["axles"].items():
            spring = s.row(source, "spring." + axle)
            for q in (0., .5, 1.):
                # Actual radius is intentionally not asserted. Test scalar inputs
                # with a common supplied radius and retain this limitation.
                geo3 = geometry_oracle(images["fm3"], "fm3", radius=.35, height=h,
                                       minimum=spring["MinRideHeight"], maximum=spring["MaxRideHeight"],
                                       slider=q, stock=0)
                geo4 = geometry_oracle(images["fm4"], "fm4", radius=.35, height=cg["config_cmheight"],
                                       minimum=spring["MinRideHeight"], maximum=spring["MaxRideHeight"],
                                       slider=q, stock=info["target_stock_height"])
                for rate in (spring["MinSpringRate"], info["effective_default_spring_rate"], spring["MaxSpringRate"]):
                    sag = s.HALF_GRAVITY * info["axle_fraction"] / rate
                    ref = geo4["selected"]
                    bound3 = extension_oracle(images["fm3"], "fm3", ref, ref - sag)
                    bound4 = extension_oracle(images["fm4"], "fm4", ref, ref - sag, info["retained_max_stretch"])
                    checks.append({"axle": axle, "ride_slider": q, "spring_rate": rate,
                                   "geometry_max_error": max(abs(geo4[k] - geo3[k]) for k in geo3),
                                   "extension_error": bound4 - bound3})
        if any(r["geometry_max_error"] > 1e-6 or abs(r["extension_error"]) > 1e-6 for r in checks):
            raise c.MappingError("Per-car original-byte check failed: " + media)
        c.dump(dest / "suspension_binary_checks.json", checks)
        record = {"car": media, "validation_passed": converted["validation_passed"],
                  "old_geometry": s.compare_geometry(source, old),
                  "new_geometry": eff["suspension_geometry_vs_source"],
                  "center_preserved": eff["centers"]["source_preserved_within_tolerance"],
                  "coefficients": eff["suspension_vs_source"]["counts"],
                  "axles": audit["suspension"]["axles"], "changes": changes,
                  "cg_binary_error": cg_error,
                  "binary_checks": len(checks),
                  "old_native_physics_differences": old_comparison["differences_by_category"].get("physics", 0),
                  "new_native_physics_differences": converted["differences"].get("physics", 0)}
        records.append(record)
        print(json.dumps({"car": media, "progress": index + 1, "changed_fields": len(changes)}), flush=True)
    summary = {
        "cars": len(records), "structural_validation_passed": sum(r["validation_passed"] for r in records),
        "geometry_preserved_before": sum(r["old_geometry"]["preserved"] for r in records),
        "geometry_preserved_after": sum(r["new_geometry"]["preserved"] for r in records),
        "center_preserved": sum(r["center_preserved"] for r in records),
        "normalized_coefficients_equal": sum(r["coefficients"]["equal"] for r in records),
        "normalized_coefficients_compared": sum(r["coefficients"]["compared"] for r in records),
        "cars_changed": sum(bool(r["changes"]) for r in records),
        "extension_caps_proven_nonbinding_for_selected_part_ranges": 2 * len(records),
        "minimum_cap_slack": min(a["cap_slack"] for r in records for a in r["axles"].values()),
        "binary_checks_passed": sum(r["binary_checks"] for r in records),
        "cg_binary_checks_passed": len(records),
        "max_cg_binary_absolute_error": max(abs(r["cg_binary_error"]) for r in records),
        "panel_native_physics_differences_before": sum(r["old_native_physics_differences"] for r in records[:30]),
        "panel_native_physics_differences_after": sum(r["new_native_physics_differences"] for r in records[:30]),
        "reused_panel": True, "runtime_tested": False, "independent_test_set": False,
    }
    c.dump(out / "results.json", records)
    c.dump(out / "summary.json", summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--re-root", type=Path, default=Path("I:/FM4-re"))
    parser.add_argument("--rules", type=Path, default=ROOT / "outputs/fm-car-converter/benchmark30-refinements-v1/rules.json")
    parser.add_argument("--previous", type=Path, default=OLD / "benchmark31")
    args = parser.parse_args()
    out = args.out.resolve()
    if out.exists():
        parser.error("Choose a new output directory")
    for source in (c.FM3_DEFAULT, c.FM4_DEFAULT):
        game_root = source.resolve().parents[2]
        if out == game_root or game_root in out.parents:
            parser.error("Output must be outside game directories")
    before = {str(p): c.sha(p) for p in (c.FM3_DEFAULT, c.FM4_DEFAULT, *IMAGES.values())}
    images = load_images()
    out.mkdir(parents=True)
    export_evidence(out / "evidence", images, args.re_root)
    c.dump(out / "micro_checks.json", micro_checks(images))
    summary = run_benchmark(out / "benchmark31", args.rules, args.previous, images)
    after = {path: c.sha(path) for path in before}
    if before != after:
        raise c.MappingError("Source changed during audit")
    c.dump(out / "manifest.json", {
        "sources_before": before, "sources_after": after, "sources_unchanged": True,
        "rules_sha256": c.sha(args.rules),
        "code_sha256": {p.name: c.sha(p) for p in Path(__file__).parent.glob("*.py")},
        "outputs": {str(p.relative_to(out)): c.sha(p) for p in out.rglob("*") if p.is_file()},
        "runtime_tested": False})
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
