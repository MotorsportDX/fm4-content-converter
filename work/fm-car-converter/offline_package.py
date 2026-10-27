"""Prepare an FM3 -> FM4 candidate in a NEW directory, using CPU only.

The output is a reviewed-file overlay, not a complete disc or signed Xbox DLC.
No installation, game launch, GPU access or profile modification occurs.
"""
from contextlib import closing
import json
from pathlib import Path
import shutil
import sqlite3
import zipfile

import converter as c
import integration as integration


SCOPES = {"CarPartPositions":"Ordinal","CarExceptions":"CarID",
          "CarInvalidDefaultParts":"Ordinal","CameraOverrides":"CarId",
          "CarTrackOffsets":"Id","Combo_Colors":"Ordinal",
          "Combo_Colors_Exceptions":"Ordinal","ArcadeCarList":"CarId"}


def overlay_collisions(result, paths):
    """Check effective identities against explicitly supplied installed DLC ZIPs."""
    records = list(result["candidate"]["nodes"].values())+result["integration"]["presentation_rows"]
    reports = []
    for path in paths:
        with zipfile.ZipFile(path) as z:
            for name in z.namelist():
                if not name.lower().endswith("_merge.slt"):
                    continue
                hits = []
                with closing(sqlite3.connect(":memory:")) as db:
                    db.row_factory = sqlite3.Row
                    db.deserialize(integration.archive_read(z,name))
                    sc = c.schema(db)
                    for node in records:
                        table,row = node["table"],node["row"]
                        if table not in sc:
                            continue
                        key = SCOPES.get(table,node.get("pk"))
                        if key is None:
                            raise c.MappingError(f"No collision key for {table}")
                        if db.execute("SELECT 1 FROM "+c.qi(table)+" WHERE "+c.qi(key)+"=?",
                                      (row[key],)).fetchone():
                            hits.append({"table":table,"key":key,"value":row[key]})
                        if table=="Data_Car" and db.execute(
                                "SELECT 1 FROM Data_Car WHERE lower(MediaName)=lower(?)",
                                (row["MediaName"],)).fetchone():
                            hits.append({"table":table,"key":"MediaName","value":row["MediaName"]})
                        # Presentation tables have both an owner key and a
                        # distinct primary key; either collision is unacceptable.
                        if "ID" in row and key!="ID" and db.execute(
                                "SELECT 1 FROM "+c.qi(table)+" WHERE ID=?",(row["ID"],)).fetchone():
                            hits.append({"table":table,"key":"ID","value":row["ID"]})
                reports.append({"path":str(path),"archive_sha256":c.sha(path),
                                "member":name,"collisions":hits})
    if any(r["collisions"] for r in reports):
        raise c.MappingError("DLC identity conflict: "+json.dumps(reports))
    return reports


def build(source, target, out, media, helper, rules=None, display_name=None, overlays=()):
    source,target,out = (Path(p).resolve() for p in (source,target,out))
    for original in (source.parents[2],target.parents[2]):
        if out==original or out in original.parents or original in out.parents:
            raise c.MappingError("Package output must be outside original game directories")
    if out.exists():
        raise c.MappingError("Choose a new package directory")
    with closing(c.connect(source)) as a, closing(c.connect(target)) as b:
        rule_data = json.loads(Path(rules).read_text()) if rules else None
        src,plan = integration.build_plan(a,b,media,rule_data,display_name)
        collision_report = overlay_collisions(plan,overlays)
    out.mkdir(parents=True)
    media_root = out/"files/Media"
    (media_root/"DB").mkdir(parents=True)
    shutil.copyfile(target,media_root/"DB/gamedb.slt")
    shutil.copyfile(target.parents[1]/"zipmanifest.xml",media_root/"zipmanifest.xml")
    try:
        manifest = integration.stage_probe(source,target,out/"files",out/"reports",media,
                                            rules,display_name,helper)
        result = json.loads((out/"reports/result.json").read_text())
        with closing(c.connect(target)) as db:
            # The import patch contains both physics and presentation metadata.
            sc = c.schema(db)
            with closing(sqlite3.connect(out/"reports/stock.slt")) as patch:
                with patch:
                    additions = result["integration"]["presentation_rows"]
                    for table in sorted({x["table"] for x in additions}):
                        patch.execute(sc[table]["sql"])
                    integration.insert_rows(patch,additions)
        with closing(c.connect(media_root/"DB/gamedb.slt")) as db:
            actual = c.extract_stock(db,media)
            if actual["nodes"] != result["candidate"]["nodes"]:
                raise c.MappingError("Merged database does not reproduce the planned stock graph")
        parts = [x["row"] for x in result["integration"]["presentation_rows"]
                 if x["table"]=="CarPartPositions"]
        pending = list(manifest["pending"])
        if not any(r["PartId"]==9 for r in parts):
            pending.insert(0,"FM4 cockpit/driver anchor PartId 9 is not yet mapped")
        manifest.update(
            package_type="Offline file overlay; not a complete game disc",
            installed=False, accepted=False, runtime_tested=False, game_launch_permitted=False,
            overlays_checked=len(collision_report), offline_database_roundtrip_passed=True,
            candidate_patch_sha256=c.sha(out/"reports/stock.slt"), pending=pending,
            files={p.relative_to(out/"files").as_posix():c.sha(p)
                   for p in (out/"files").rglob("*") if p.is_file()},
        )
        c.dump(out/"reports/dlc_collisions.json",collision_report)
        c.dump(out/"manifest.json",manifest)
        return manifest
    except Exception as error:
        c.dump(out/"FAILED.json",{"accepted":False,"installed":False,"error":str(error)})
        raise


if __name__=="__main__":
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--fm3",type=Path,default=c.FM3_DEFAULT)
    p.add_argument("--fm4",type=Path,default=c.FM4_DEFAULT)
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--media-name",required=True)
    p.add_argument("--model-helper",type=Path,required=True)
    p.add_argument("--rules",type=Path)
    p.add_argument("--display-name")
    p.add_argument("--overlay-zip",type=Path,action="append",default=[])
    a = p.parse_args()
    r = build(a.fm3,a.fm4,a.out,a.media_name,a.model_helper,a.rules,a.display_name,a.overlay_zip)
    print(json.dumps({k:v for k,v in r.items() if k not in ("inputs","assets","files")},indent=2))
