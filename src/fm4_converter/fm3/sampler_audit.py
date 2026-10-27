"""Offline sampler register/resource audit from FM4 original loader evidence.

No shader execution. Keep handle discovery separate from proven resource binds,
and leave unresolved global state explicit.
SPDX-License-Identifier: GPL-3.0-only
"""
from collections import Counter


class SamplerError(ValueError):
    pass


# 828F3D98 caches these handles; 828F3238 binds the per-car resources.
GLOBAL_RESOURCES = {
    "mirrorSamplerDefault": (156, 15152),
    "mirrorSamplerRearSuper": (160, 15184),
    "mirrorSamplerLeftSuper": (164, 15216),
    "mirrorSamplerRightSuper": (168, 15248),
    "windshieldReflectionSampler": (172, 15284),
    "windshieldReflectionDepthSampler": (176, 15316),
    "digitalGaugeSampler": (180, 15348),
    "ambientCubemapSampler": (184, 15380),
    "blurredCubemapSampler": (188, 15412),
    "specularCubemapSampler": (192, 15444),
    "shLookupCubemapSampler": (196, 15476),
    "envSampler": (204, 15024),
    "envStaticSampler": (208, 15056),
    "envBackgroundSampler": (212, 15088),
    "lightsNormalSampler": (216, 15120),
}
HANDLE_ONLY = {"s_shadowMapNear": 280, "s_shadowMapFar": 284, "s_varianceShadowMap": 288}
EVIDENCE = {
    "sampler_handles": "0x828F3D98", "texture_bind_wrapper": "0x8285ED08",
    "effect_texture_assignment": "0x822E2CE8", "car_global_resources": "0x828F3238",
    "wheel_resources": "0x828F5BA8", "wheel_atlas_loader": "0x828FBB38",
    "tire_atlas_loader": "0x828FE2E8",
    "atlas_lod_binding": ["0x828F70A0", "0x828F7288", "0x828F7B50"],
}


def registers(effect):
    rows = []
    for index, shader_pass in enumerate(effect["passes"]):
        for stage in ("vertex", "pixel"):
            shader = shader_pass[stage]
            if shader is None:
                continue
            occupied = {}
            for c in shader["constants"]:
                if not c["sampler"]:
                    continue
                first, count = c["register"], c["register_count"]
                if count <= 0 or first < 0 or first + count > 16:
                    raise SamplerError("Invalid compiled sampler register range")
                for slot in range(first, first + count):
                    if slot in occupied:
                        raise SamplerError("Overlapping compiled sampler registers")
                    occupied[slot] = c["name"]
                rows.append({"pass_index": index, "pass_name": shader_pass["name"],
                             "stage": stage, "sampler": c["name"],
                             "register": first, "register_count": count})
    return rows


def audit(libraries, meshes, dependency, car, wheel, xml_sampler_names):
    """Check every compiled pass, then check loader-owned atlas dependencies.

    Tire a/b/c are conditional on the tire category (<=1, ==2, >2).
    Check all three native branches without guessing a category from geometry.
    """
    slots, bindings, unresolved = {}, {}, set()
    for mode, effects in libraries.items():
        for name in sorted({row["technique"] for row in meshes}):
            slots[f"{mode}/{name}"] = registers(effects[name])
    for row in meshes:
        wheel_model = row["model"].casefold().startswith(wheel)
        family = "wheel" if wheel_model else "car"
        key = f"{family}/lod{row['lod']}/{row['technique']}"
        if key in bindings:
            continue
        samplers = {s for effects in libraries.values()
                    for s in effects[row["technique"]]["samplers"]}
        values = {}
        for name in sorted(samplers):
            if name in ("baseSampler", "damageSampler"):
                if name == "baseSampler" and wheel_model:
                    roots, atlas = wheel, "wheel"
                else:
                    roots, atlas = car, "damage" if name == "damageSampler" else "nodamage"
                primary = atlas + ("_lod0" if row["lod"] == 0 else "") + ".xds"
                files = [dependency(roots, primary)]
                if row["lod"] == 0:
                    files.append(dependency(roots, atlas + ".xds"))
                values[name] = {"owner": family, "kind": "atlas",
                                "files": files, "lod0_fallback_to_low": row["lod"] == 0}
            elif name in {f"blurRimSampler{i}" for i in (1, 2, 3, 4)}:
                index = int(name[-1])-1
                values[name] = {"owner": "wheel", "kind": "atlas",
                                "material_handle_offset": 236+4*index,
                                "resource_offset": 192+32*index,
                                "files": [dependency(wheel, f"wheel{index}.xds")]}
            elif name == "blurTireSampler" or name in {f"blurTireSampler{i}" for i in (2, 3, 4)}:
                index = 0 if name == "blurTireSampler" else int(name[-1])-1
                values[name] = {"owner": "native_shared_tire", "kind": "conditional_atlas",
                                "material_handle_offset": 220+4*index,
                                "resource_offset": 32+32*index,
                                "files": [dependency("Shared/", f"tire{c}{index}.xds") for c in "abc"],
                                "condition": "tire category <=1: a; ==2: b; >2: c"}
            elif name in GLOBAL_RESOURCES:
                handle, resource = GLOBAL_RESOURCES[name]
                if wheel_model and name in ("envSampler", "envStaticSampler"):
                    resource = 1656 if name == "envSampler" else 1688
                values[name] = {"kind": "engine_resource", "material_handle_offset": handle,
                                "resource_offset": resource, "runtime_value_verified": False}
            elif name in xml_sampler_names:
                values[name] = {"kind": "xml_settings",
                                "note": "Configured file paths checked separately by appearance audit"}
            elif name in HANDLE_ONLY:
                values[name] = {"kind": "handle_only", "material_handle_offset": HANDLE_ONLY[name],
                                "runtime_value_verified": False}
                unresolved.add(name)
            else:
                values[name] = {"kind": "unresolved_global", "runtime_value_verified": False}
                unresolved.add(name)
        bindings[key] = values
    return {"passed": True, "scope": "Compiled sampler registers and standard loader atlas dependencies",
            "evidence": EVIDENCE, "technique_mode_count": len(slots),
            "sampler_register_records": sum(len(v) for v in slots.values()),
            "registers": slots, "bindings": bindings,
            "binding_kinds": dict(Counter(v["kind"] for b in bindings.values() for v in b.values())),
            "unresolved_runtime_resources": sorted(unresolved), "runtime_binding_tested": False}
