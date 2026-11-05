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

from . import archive_cpu
from . import carbin_audit
from . import effect_audit
from . import driver_audit
from . import granny_audit
from . import sampler_audit


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


def drop_unmatched_closing_tags(data):
    """(bytes, removed tags) of an XML document whose only fault is closing tags without an
    opening one (FM3 CAD_8_CTSV_08 shadersettings.xml has a stray `</tail_light>`).

    Well-formed input is returned unchanged; anything else that still fails raises."""
    try:
        xml(data)
        return data, []
    except ET.ParseError:
        pass
    text = data.decode("utf-8")
    stack, drop = [], []
    for m in re.finditer(r"<(/?)([A-Za-z_][\w.:-]*)[^>]*?(/?)>", text):
        closing, name, empty = m.group(1), m.group(2), m.group(3)
        if empty or m.group(0).startswith(("<?", "<!")):
            continue
        if not closing:
            stack.append(name)
        elif stack and stack[-1] == name:
            stack.pop()
        elif name not in stack:
            drop.append(m)
        else:
            raise AppearanceError(f"Unrepairable XML nesting at </{name}>")
    for m in reversed(drop):
        # The whole line when the stray tag stands alone on it.
        start = text.rfind("\n", 0, m.start()) + 1
        end = text.find("\n", m.end())
        end = len(text) if end < 0 else end + 1
        if text[start:m.start()].strip() or text[m.end():end].strip():
            start, end = m.start(), m.end()
        text = text[:start] + text[end:]
    repaired = text.encode("utf-8")
    xml(repaired)
    return repaired, [m.group(0) for m in drop]


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


# Legacy layouts FM4 itself ships in Disc 1 Media/Cars (count of native cars,
# 2 November 2026): (CarAttributes, Driver) version -> elements every native
# file of that version has, and the gauge layout. Version 4 predates the
# cockpit/hands block; 10/11 keep gauges at the top level. Native race cars
# without carattribs.xml (FOR_5_FGFalcon_11, MER_1_CClass_11) also exist.
_COCKPIT = ("DriverHandsOffset", "DriverHandsScale", "CockpitNearPlane", "CockpitShadowScale",
            "DriverHandsSteeringWheelOverride", "SteeringWheelAngleOverride")
NATIVE_LAYOUTS = {
    ("4", "5"): ((), None), ("4", "6"): ((), None),
    ("10", "6"): (_COCKPIT, ["Speed", "Tach", "Fuel"]),
    ("11", "6"): (_COCKPIT, ["Speed", "Tach", "Fuel", "Boost"]),
    **{(v, "6"): (_COCKPIT, "Gauges") for v in ("12", "13", "14", "15")},
}


# Car-folder textures some native FM4 cars omit although they use the technique
# (Disc 1 scan, 2 November 2026); the game runs those cars, so their absence
# is accepted for these exact pairs and recorded.
ABSENT_TEXTURE_PRECEDENT = {
    ("cockpit_bump_plastic2", "plastic2_nrm.xds"): "AST_One77_10, MER_SLR_05, PEU_308RCZ_10, PON_FirebirdTransAm_69",
    ("cockpit_bump_leather2", "leather2_nrm.xds"): "CAD_CTSV_09, CHE_CobaltSS_10, FER_360_99, MAZ_RX7SpiritR_02",
    ("cockpit_bump_plastic3", "plastic3_nrm.xds"): "FER_599_06",
    ("cockpit_wood", "wood.xds"): "MER_SLSAMG_11",
}


# Mapped technique names FM4's own cars use although its effects lack them
# (Disc 1 scan, 2 November 2026). The game draws those cars, so a mesh with
# exactly such a name is accepted and listed; any other unknown name is not.
NATIVE_UNKNOWN_TECHNIQUES = {
    "Material__1": "TVR_Sagaris_05 wheel LOD0",
    "cockpit_Tail_light_lod0": "CHE_CamaroSS_10 interior LOD0",
    # FM3 sources whose material has no FM4 effect technique. FM4's own cars above show a
    # mesh with an unknown technique name loads and races; these three are each checked
    # in game before acceptance (docs/fm3-acceptance.md, M3/M4).
    "body2": "as Material__1; FM3 FER_71_F430GT_08 bumperFa",
    "LOD1": "as Material__1; FM3 TOY_35_Supra_04 bumperFrameF",
    "bump_plastic": "as Material__1; FM3 PON_GTO_68 wheel LOD3",
    "bump_stitching": "as Material__1; FM3 PON_GTO_68 wheel",
    "leather": "as Material__1; FM3 PON_GTO_68 wheel",
    "bump_leather": "as Material__1; FM3 PON_GTO_68 wheel",
}


# FM4's cockpit effects multiply the interior texture by a paint-scale constant;
# a car without a setting gets the global default of Shared.zip
# ShaderSettings/Normal.xml (0.5 for plastic/leather/cloth, 0.002 for metal...),
# else the effect initializer 1.0. FM3's effects have no such constant. On the
# 117 cars both games ship, FM4 shows a cockpit material at about 0.38x the
# default times its FM3 texture albedo, through darker textures or lower
# settings: median of (FM4 albedo x setting or default) / FM3 albedo, linear
# luminance at the mesh's LOD0 vertex UVs
# (outputs/fm-car-converter/cockpit-paint-v1/ratio_all.py). FM3 textures at the
# default render flat white (SRT4 ACR, the FM4 port of an FM3 car, sets 0.108 for
# plastic). Medians of >= 20 cars; the rest take default x 0.382, the pooled
# non-metal ratio. Not set: cockpit_body (car paint), cockpit_shadowMap, and
# techniques no shared car uses (listed in the record).
COCKPIT_PAINT_SCALES = {
    "cockpit_plastic": ("CockpitPlasticPaintScale", 0.169),
    "cockpit_mottled": ("CockpitPlasticPaintScale", 0.137),
    "cockpit_gauge_emissive": ("CockpitPlasticPaintScale", 0.416),
    "cockpit_badge": ("PaintScale", 0.208),
    "cockpit_cloth": ("PaintScale", 0.206),
    "cockpit_leather": ("PaintScale", 0.220),
    "cockpit_metal": ("PaintScale", 0.002),
    "cockpit_reflector": ("PaintScale", 0.398),
    "cockpit_rubber": ("PaintScale", 0.159),
    "cockpit_solid": ("PaintScale", 0.153),
    "cockpit_stitching": ("PaintScale", 0.191),
    "cockpit_wood": ("PaintScale", 0.096),
    "cockpit_bump_leather": ("CockpitPaintScale", 0.183),
    "cockpit_bump_leather2": ("CockpitPaintScale", 0.216),
    "cockpit_bump_leather3": ("CockpitPaintScale", 0.191),
    "cockpit_bump_plastic": ("CockpitPaintScale", 0.113),
    "cockpit_bump_plastic2": ("CockpitPaintScale", 0.187),
    "cockpit_bump_plastic3": ("CockpitPaintScale", 0.115),
}
UNMEASURED_PAINT_TECHNIQUES = ("cockpit_metal2", "cockpit_smooth_metal")


def cockpit_paint_settings(settings, techniques):
    """Source shadersettings.xml plus FM4 paint scales for `techniques`.

    Source text and values are kept; a technique the source already scales is
    left alone. Returns (bytes or None, added, unmeasured)."""
    wanted = [(t, *COCKPIT_PAINT_SCALES[t]) for t in sorted(techniques) if t in COCKPIT_PAINT_SCALES]
    unmeasured = sorted(t for t in techniques if t in UNMEASURED_PAINT_TECHNIQUES)
    root = xml(settings) if settings is not None else ET.Element("ShaderSettings")
    wanted = [w for w in wanted if not root.findall(w[0]+"/"+w[1])]
    if not wanted:
        return settings, [], unmeasured
    bom = b"\xef\xbb\xbf" if settings is not None and settings.startswith(b"\xef\xbb\xbf") else b""
    text = settings[len(bom):].decode("utf-8") if settings is not None else "<ShaderSettings>\r\n</ShaderSettings>\r\n"
    newline = "\r\n" if "\r\n" in text else "\n"

    def before(match):
        # At the start of the closing tag's line when only indentation precedes it.
        start = text.rfind("\n", 0, match.start())+1
        return start if not text[start:match.start()].strip() else match.start()
    tail = []
    for name, key, value in wanted:
        line = f'    <{key} value="{value:.3f}"/>{newline}'
        if root.find(name) is None:
            tail.append(f"  <{name}>{newline}{line}  </{name}>{newline}")
            continue
        closing = list(re.finditer(rf"</{name}\s*>", text))
        empty = list(re.finditer(rf"<{name}\s*/>", text))
        if len(closing)+len(empty) != 1:
            raise AppearanceError(f"Ambiguous shadersettings element: {name}")
        if closing:
            at = before(closing[0])
            text = text[:at]+(line if at < closing[0].start() or text[at-1:at] == "\n" else newline+line)+text[at:]
        else:
            m = empty[0]
            text = text[:m.start()]+f"<{name}>{newline}{line}  </{name}>"+text[m.end():]
    end = list(re.finditer(r"</ShaderSettings\s*>", text))
    if len(end) != 1:
        raise AppearanceError("Malformed shadersettings.xml root")
    at = before(end[0])
    lead = "" if not tail or text[at-1:at] in ("\n", "") else newline
    text = text[:at]+lead+"".join(tail)+text[at:]
    result = bom+text.encode("utf-8")
    # Every source entry, in order (some FM3 files repeat an element).
    entries = lambda r, skip=(): [(n.tag, p.tag, p.attrib) for n in r for p in n if (n.tag, p.tag) not in skip]
    if entries(xml(result), {(n, k) for n, k, _ in wanted}) != entries(root):
        raise AppearanceError("Source shadersettings value changed")
    return result, [{"technique": n, "parameter": k, "value": round(v, 3)} for n, k, v in wanted], unmeasured


def cockpit_techniques(payloads, media):
    path = next((p for p in payloads if p.as_posix().casefold()
                 == f"media/cars/{media}/{media}_cockpit.carbin".casefold()), None)
    if path is None:
        return set()
    model = carbin_audit.parse(payloads[path], "FM4")
    return {technique(s["name"], m["name"], m["lod"]) for s in model["sections"] for m in s["meshes"]}


def with_cockpit_paint_scales(payloads, media):
    """Write FM4 paint scales for the cockpit's techniques into shadersettings.xml."""
    car = f"Media/Cars/{media}/"
    path = next((p for p in payloads if p.as_posix().casefold() == (car+"shadersettings.xml").casefold()),
                Path(car)/"shadersettings.xml")
    result, added, unmeasured = cockpit_paint_settings(payloads.get(path), cockpit_techniques(payloads, media))
    payloads = dict(payloads)
    if result is not None:
        payloads[path] = result
    return payloads, {"added": added, "unmeasured_techniques_left_at_default": unmeasured}


def driver_attributes(data):
    if data is None:
        return {"car_attributes_version": None, "native_precedent": "no carattribs.xml",
                "source_attributes_preserved": True}
    root = xml(data)
    driver = root.find("Driver")
    version = (root.get("Version"), driver.get("Version") if driver is not None else None)
    if root.tag != "CarAttributes" or version not in NATIVE_LAYOUTS:
        raise AppearanceError(f"CarAttributes/Driver version {version} has no native FM4 precedent")
    required, layout = NATIVE_LAYOUTS[version]
    for node in (driver, *(root.find(n) for n in required)):
        if node is None or not all(math.isfinite(float(v)) for v in node.attrib.values()):
            raise AppearanceError("Missing/nonfinite driver or cockpit attribute")
    for node, attr in ((driver, "BodyScale"), (root.find("DriverHandsScale"), "value"),
                       (root.find("CockpitNearPlane"), "value")):
        if node is not None and float(node.get(attr, "0")) <= 0:
            raise AppearanceError("Driver scale or cockpit near plane must be positive")
    if layout == "Gauges":
        gauges = root.find("Gauges")
        if gauges is None or [g.tag for g in gauges] != ["Speed", "Tach", "Fuel", "Boost"]:
            raise AppearanceError("Unreviewed legacy gauge layout")
        gauges = list(gauges)
    elif layout:
        gauges = [root.find(n) for n in layout]
        if any(g is None for g in gauges):
            raise AppearanceError("Unreviewed legacy gauge layout")
    else:
        gauges = []
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
    hands, near = root.find("DriverHandsOffset"), root.find("CockpitNearPlane")
    offset = [float(hands.attrib["value."+a]) for a in "xyz"] if hands is not None else None
    return {"car_attributes_version": int(version[0]), "driver_version": int(version[1]),
            "gauge_tick_counts": counts, "hands_offset": offset,
            "hands_auto_offset": offset is None or all(x == 0 for x in offset),
            "body_scale": float(driver.attrib["BodyScale"]),
            "near_plane": float(near.attrib["value"]) if near is not None else None,
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
        if filename == "shadersettings.xml":
            # Only the FM4 cockpit paint scales may be added (see COCKPIT_PAINT_SCALES).
            old, paint_added, paint_unmeasured = cockpit_paint_settings(old, cockpit_techniques(target, media))
        # Absent in both is native too (63 Disc 1 cars ship no shadersettings.xml).
        if old != lookup.get(car+filename):
            raise AppearanceError(f"Source {filename} was not preserved")
    attributes = lookup.get(car+"carattribs.xml")
    driver = driver_attributes(attributes)
    settings_xml = lookup.get(car+"shadersettings.xml")
    overrides = xml(settings_xml) if settings_xml is not None else ET.Element("ShaderSettings")
    inputs, libraries = {}, {}
    for mode, filename in (("race", "shaders_v16.fxobj"), ("ui", "shaders_ui_v16.fxobj")):
        path = target_root/"Shaders/Cars"/filename
        data = path.read_bytes()
        inputs[str(path)] = sha(data)
        libraries[mode] = effect_audit.read_effect(data)

    shared_path, driver_path = target_root/"Cars/Shared.zip", target_root/"Cars/Driver.zip"
    for path in (shared_path, driver_path, target_root/"zipmanifest.xml"):
        inputs[str(path)] = sha(path.read_bytes())
    mounts = {n.attrib["path"].replace("\\", "/").casefold()
              for n in xml((target_root/"zipmanifest.xml").read_bytes()).findall("Zip")}
    for name in ("shared", "driver"):
        if f"game:/media/cars/{name}.zip" not in mounts:
            raise AppearanceError(f"Native {name} archive is not mounted")
    # The native driver audit decodes four GR2 files of Driver.zip that libmspack cannot read
    # with the proprietary XMem and Granny DLLs, supplied locally and never bundled. Without
    # both (a player's computer), the audit is skipped and recorded so; it reads FM4's own
    # driver files and the car's carattribs.xml, and changes no packaged byte.
    archive_decoder, granny_decoder = archive_cpu.decoder_path(), granny_audit.decoder_path()
    if not (archive_decoder.is_file() and granny_decoder.is_file()):
        driver_files = None
        driver_animation = {"passed": None, "skipped": "The proprietary XMem and Granny decoders are "
                            "not present; the native driver animation audit did not run"}
        archive_validation = "Native driver files not decoded (decoders absent)"
    else:
        inputs[str(archive_decoder)] = sha(archive_decoder.read_bytes())
        if inputs[str(archive_decoder)] != archive_cpu.DECODER_SHA256:
            raise AppearanceError("Unreviewed CPU archive decoder")
        with zipfile.ZipFile(driver_path) as z:
            entries = {n.casefold(): n for n in z.namelist() if not n.endswith("/")}
            for required in ("driverlod0.gr2", "hands.gr2", "driver.anim.bin", "driver01.skinbin",
                             "driver02.skinbin"):
                if required not in entries:
                    raise AppearanceError(f"Missing native driver dependency: {required}")
            driver_payloads = {n: archive_read(z, n) for n in sorted(entries.values())}
            driver_files = [{"path": n, "sha256": sha(b)} for n, b in driver_payloads.items()]
            driver_animation = driver_audit.audit(attributes, driver_payloads)
            inputs[str(granny_decoder)] = sha(granny_decoder.read_bytes())
        archive_validation = "Native driver files decoded on CPU; every ZIP size and CRC verified"

    bindings, rows, undeclared, checked_overrides, absent, unknown_techniques = {}, [], set(), [], [], []
    with zipfile.ZipFile(shared_path) as shared:
        names = {n.casefold(): n for n in shared.namelist()}
        definitions = xml(archive_read(shared, names["textures.xml"]))
        settings = [xml(archive_read(shared, names["shadersettings/"+n+".xml"]))
                    for n in ("normal", "metallic", "ui")]
        for node in overrides:
            for parameter in node:
                # Native FM4 shadersettings also name techniques/constants its
                # effects lack (e.g. CockpitPaintScale on 22 Disc 1 cars,
                # tail_light_LOD0 on ACU_NSX_97): the binder leaves them unused.
                unbound = [mode for mode, effects in libraries.items()
                           if node.tag not in effects or parameter.tag not in effects[node.tag]["constants"]]
                # Empty elements carry nothing to bind; FM4 ships some too
                # (GMC_Syclone_92, LEX_1_SC430_10).
                if not all(math.isfinite(float(v)) for v in parameter.attrib.values()):
                    raise AppearanceError("Nonfinite material override")
                if unbound and {"technique": node.tag, "parameter": parameter.tag} in [
                        {k: a[k] for k in ("technique", "parameter")} for a in paint_added]:
                    raise AppearanceError("Added cockpit paint scale is not an effect constant")
                checked_overrides.append({"technique": node.tag, "parameter": parameter.tag,
                                          "unbound_in": unbound, **parameter.attrib})

        def dependency(root, name, technique_name=None):
            key = (root + name).casefold()
            if key not in lookup and (technique_name, name.casefold()) in ABSENT_TEXTURE_PRECEDENT:
                absent.append({"technique": technique_name, "texture": root+name,
                               "native_precedent": ABSENT_TEXTURE_PRECEDENT[(technique_name, name.casefold())]})
                return key
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

        missing = set()
        for path, data in sorted(target.items()):
            if path.suffix.lower() == ".carbin":
                for section in carbin_audit.parse(data, "FM4")["sections"]:
                    for mesh in section["meshes"]:
                        name = technique(section["name"], mesh["name"], mesh["lod"])
                        if name not in NATIVE_UNKNOWN_TECHNIQUES or any(name in e for e in libraries.values()):
                            missing.update(f"{mode} {path.name}/{section['name']}/{name}"
                                           for mode, effects in libraries.items() if name not in effects)
        if missing:
            raise AppearanceError("Missing technique(s): " + ", ".join(sorted(missing)))
        for path, data in sorted(target.items()):
            if path.suffix.lower() != ".carbin":
                continue
            model = carbin_audit.parse(data, "FM4")
            if path.stem.casefold() == media.casefold()+"_cockpit":
                driver["rig"] = rig(model)
            for section in model["sections"]:
                for mesh in section["meshes"]:
                    name = technique(section["name"], mesh["name"], mesh["lod"])
                    if name in NATIVE_UNKNOWN_TECHNIQUES and all(name not in e for e in libraries.values()):
                        unknown_techniques.append({"model": path.as_posix(), "part": section["name"],
                                                   "material": mesh["name"], "lod": mesh["lod"],
                                                   "index_count": mesh["indices"]["count"],
                                                   "native_precedent": NATIVE_UNKNOWN_TECHNIQUES[name]})
                        continue
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
                            deps.add(dependency(root, texture.attrib["value"], name))
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
            "cockpit_paint_scales": {"added": paint_added,
                                     "unmeasured_techniques_left_at_default": paint_unmeasured},
            "absent_textures_with_native_precedent": absent,
            "techniques_without_effect_native_precedent": unknown_techniques,
            "archive_validation": archive_validation,
            "native_driver_assets": driver_files}
