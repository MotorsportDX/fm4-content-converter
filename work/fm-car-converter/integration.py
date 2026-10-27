"""Build a stock-car import probe for an isolated FM4-PC test disc.

Original game data and the normal user profile are never installation targets.
Runtime acceptance is recorded separately from successful database validation.
"""
from __future__ import annotations

from collections import Counter
from contextlib import closing
import json
import io
from pathlib import Path, PurePosixPath
import sqlite3
import struct
import sys
import xml.etree.ElementTree as ET
import zipfile

import converter as c
import code_semantics
import ui_names
import ui_thumbnail
from calibration import apply_to_result

SHARED = Path(__file__).resolve().parents[2] / "outputs/physics-research-2026-10-20/shared"


def archive_read(archive, member):
    # The existing local method-21 decoder verifies decompressed size and CRC.
    if str(SHARED) not in sys.path:
        sys.path.insert(0, str(SHARED))
    import forza_zip
    try:
        return forza_zip.read(archive, member)
    except ValueError:
        info = archive.getinfo(member) if isinstance(member, str) else member
        if info.compress_type != 21:
            raise
        from archive_cpu import read_xmem
        # Some native driver GR2 streams exceed the research decoder's support.
        # The fallback must independently reproduce the exact ZIP size and CRC.
        return read_xmem(archive, info)


def safe_member(name):
    normalized = name.replace("\\", "/")
    parts = PurePosixPath(normalized)
    if (parts.is_absolute() or ".." in parts.parts or ":" in normalized
            or not parts.parts or any(p.endswith((".", " ")) for p in parts.parts)):
        raise c.MappingError(f"Unsafe archive member: {name!r}")
    return parts


def build_plan(source_db, target_db, media, rules=None, display_name=None):
    """Plan a new stock car without changing either database."""
    source = c.extract_stock(source_db, media)
    car_id = source["nodes"]["car"]["row"]["Id"]
    if not 1 <= car_id < 65535:
        raise c.MappingError("The source ordinal is outside this probe's 16-bit range")
    if c.rows(target_db, "Data_Car", "Id=? OR lower(MediaName)=lower(?)", (car_id, media)):
        raise c.MappingError("The car identity already exists in the target; replacement is unsupported")
    result = c.convert(source_db, target_db, source, id_base=2000)
    if rules is not None:
        apply_to_result(result, source, rules, "conservative")
    code_semantics.apply(result, source)
    graph = result["candidate"]
    car = graph["nodes"]["car"]["row"]
    old_id = car["Id"]
    car["Id"] = car_id
    for edge in graph["edges"]:
        if edge["to"] == "car":
            graph["nodes"][edge["from"]]["row"][edge["column"]] = car_id
    changes = []
    label = display_name or (media+" (FM3)")
    if not label.strip() or label.startswith("_&") or "\0" in label:
        raise c.MappingError("Use a nonempty literal display name, not a source localization key")
    names = ui_names.plan(source["nodes"]["car"]["row"], label)
    for field, value in {
        "ModelId":car_id, "ContentId":0, "IsInstalled":1, "IsPurchased":1,
        "IsArcade":1, "IsUnicorn":0, "IsDrivable":1,
        "HasCarExperience":0, "IsCarExperienceUnlocked":0,
        "DisplayName":names["DisplayName"]["reference"],
        "ModelShort":names["ModelShort"]["reference"],
    }.items():
        changes.append({"role":"car", "column":field, "before":car[field], "after":value})
        car[field] = value
    for entry in result["id_map"]:
        if entry["table"] == "Data_Car":
            entry["target_id"] = car_id
    for mapping in result["mapping"]:
        row = graph["nodes"][mapping["role"]]["row"]
        mapping["target_value"] = row[mapping["target_column"]]
    for role, node in graph["nodes"].items():
        if not 1 <= node["row"][node["pk"]] < 2**31:
            raise c.MappingError(f"Invalid allocated key: {role}")
    additions, reused = [], []
    tc, sc = c.schema(target_db), c.schema(source_db)
    presentation = {
        "CarPartPositions":"Ordinal", "CarExceptions":"CarID",
        "CarInvalidDefaultParts":"Ordinal", "CameraOverrides":"CarId",
        "CarTrackOffsets":"Id", "Combo_Colors":"Ordinal",
        "Combo_Colors_Exceptions":"Ordinal", "ArcadeCarList":"CarId",
    }
    for table, scope in presentation.items():
        selected = c.rows(source_db, table, c.qi(scope)+"=?", (car_id,))
        if not selected:
            continue
        existing = c.rows(target_db, table, c.qi(scope)+"=?", (car_id,))
        if existing:
            if existing != selected:
                raise c.MappingError(f"Conflicting target presentation rows for {table}/{car_id}")
            reused.append({"table":table, "rows":existing})
            continue
        source_columns = {x["name"] for x in sc[table]["columns"]}
        generated_id = 1 + (target_db.execute(
            "SELECT MAX(ID) FROM "+c.qi(table)).fetchone()[0] or 0) if table in {
                "CarPartPositions","Combo_Colors","Combo_Colors_Exceptions"} else None
        for original in selected:
            row = {}
            for col in tc[table]["columns"]:
                key = col["name"]
                if key in original:
                    row[key] = original[key]
                elif key == "ID" and generated_id is not None:
                    row[key] = generated_id
                    generated_id += 1
                elif table == "CameraOverrides":
                    counts = Counter(r[0] for r in target_db.execute(
                        "SELECT "+c.qi(key)+" FROM "+c.qi(table)))
                    mode = counts.most_common()
                    if not mode or mode[0][0] != 0 or (len(mode)>1 and mode[0][1]==mode[1][1]):
                        raise c.MappingError(f"No unambiguous neutral camera default for {key}")
                    row[key] = 0.0
                else:
                    raise c.MappingError(f"Unmapped presentation field {table}.{key}")
            if source_columns - row.keys():
                raise c.MappingError(f"Removed presentation fields: {table}")
            additions.append({"table":table, "row":row})
    import camera_semantics
    camera = camera_semantics.apply(source_db,target_db,car_id,additions)
    result["integration"] = {
        "source_ordinal":car_id, "initial_candidate_ordinal":old_id,
        "metadata_changes":changes, "presentation_rows":additions, "reused_presentation":reused,
        "scope":"Stock, base disc only, isolated FM4-PC import probe",
        "accepted":False, "runtime_tested":False,
        "cockpit_reference":camera,
        "localized_names":names,
    }
    return source, result


def insert_rows(db, records):
    seen = set()
    for record in records:
        table, row = record["table"], record["row"]
        signature = (table, json.dumps(row, sort_keys=True))
        if signature in seen:
            continue
        seen.add(signature)
        db.execute("INSERT INTO "+c.qi(table)+" ("+",".join(map(c.qi,row))
                   +") VALUES ("+",".join("?" for _ in row)+")",tuple(row.values()))
    return len(seen)


def asset_archives(payloads, media, wheel):
    """Explicit mounts are necessary: the retail resolver ignores unlisted loose car files."""
    roots = (Path("Media/Cars")/media, Path("Media/Wheels")/wheel,
             Path("Media/UI/Textures/Thumbnails"))
    archives = {}
    accounted = set()
    for root in roots:
        stream = io.BytesIO()
        with zipfile.ZipFile(stream,"w",compression=zipfile.ZIP_STORED) as z:
            for path,data in sorted(payloads.items()):
                if path.is_relative_to(root):
                    info = zipfile.ZipInfo(path.relative_to(root).as_posix(),(1980,1,1,0,0,0))
                    info.compress_type = zipfile.ZIP_STORED
                    z.writestr(info,data)
                    accounted.add(path)
        archives[root.with_suffix(".zip")] = stream.getvalue()
    if accounted != payloads.keys():
        raise c.MappingError("Asset has no reviewed ZIP mount")
    return archives


def extend_zip_manifest(original, archives, replacements=()):
    tree = ET.fromstring(original)
    if tree.tag != "ZipFiles" or tree.attrib.get("version") != "3":
        raise c.MappingError("Unsupported target ZIP manifest")
    paths = {x.attrib["path"].casefold() for x in tree.findall("Zip")}
    replace = {"game:\\"+str(p).replace("/","\\").lower() for p in replacements}
    supplied = {"game:\\"+str(p).replace("/","\\").lower() for p in archives}
    if not replace <= paths & supplied:
        raise c.MappingError("Replacement ZIP must have an existing mount and supplied payload")
    for path,data in sorted(archives.items()):
        guest = "game:\\"+str(path).replace("/","\\").lower()
        if guest.casefold() in paths and guest not in replace:
            raise c.MappingError(f"ZIP mount already exists: {guest}")
        # Our generated archives have no comments and are ordinary ZIP32.
        if data[-22:-18] != b"PK\x05\x06":
            raise c.MappingError("Missing canonical ZIP end record")
        disk,cd_disk,n_disk,count,size,start,comment = struct.unpack_from("<4H2IH",data,len(data)-18)
        if disk or cd_disk or n_disk != count or comment or start+size != len(data)-22:
            raise c.MappingError("Invalid ZIP32 directory")
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            if z.testzip() is not None or len(z.infolist()) != count:
                raise c.MappingError("Generated archive failed CRC validation")
        if guest in replace:
            nodes = [x for x in tree.findall("Zip") if x.attrib["path"].casefold()==guest]
            if len(nodes)!=1:
                raise c.MappingError("Ambiguous replacement ZIP mount")
            nodes[0].attrib.update(dirstart=str(start),dirsize=str(size),direntries=str(count))
        else:
            ET.SubElement(tree,"Zip",{"version":"1","path":guest,"priority":"80",
                                     "dirstart":str(start),"dirsize":str(size),"direntries":str(count)})
        paths.add(guest.casefold())
    return ET.tostring(tree,encoding="utf-8",xml_declaration=True)


def stage_probe(source_path, target_path, disc, out, media, rules_path=None, display_name=None,
                model_helper=None):
    """Populate a *copy* of the target disc; never accepts original roots."""
    source_path, target_path, disc, out = map(
        lambda x:Path(x).resolve(), (source_path, target_path, disc, out))
    for original in (source_path.parents[2], target_path.parents[2]):
        if disc == original or original in disc.parents or disc in original.parents:
            raise c.MappingError("Test disc must be separate from original game directories")
        if out == original or original in out.parents:
            raise c.MappingError("Output must be outside original game directories")
    destination_db = disc / "Media/DB/gamedb.slt"
    if not destination_db.exists() or c.sha(destination_db) != c.sha(target_path):
        raise c.MappingError("Test disc must contain an unchanged copy of the target database")
    if out.exists():
        raise c.MappingError("Choose a new output directory")
    if model_helper is None:
        raise c.MappingError("A reviewed CPU model converter is required; raw FM3 models are incompatible")
    source_root, target_root = source_path.parents[1], target_path.parents[1]
    inputs = {str(source_path):c.sha(source_path), str(target_path):c.sha(target_path)}
    payloads = {}
    with closing(c.connect(source_path)) as source_db, closing(c.connect(target_path)) as target_db:
        rules = json.loads(Path(rules_path).read_text(encoding="utf-8")) if rules_path else None
        source, result = build_plan(source_db, target_db, media, rules, display_name)
        wheel = source["nodes"]["wheel"]["row"]["MediaName"]
        assets = []
        for folder, name in (("Cars",media), ("Wheels",wheel)):
            path = source_root/folder/(name+".zip")
            inputs[str(path)] = c.sha(path)
            with zipfile.ZipFile(path) as archive:
                for info in archive.infolist():
                    member = safe_member(info.filename)
                    if info.is_dir():
                        continue
                    relative = Path("Media")/folder/name/Path(*member.parts)
                    data = archive_read(archive, info)
                    if relative.as_posix().casefold() in {p.as_posix().casefold() for p in payloads}:
                        raise c.MappingError("Duplicate case-insensitive asset path")
                    payloads[relative] = data
                    assets.append({"path":relative.as_posix(), "bytes":len(data),
                                   "carbin_version":int.from_bytes(data[:4],"big")
                                   if member.suffix.lower()==".carbin" else None,
                                   "source":str(path), "member":info.filename})
        thumb_zip = source_root/"UI/Textures.zip"
        thumb_member = f"Thumbnails/Thumbnail_{source['nodes']['car']['row']['Id']}.xds"
        inputs[str(thumb_zip)] = c.sha(thumb_zip)
        with zipfile.ZipFile(thumb_zip) as archive:
            payloads[Path("Media/UI/Textures")/thumb_member] = archive_read(archive,thumb_member)
        # FM4 retains several FM3 audio definitions. Require the exact car entry;
        # no silently substituted engine or donor-car model is permitted.
        audio = target_root/"audio/Cars/CarModelTuning.zip"
        with zipfile.ZipFile(audio) as archive:
            matches = [n for n in archive.namelist() if n.casefold()==(media+"_CMT.xml").casefold()]
            if len(matches) != 1:
                raise c.MappingError("Native FM4 car audio tuning is unavailable")
            archive_read(archive,matches[0])
        from asset_conversion import convert_payloads
        from appearance_audit import audit as audit_appearance
        source_payloads = payloads
        payloads, asset_validation = convert_payloads(source_payloads,model_helper)
        appearance_validation = audit_appearance(
            source_payloads, payloads, target_root, media, wheel, archive_read)
        inputs.update(appearance_validation["inputs"])
        # Generic material conversion preserves pixels. The UI thumbnail has a
        # different layout and is transformed/audited separately afterwards.
        native_ui = target_root/"UI/Textures.zip"
        inputs[str(native_ui)] = c.sha(native_ui)
        with zipfile.ZipFile(native_ui) as z:
            controls = [archive_read(z,f"Thumbnails/Thumbnail_{n}.xds") for n in (1002,1003,1305)]
        if len({b[:52] for b in controls}) != 1:
            raise c.MappingError("Native thumbnail control headers disagree")
        thumb_path = Path("Media/UI/Textures")/thumb_member
        payloads[thumb_path], thumbnail_validation = ui_thumbnail.convert(payloads[thumb_path],controls[0])
        for record in asset_validation["assets"]:
            if record["path"] == thumb_path.as_posix():
                record.update(operation="FM4 UI atlas with transparent matte and two view slots",
                              pixel_payload_unchanged=False,texture=thumbnail_validation["texture"],
                              sha256=thumbnail_validation["target_sha256"],bytes=len(payloads[thumb_path]))
        asset_validation["scope"] = "Model geometry/rig, material XDS preservation and separately audited UI atlas conversion"
        archives = asset_archives(payloads,media,wheel)
        name_archives, name_validation = ui_names.build_archives(
            source_root,target_root,result["integration"]["localized_names"],archive_read,c.sha)
        inputs.update(name_validation["inputs"])
        archives.update(name_archives)
        manifest_path = disc/"Media/zipmanifest.xml"
        original_manifest = target_root/"zipmanifest.xml"
        if c.sha(manifest_path) != c.sha(original_manifest):
            raise c.MappingError("Test disc ZIP manifest differs from the target")
        manifest_data = extend_zip_manifest(manifest_path.read_bytes(),archives,name_archives)
        for relative in archives:
            target = disc/relative
            if target.exists() and (relative not in name_archives or
                    c.sha(target) != c.sha(target_root/relative.relative_to("Media"))):
                raise c.MappingError(f"Refusing to replace an existing asset: {relative}")
        out.mkdir(parents=True)
        patch = c.write_patch(out/"stock.slt",target_db,result["candidate"])
        validation = c.validate(result["candidate"],target_db,out/"stock.slt",source)
        if not validation["passed"]:
            raise c.MappingError(str(validation["issues"]))
        c.dump(out/"source_ir.json",source)
        c.dump(out/"result.json",result)
        c.dump(out/"assets.json",assets)
        c.dump(out/"asset_validation.json",asset_validation)
        c.dump(out/"appearance_validation.json",appearance_validation)
        c.dump(out/"ui_name_validation.json",name_validation)
        c.dump(out/"ui_thumbnail_validation.json",thumbnail_validation)
        c.dump(out/"validation.json",validation)
    records = list(result["candidate"]["nodes"].values())+result["integration"]["presentation_rows"]
    with closing(sqlite3.connect(destination_db)) as db:
        with db:
            inserted = insert_rows(db,records)
            if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise c.MappingError("Merged database failed integrity_check")
    for relative, data in archives.items():
        target = disc/relative
        target.parent.mkdir(parents=True,exist_ok=True)
        # Replacing a copied archive must not mutate a hard-linked source file.
        temporary = target.with_name(target.name+".fm3-import.tmp")
        with temporary.open("xb") as f:
            f.write(data)
        temporary.replace(target)
    temporary = manifest_path.with_name(manifest_path.name+".fm3-import.tmp")
    with temporary.open("xb") as f:
        f.write(manifest_data)
    temporary.replace(manifest_path)
    for path, digest in inputs.items():
        if c.sha(path) != digest:
            raise c.MappingError(f"Input changed during staging: {path}")
    manifest = {"disc":str(disc), "media":media, "car_id":result["integration"]["source_ordinal"],
                "inputs":inputs, "sources_unchanged":True,
                "merged_rows":inserted, "merged_database_sha256":c.sha(destination_db),
                "assets":{p.as_posix():c.sha(disc/p) for p in archives},
                "zip_manifest_sha256":c.sha(manifest_path),
                "accepted":False, "runtime_tested":False,
                "offline_geometry_passed":True, "game_launch_permitted":False,
                "offline_appearance_structure_passed":True,
                "offline_sampler_metadata_passed":appearance_validation["sampler_validation"]["passed"],
                "offline_driver_animation_data_passed":appearance_validation["driver_animation_validation"]["passed"],
                "offline_ui_names_passed":name_validation["passed"],
                "offline_ui_thumbnail_passed":thumbnail_validation["passed"],
                "pending":["Rendered material/shading and driver/cockpit animation after user permission",
                           "Participant name and both thumbnail slots in runtime UI after user permission",
                           "Menu, visible original model and driving verification after user permission"]}
    c.dump(out/"manifest.json",manifest)
    return manifest


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fm3",type=Path,default=c.FM3_DEFAULT)
    parser.add_argument("--fm4",type=Path,default=c.FM4_DEFAULT)
    parser.add_argument("--disc",type=Path,required=True)
    parser.add_argument("--out",type=Path,required=True)
    parser.add_argument("--media-name",required=True)
    parser.add_argument("--rules",type=Path)
    parser.add_argument("--display-name",help="Literal name for the target menu")
    parser.add_argument("--model-helper",type=Path,required=True,help="Reviewed CPU-only carbin-cpu.exe")
    args = parser.parse_args()
    result = stage_probe(args.fm3,args.fm4,args.disc,args.out,args.media_name,args.rules,args.display_name,
                         args.model_helper)
    print(json.dumps({k:v for k,v in result.items() if k not in ("assets","inputs")},indent=2))
