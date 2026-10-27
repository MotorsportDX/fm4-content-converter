"""Preserve the FM3 stock cockpit reference in FM4, using traced selector IDs.

This covers explicit nonzero cockpit offsets only. It does not infer a camera
from model bounds or retune the driver's animation rig.
"""
import math

import converter as c

EVIDENCE = {
    "fm3_reference_selector":{"function":"0x824622E0","instruction":"0x8246230C: li r5,4",
                             "image_sha256":"a1d914cdc4ac837e6ba5cbdf2419d4effbafc160d3c51160a32e6f58e06cb67d"},
    "fm4_reference_selector":{"function":"0x8267CE90","instruction":"0x8267CEBC: li r5,9",
                             "image_sha256":"7a56b178d856c0dabb6d32120de6b5b6d7182a0c35bff836763d08684e3d5c41"},
    "explicit_offsets":["FM3 0x82462350: offsets at +52/+56/+60",
                        "FM4 0x8267CF18: offsets at +52/+56/+60"],
    "reference_plus_offset":["FM3 0x824624D8..0x824624E8",
                             "FM4 0x82687E74..0x82687E80"],
    "fm4_part_loader":"0x823C3A10: PartId 0..9, stride 16",
}


def apply(source_db, target_db, car_id, additions):
    refs = c.rows(source_db,"CarPartPositions","Ordinal=? AND PartId=4",(car_id,))
    cameras = c.rows(source_db,"CameraOverrides","CarId=?",(car_id,))
    if len(refs)!=1 or len(cameras)!=1:
        return {"applied":False,"reason":"Source cockpit reference or explicit camera row missing"}
    axes = "XYZ"
    offset = [cameras[0]["CamCockpitOffset"+axis] for axis in axes]
    if not any(offset):
        return {"applied":False,"reason":"Source uses INI defaults; default-offset mapping is not implemented"}
    reference = [refs[0]["PartPos"+axis] for axis in axes]
    if not all(isinstance(v,(int,float)) and math.isfinite(v) for v in reference+offset):
        raise c.MappingError("Nonfinite cockpit reference or offset")
    if c.rows(target_db,"CarPartPositions","Ordinal=? AND PartId=9",(car_id,)):
        raise c.MappingError("Target cockpit reference already exists")
    if any(x["table"]=="CarPartPositions" and x["row"]["PartId"]==9 for x in additions):
        raise c.MappingError("Cockpit reference was already mapped")
    highest = target_db.execute("SELECT MAX(ID) FROM CarPartPositions").fetchone()[0] or 0
    highest = max([highest]+[x["row"]["ID"] for x in additions if x["table"]=="CarPartPositions"])
    row = {"ID":highest+1, "Ordinal":car_id, "PartId":9,
           **{"PartPos"+axis:value for axis,value in zip(axes,reference)}}
    additions.append({"table":"CarPartPositions","row":row})
    return {"applied":True,"source_part_id":4,"target_part_id":9,
            "reference":reference,"explicit_offset":offset,
            "reference_plus_offset":[a+b for a,b in zip(reference,offset)],
            "evidence":EVIDENCE,
            "scope":"Stock local cockpit basepoint before look/headtracking/world transform",
            "runtime_tested":False,"driver_animation_validated":False}
