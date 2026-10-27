"""FM4 native hand-rig and selected animation data compatibility, offline.

Branch evidence: 828EB3F8 (clip loading), 828E57A0 (initial blend),
82D2E1B0 / 82D8FC68 (clip registry), 82903B80 (attributes).
This validates binding/data; it does not reproduce IK or animate a rendered pose.
SPDX-License-Identifier: GPL-3.0-only
"""
from collections import Counter
import hashlib
import math
import struct
import xml.etree.ElementTree as ET

import granny_audit as gr


class DriverError(ValueError):
    pass


REQUIRED = {"Bone_Spine_01", "Bone_Spine_02", "Bone_Spine_03", "Bone_ShoulderL",
            "Bone_ShoulderR", "Bone_ArmUpper_L", "Bone_ArmUpper_R", "Bone_ArmLower_L",
            "Bone_ArmLower_R", "Bone_HandL", "Bone_HandR", "Bone_ForArmNub_L",
            "Bone_ForArmNub_R", "Bone04", "Bone_Thumb_R03"}
REST_ANCHORS = {"l_anchor_target", "l_anchor_targetB", "r_anchor_target", "r_anchor_targetB"}
FORMATS = {1: "DaK32fC32f", 2: "DaIdentity", 3: "DaConstant32f",
           4: "D3Constant32f", 5: "D4Constant32f",
           8: "D4nK16uC15u", 9: "D4nK8uC7u", 10: "D3K16uC16u",
           11: "D3K8uC8u", 18: "D3I1K8uC8u"}


def finite(values):
    if not all(math.isfinite(v) for v in values):
        raise DriverError("Nonfinite driver transform/curve data")


def numbers(value):
    if isinstance(value, gr.Node):
        return [v for key in value.fields for v in numbers(value.get(key))]
    if isinstance(value, (list, tuple)):
        return [v for item in value for v in numbers(item)]
    if isinstance(value, (float, int)):
        return [value]
    raise DriverError("Unexpected nonnumeric animation curve member")


def curve(node, dimension, duration):
    data = node.get("CurveData")
    if data is None:
        raise DriverError("Missing driver curve data")
    headers = [k for k in data.fields if k.startswith("CurveDataHeader_")]
    if len(headers) != 1:
        raise DriverError("Missing driver curve header")
    header = data.get(headers[0])
    fmt, degree = header.get("Format"), header.get("Degree")
    if fmt not in FORMATS or headers[0] != "CurveDataHeader_" + FORMATS[fmt]:
        raise DriverError("Unreviewed driver curve format")
    finite(numbers(data))
    if not 0 <= degree <= 3:
        raise DriverError("Invalid driver curve degree")
    if fmt == 2:
        if degree != 0 or data.get("Dimension") != dimension:
            raise DriverError("Identity curve dimension/degree mismatch")
        return FORMATS[fmt]
    if fmt in (3, 4, 5):
        controls = numbers(data.get("Controls"))
        if len(controls) != dimension or degree != 0:
            raise DriverError("Constant curve dimension/degree mismatch")
        if dimension == 4 and abs(sum(v*v for v in controls)-1) > .01:
            raise DriverError("Non-unit constant driver quaternion")
        return FORMATS[fmt]
    tolerance = 0.0001
    if fmt == 1:
        knots = numbers(data.get("Knots"))
        if len(numbers(data.get("Controls"))) != dimension*len(knots):
            raise DriverError("Float curve knot/control count mismatch")
    else:
        if dimension != (4 if fmt in (8, 9) else 3):
            raise DriverError("Compressed curve dimension mismatch")
        packed = numbers(data.get("KnotsControls"))
        width = 2 if fmt == 18 else 4
        if len(packed) % width:
            raise DriverError("Compressed curve knot/control count mismatch")
        if fmt in (8, 9):
            scale = data.get("OneOverKnotScale")
        else:
            scale = struct.unpack("<f", struct.pack("<I", data.get("OneOverKnotScaleTrunc") << 16))[0]
        if not math.isfinite(scale) or scale <= 0:
            raise DriverError("Invalid driver curve time scale")
        knots = [x/scale for x in packed[:len(packed)//width]]
        tolerance = max(tolerance, 2/scale)
    if len(knots) <= degree or any(a > b for a, b in zip(knots, knots[1:])):
        raise DriverError("Invalid/nonmonotonic driver curve knots")
    if knots[0] < 0 or knots[-1] > duration + tolerance:
        raise DriverError("Driver curve time outside animation duration")
    return FORMATS[fmt]


def skeletons(assets):
    results = []
    for filename in ("driverlod001.gr2", "driverlod002.gr2"):
        root = gr.File(assets[filename]).root
        matches = [s for s in root.get("Skeletons") if s.get("Name") == "Bone_Spine_01"]
        if len(matches) != 1:
            raise DriverError("Native hand skeleton is missing or ambiguous")
        bones = matches[0].get("Bones")
        names = [b.get("Name") for b in bones]
        if len(set(names)) != len(names) or not REQUIRED <= set(names):
            raise DriverError("Missing/duplicate native driver bones")
        parents = [b.get("ParentIndex") for b in bones]
        if parents.count(-1) != 1:
            raise DriverError("Driver skeleton needs one root")
        for i, bone in enumerate(bones):
            # Native order need not be topological. Check every ancestry chain.
            visited = {i}
            p = parents[i]
            while p != -1:
                if not 0 <= p < len(bones) or p in visited:
                    raise DriverError("Cyclic/invalid driver bone parent")
                visited.add(p)
                p = parents[p]
            transform = bone.get("Transform")
            finite(transform[1:])
            finite(bone.get("InverseWorldTransform"))
            if transform[0] & ~7 or abs(sum(v*v for v in transform[4:8])-1) > .01:
                raise DriverError("Invalid driver rest transform/quaternion")
        results.append({"path": filename, "bones": names, "parents": parents,
                        "sha256": hashlib.sha256(assets[filename]).hexdigest()})
    if results[0]["bones"] != results[1]["bones"] or results[0]["parents"] != results[1]["parents"]:
        raise DriverError("Native driver skin skeletons disagree")
    return results


def selection(attributes):
    root = ET.fromstring(attributes)
    alternate = root.find("Use10_2Animations")
    if alternate is None or alternate.get("value") not in ("0", "1"):
        raise DriverError("Missing/invalid Use10_2Animations")
    driver = root.find("Driver")
    if driver is None or driver.get("HasPaddleShifter") not in ("0", "1"):
        raise DriverError("Missing/invalid HasPaddleShifter")
    use_alt = alternate.get("value") == "1"
    paddle = driver.get("HasPaddleShifter") == "1"
    suffix = "_B" if use_alt else ""
    files = [f"SteerLock2Lock{size}{suffix}.gr2" for size in ("Small", "Large")]
    files += ([f"RotatingPaddleShift{side}.gr2" for side in ("Left", "Right")] if paddle
              else [f"ShiftStickConsole{side}.gr2" for side in ("Left", "Right")])
    if paddle:
        files += [f"SteerLock2Lock{size}{suffix}_ROT.gr2" for size in ("Small", "Large")]
    return {"use_10_2": use_alt, "has_paddle_shifter": paddle,
            "steering_clip_ids": [4, 5, 6, 7] if use_alt else [0, 1, 2, 3],
            "shift_clip_ids_checked": [16, 17] if paddle else [18, 19],
            "shift_scope": "Both handedness branches checked; runtime chooses one stick-shift side",
            "files": files}


def audit(attributes, assets):
    assets = {k.casefold(): v for k, v in assets.items()}
    selected = selection(attributes)
    required = {"driverlod001.gr2", "driverlod002.gr2"} | {n.casefold() for n in selected["files"]}
    if missing := required - assets.keys():
        raise DriverError(f"Missing native driver animation/model: {sorted(missing)}")
    skins = skeletons(assets)
    bone_names = set(skins[0]["bones"])
    animations = []
    for filename in selected["files"]:
        raw = assets[filename.casefold()]
        root = gr.File(raw).root
        anims = root.get("Animations")
        if len(anims) != 1:
            raise DriverError("Expected one native driver animation")
        anim = anims[0]
        duration, step = anim.get("Duration"), anim.get("TimeStep")
        finite((duration, step))
        if not 0 < step <= duration <= 120:
            raise DriverError("Invalid driver animation timing")
        groups = [g for g in anim.get("TrackGroups") if g.get("Name") == "Bone_Spine_01"]
        if len(groups) != 1:
            raise DriverError("Driver animation has no unique matching skeleton track group")
        tracks = groups[0].get("TransformTracks")
        names = [t.get("Name") for t in tracks]
        missing = bone_names - set(names)
        if len(set(names)) != len(names) or not REQUIRED <= set(names) or missing - REST_ANCHORS:
            raise DriverError("Driver animation has missing/duplicate bone tracks")
        formats = Counter()
        for track in tracks:
            for field, dimension in (("OrientationCurve", 4), ("PositionCurve", 3), ("ScaleShearCurve", 9)):
                formats[curve(track.get(field), dimension, duration)] += 1
        animations.append({"path": filename, "sha256": hashlib.sha256(raw).hexdigest(),
                           "duration_seconds": duration, "time_step_seconds": step,
                           "track_count": len(tracks), "matched_bones": len(bone_names & set(names)),
                           "rest_pose_anchors_without_tracks": sorted(missing),
                           "extra_tracks": sorted(set(names)-bone_names), "curve_formats": dict(formats)})
    return {"passed": True, "scope": "Native hand skeleton, selected clip bindings, curve data integrity",
            "selection": selected, "skins": skins, "animations": animations,
            "pose_playback_tested": False, "body_anim_bin_decoded": False,
            "limitations": ["IK, blend weights, coordinate conversion and grip alignment require pose playback",
                            "driver.anim.bin remains archive CRC/size checked only"]}
