"""CPU-only material/dependency and legacy cockpit validation.

Standard FM4 car effects (race/UI, LOD0..5) only. This is a structural audit,
not proof of lighting, animation, or rendered appearance.
SPDX-License-Identifier: GPL-3.0-only
"""
from collections import Counter
import hashlib
import math
from pathlib import Path
import re
import struct
import xml.etree.ElementTree as ET
import zipfile

import archive_cpu
import carbin_audit
import effect_audit
import driver_audit
import granny_audit
import sampler_audit


class AppearanceError(ValueError):
    pass


IMAGE_SHA256 = "7a56b178d856c0dabb6d32120de6b5b6d7182a0c35bff836763d08684e3d5c41"
# Original executable functions, checked against FM4-re assembly and raw image.
EVIDENCE = {
    "material_mapping": "0x828F9C30", "tire_predicate": "0x828ECCD8",
    "rim_predicate": "0x828ECE18", "attribute_reader": "0x82903B80",
    "hands_auto_offset": "0x828E57A0", "hands_transform": "0x828DB660",
}
COCKPIT_PARTS = ("interior", "seat", "steering_wheel", "speed", "fuel", "boost",
                 "oiltemp", "oilpressure", "watertemp", "volt", "gaugea",
                 "gaugeb", "gaugec", "gauged", "gaugee", "gaugef", "power",
                 "doorcard", "tach", "boot")
WHEEL_PREFIXES = ("tire", "dropShadowTire", "sidewall", "tread", "scaling_text",
                  "wheel_black", "rim", "ghostRim", "inner_rim", "outer_rim",
                  "chrome_rim", "chrome_blur_rim", "chrome_blur_lip",
                  "wheel_emblem", "blur_rim", "blur_lip", "dropShadowRim",
                  "geoShadowRim")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def xml(data):
    # Retail texture definitions contain bare '&' in loadFlags expressions.
    return ET.fromstring(re.sub(rb"&(?!amp;|lt;|gt;|quot;|apos;|#\d+;|#x[0-9a-fA-F]+;)",
                               b"&amp;", data))


def technique(part, material, lod, detailed=True):
    """Standard (non-SuperLOD) branch of the retail material-name mapper."""
    part = part.casefold()
    for brake in ("rotor", "caliper"):
        if brake in part:
            exceptions = ("ghost", "geoshadowbrake", "shadowmap", "dropshadowbrake", "brake_badge")
            return material if any(s in material.casefold() for s in exceptions) else brake
    if lod == 0 and detailed and any(s in part for s in COCKPIT_PARTS):
        return "cockpit_" + material
    wheel = (material.startswith(WHEEL_PREFIXES)
             or any(s in material for s in ("ghostTire", "geoShadowTire", "tire_", "sidewall", "tread", "rim_")))
    if not (lod == 0 and detailed) and wheel:
        return material + "_V2"
    if part in ("glassf", "lexanf") and material in ("window", "window_2"):
        return "front" + material
    return material


def load_flags(expression, flags):
    """Parse the conjunction/negation form used by retail texture definitions."""
    if not expression:
        return True
    result = True
    for term in expression.split("&"):
        term = term.strip()
        if not re.fullmatch(r"!?[A-Za-z0-9]+", term) or term.lstrip("!") not in flags:
            raise AppearanceError(f"Unreviewed texture load flags: {expression}")
        value = flags[term.lstrip("!")]
        result &= not value if term.startswith("!") else value
    return result


def driver_attributes(data):
    root = xml(data)
    if root.tag != "CarAttributes" or root.get("Version") != "15":
        raise AppearanceError("Only reviewed legacy CarAttributes version 15 is supported")
    driver = root.find("Driver")
    if driver is None or driver.get("Version") != "6":
        raise AppearanceError("Expected reviewed driver attributes version 6")
    for node in (driver, root.find("DriverHandsOffset"), root.find("DriverHandsScale"),
                 root.find("CockpitNearPlane"), root.find("CockpitShadowScale"),
                 root.find("DriverHandsSteeringWheelOverride"), root.find("SteeringWheelAngleOverride")):
        if node is None or not all(math.isfinite(float(v)) for v in node.attrib.values()):
            raise AppearanceError("Missing/nonfinite driver or cockpit attribute")
    for node, attr in ((driver, "BodyScale"), (root.find("DriverHandsScale"), "value"),
                       (root.find("CockpitNearPlane"), "value")):
        if float(node.get(attr, "0")) <= 0:
            raise AppearanceError("Driver scale or cockpit near plane must be positive")
    gauges = root.find("Gauges")
    if gauges is None or [g.tag for g in gauges] != ["Speed", "Tach", "Fuel", "Boost"]:
        raise AppearanceError("Unreviewed legacy gauge layout")
    counts = {}
    for gauge in gauges:
        ticks = [(float(t.attrib["Param"]), float(t.attrib["Value"])) for t in gauge]
        if len(ticks) != int(gauge.attrib["NumTicks"]):
            raise AppearanceError("Gauge tick count mismatch")
        if any(not all(math.isfinite(x) for x in t) for t in ticks):
            raise AppearanceError("Nonfinite gauge tick")
        if any(ticks[i][1] >= ticks[i+1][1] for i in range(len(ticks)-1)):
            raise AppearanceError("Gauge input values are not strictly increasing")
        counts[gauge.tag] = len(ticks)
    offset = [float(root.find("DriverHandsOffset").attrib["value."+a]) for a in "xyz"]
    return {"car_attributes_version": 15, "driver_version": 6, "gauge_tick_counts": counts,
            "hands_offset": offset, "hands_auto_offset": all(x == 0 for x in offset),
            "body_scale": float(driver.attrib["BodyScale"]),
            "near_plane": float(root.find("CockpitNearPlane").attrib["value"]),
            "source_attributes_preserved": True}


def rig(model):
    if model["type"] != 2:
        raise AppearanceError("Cockpit must use the body header")
    header = model["header"]
    shift = carbin_audit.u32(header, 0x160)*140
    values = {}
    for name, offset in (("left_grip", 0x1c8), ("right_grip", 0x1d8),
                         ("steering_pivot", 0x228), ("steering_axis", 0x238),
                         ("driver_rest", 0x248), ("shifter", 0x258)):
        vector = struct.unpack_from(">4f", header, offset+shift)
        if not all(math.isfinite(x) for x in vector):
            raise AppearanceError(f"Nonfinite cockpit {name}")
        values[name] = list(vector)
    axis_length = math.sqrt(sum(x*x for x in values["steering_axis"][:3]))
    if abs(axis_length-1) > 0.001:
        raise AppearanceError("Cockpit steering axis is not unit length")
    wheel = [s for s in model["sections"] if s["name"].casefold() == "steering_wheel"]
    if len(wheel) != 1 or wheel[0]["lod0"]["count"] == 0:
        raise AppearanceError("Missing cockpit steering-wheel geometry")
    values.update(steering_axis_length=axis_length,
                  pivot_to_section_origin_m=math.dist(values["steering_pivot"][:3], wheel[0]["bounds"][:3]),
                  steering_wheel_vertices=wheel[0]["lod0"]["count"])
    return values


def audit(source, target, target_root, media, wheel, archive_read):
    """Validate an already geometry/texture-audited payload before packaging."""
    target_root = Path(target_root)
    lookup = {p.as_posix().casefold(): b for p, b in target.items()}
    car = f"Media/Cars/{media}/".casefold()
    wheel_root = f"Media/Wheels/{wheel}/".casefold()
    for filename in ("carattribs.xml", "shadersettings.xml"):
        old = next((b for p, b in source.items() if p.as_posix().casefold() == car+filename), None)
        if old is None or old != lookup.get(car+filename):
            raise AppearanceError(f"Source {filename} was not preserved")
    driver = driver_attributes(lookup[car+"carattribs.xml"])
    overrides = xml(lookup[car+"shadersettings.xml"])
    inputs, libraries = {}, {}
    for mode, filename in (("race", "shaders_v16.fxobj"), ("ui", "shaders_ui_v16.fxobj")):
        path = target_root/"Shaders/Cars"/filename
        data = path.read_bytes()
        inputs[str(path)] = sha(data)
        libraries[mode] = effect_audit.read_effect(data)

    shared_path, driver_path = target_root/"Cars/Shared.zip", target_root/"Cars/Driver.zip"
    for path in (shared_path, driver_path, target_root/"zipmanifest.xml"):
        inputs[str(path)] = sha(path.read_bytes())
    decoder = archive_cpu.decoder_path()
    inputs[str(decoder)] = sha(decoder.read_bytes())
    if inputs[str(decoder)] != archive_cpu.DECODER_SHA256:
        raise AppearanceError("Unreviewed CPU archive decoder")
    mounts = {n.attrib["path"].replace("\\", "/").casefold()
              for n in xml((target_root/"zipmanifest.xml").read_bytes()).findall("Zip")}
    for name in ("shared", "driver"):
        if f"game:/media/cars/{name}.zip" not in mounts:
            raise AppearanceError(f"Native {name} archive is not mounted")
    with zipfile.ZipFile(driver_path) as z:
        entries = {n.casefold(): n for n in z.namelist() if not n.endswith("/")}
        for required in ("driverlod0.gr2", "hands.gr2", "driver.anim.bin", "driver01.skinbin", "driver02.skinbin"):
            if required not in entries:
                raise AppearanceError(f"Missing native driver dependency: {required}")
        driver_payloads = {n: archive_read(z, n) for n in sorted(entries.values())}
        driver_files = [{"path": n, "sha256": sha(b)} for n, b in driver_payloads.items()]
        driver_animation = driver_audit.audit(lookup[car+"carattribs.xml"], driver_payloads)
        decoder = granny_audit.decoder_path()
        inputs[str(decoder)] = sha(decoder.read_bytes())

    bindings, rows, undeclared, checked_overrides = {}, [], set(), []
    with zipfile.ZipFile(shared_path) as shared:
        names = {n.casefold(): n for n in shared.namelist()}
        definitions = xml(archive_read(shared, names["textures.xml"]))
        settings = [xml(archive_read(shared, names["shadersettings/"+n+".xml"]))
                    for n in ("normal", "metallic", "ui")]
        for node in overrides:
            for parameter in node:
                for mode, effects in libraries.items():
                    if node.tag not in effects or parameter.tag not in effects[node.tag]["constants"]:
                        raise AppearanceError(f"Unknown {mode} material override: {node.tag}/{parameter.tag}")
                if not parameter.attrib or not all(math.isfinite(float(v)) for v in parameter.attrib.values()):
                    raise AppearanceError("Nonfinite/empty material override")
                checked_overrides.append({"technique": node.tag, "parameter": parameter.tag, **parameter.attrib})

        def dependency(root, name):
            key = (root + name).casefold()
            if key not in bindings:
                if root == "Shared/":
                    if name.casefold() not in names:
                        raise AppearanceError(f"Missing shared texture: {name}")
                    data = archive_read(shared, names[name.casefold()])
                else:
                    if key not in lookup:
                        raise AppearanceError(f"Missing local texture: {key}")
                    data = lookup[key]
                bindings[key] = {"path": root+name, "bytes": len(data), "sha256": sha(data)}
            return key

        for path, data in sorted(target.items()):
            if path.suffix.lower() != ".carbin":
                continue
            model = carbin_audit.parse(data, "FM4")
            if path.stem.casefold() == media.casefold()+"_cockpit":
                driver["rig"] = rig(model)
            for section in model["sections"]:
                for mesh in section["meshes"]:
                    name = technique(section["name"], mesh["name"], mesh["lod"])
                    samplers = set()
                    for mode, effects in libraries.items():
                        if name not in effects:
                            raise AppearanceError(f"Missing {mode} technique: {path.name}/{section['name']}/{name}")
                        samplers.update(effects[name]["samplers"])
                    configured = {n.tag for setting in settings for n in setting.findall(name+"/*")}
                    configured.update(n.tag for n in overrides.findall(name+"/*"))
                    flags = {"SuperLOD": False, "Cockpit": mesh["lod"] == 0,
                             "LOD0": mesh["lod"] == 0, "LOD15": mesh["lod"] != 0,
                             "InGameTextures": True, "CarCommon": True}
                    deps = set()
                    for sampler in sorted(samplers):
                        definition = definitions.find(sampler)
                        if definition is None:
                            # Global/atlas resources are not XML file bindings.
                            undeclared.add(sampler)
                            continue
                        if sampler not in configured:
                            # Shared PS programs may declare resources unused by
                            # this technique's settings (e.g. emblem/Badge2Sampler).
                            continue
                        for texture in definition:
                            if not load_flags(texture.get("loadFlags", ""), flags):
                                continue
                            root = {"%CARFOLDER%": car, "%WHEELFOLDER%": wheel_root,
                                    "%SHAREDCARFOLDER%": "Shared/"}.get(texture.get("searchPath"))
                            if root is None:
                                raise AppearanceError("Unknown texture search path")
                            deps.add(dependency(root, texture.attrib["value"]))
                    rows.append({"model": path.as_posix(), "part": section["name"],
                                 "material": mesh["name"], "lod": mesh["lod"],
                                 "technique": name, "file_bindings": sorted(deps)})
        # Atlas slots are set by the loader, not textures.xml. Require both car
        # resolutions and every standard wheel colour variant; don't infer a
        # wheel atlas from the car's baseSampler name.
        for name in ("nodamage", "damage"):
            for suffix in ("", "_lod0"):
                dependency(car, name+suffix+".xds")
        for name in ("wheel.xds", "wheel_lod0.xds"):
            dependency(wheel_root, name)
        for path in source:
            if path.parent.as_posix().casefold()+"/" == wheel_root and re.fullmatch(
                    r"wheel[0-3](?:_lod0)?\.xds", path.name, re.I):
                dependency(wheel_root, path.name)
        samplers = sampler_audit.audit(libraries, rows, dependency, car, wheel_root,
                                        {n.tag for n in definitions})
    if "rig" not in driver:
        raise AppearanceError("Missing cockpit model")
    for path, digest in inputs.items():
        if sha(Path(path).read_bytes()) != digest:
            raise AppearanceError(f"Native dependency changed during audit: {path}")
    return {"passed": True, "cpu_only": True, "runtime_tested": False,
            "scope": "Standard LOD0..5 effect/sampler metadata, texture files, legacy rig and native hand animation data",
            "excluded": ["Shader execution/lighting", "Pose and animation playback",
                         "SuperLOD/Autovista", "Runtime global sampler binding"],
            "evidence": EVIDENCE, "original_image_sha256": IMAGE_SHA256,
            "inputs": inputs, "mesh_count": len(rows),
            "techniques": dict(sorted(Counter(r["technique"] for r in rows).items())),
            "meshes": rows, "texture_dependencies": list(bindings.values()),
            "samplers_without_xml_file_binding": sorted(undeclared),
            "sampler_validation": samplers, "driver_animation_validation": driver_animation,
            "material_overrides": checked_overrides, "driver": driver,
            "archive_validation": "Native driver files decoded on CPU; every ZIP size and CRC verified",
            "native_driver_assets": driver_files}
