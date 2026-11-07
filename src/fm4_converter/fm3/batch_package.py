"""Package many FM3-only cars into ONE FM4 offline overlay, using CPU only.

FM4 serves one database, one Data_Car.str per language and one thumbnail atlas
mount, so per-car packages cannot be combined by copying files. Here cars are
planned one after another against the growing package database (their new keys
never collide) while every key of an installed DLC patch stays reserved.

Sources: FM3 Disc 1 (`Media/Cars|Wheels/<name>.zip`) and the Disc 2 content
packages (STFS `<n>_pri_65.zip`, loose `media/cars/<name>/...`). A wheel FM4
already ships (disc or installed DLC) is reused, not shipped again; a wheel two
imported cars share is converted once. A car whose registry row (e.g. the
Porsche make) exists only in a DLC patch records that pack in `requires`.

The output is a reviewed-file overlay, not a complete disc or signed Xbox DLC.
"""
from collections import defaultdict
from contextlib import closing
import glob
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import sqlite3
import traceback
import zipfile

from . import converter as c
from . import integration
from . import offline_package
from . import ui_names
from .integration import archive_read
from .. import stack

FM3_DISC2_DEFAULT = Path(r"D:\Data\FM3\USA\Forza Motorsport 3 (USA) (Disc 2) (Content Install Disc) (1)"
                         r"\Content\0000000000000000\4D53084D\00000002")
THUMBNAILS = Path("Media/UI/Textures/Thumbnails")
_DISC2_ZIP = re.compile(r"(?:^|/)\d{4}_pri_\d+\.zip$", re.IGNORECASE)


class Sources:
    """FM3 car/wheel folders on Disc 1 ZIPs and inside Disc 2 STFS packages."""

    def __init__(self, source_root, disc2=None):
        self.root, self.inputs, self.disc2 = Path(source_root), {}, {}
        for package in sorted(Path(disc2).glob("*")) if disc2 else ():
            from ..archives.stfs_reader import STFS
            from ..archives.stfs_zip_io import STFSFile
            stfs = STFS(package)
            for entry in stfs.entries:
                if entry["directory"] or not _DISC2_ZIP.search(entry["name"]):
                    continue
                archive = zipfile.ZipFile(STFSFile(stfs, entry))
                self.inputs[str(package)] = c.sha(package)
                for info in archive.infolist():
                    parts = info.filename.replace("\\", "/").split("/")
                    if len(parts) > 3 and parts[0].casefold() == "media" and not info.is_dir():
                        key = (parts[1].casefold(), parts[2].casefold())
                        self.disc2.setdefault(key, (f"{package.name}:{entry['name']}", archive, []))[2].append(info)

    def members(self, folder, name):
        """(origin, {relative member: bytes}) of Media/<folder>/<name>."""
        path = self.root/folder/(name+".zip")
        if path.exists():
            self.inputs[str(path)] = c.sha(path)
            with zipfile.ZipFile(path) as archive:
                return str(path), {integration.safe_member(i.filename): archive_read(archive, i)
                                   for i in archive.infolist() if not i.is_dir()}
        found = self.disc2.get((folder.casefold(), name.casefold()))
        if found is None:
            raise c.MappingError(f"No FM3 source for {folder}/{name}")
        origin, archive, infos = found
        members = {}
        for info in infos:
            member = PurePosixPath(*integration.safe_member(info.filename).parts[3:])
            if member in members:
                raise c.MappingError("Duplicate member in "+origin)
            members[member] = archive_read(archive, info)
        return origin, members


def installed_content(content_root):
    """Reserved keys, registry rows and wheel folders of every installed DLC pack."""
    reserved, registry, wheels, overlays = defaultdict(set), defaultdict(list), {}, []
    for path in sorted(Path(content_root).glob("*/Media/DLCZips/*.zip")) if content_root else ():
        overlays.append(path)
        origin = f"{path.parents[2].name}/{path.name}"
        with zipfile.ZipFile(path) as z:
            for name in z.namelist():
                parts = name.replace("\\", "/").split("/")
                if len(parts) > 3 and [p.casefold() for p in parts[:2]] == ["media", "wheels"]:
                    wheels.setdefault(parts[2].casefold(), (path, origin))
                if not name.lower().endswith("_merge.slt"):
                    continue
                with closing(sqlite3.connect(":memory:")) as db:
                    db.row_factory = sqlite3.Row
                    db.deserialize(archive_read(z, name))
                    for table, info in c.schema(db).items():
                        keys = {x["name"] for x in info["columns"]} & {"Id", "ID", "Ordinal"}
                        for row in map(dict, db.execute("SELECT * FROM "+c.qi(table))):
                            registry[table].append((origin, row))
                            for key in keys:
                                reserved[table].add(row[key])
    return reserved, registry, wheels, overlays


def missing_cars(source_db, target_db, registry):
    """FM3 stock cars neither the FM4 disc nor an installed DLC patch defines."""
    known = {r[0].casefold() for r in target_db.execute("SELECT MediaName FROM Data_Car")}
    known |= {row["MediaName"].casefold() for _, row in registry.get("Data_Car", ())}
    return [r[0] for r in source_db.execute("SELECT MediaName FROM Data_Car ORDER BY Id")
            if r[0].casefold() not in known]


def names(source_root, source_car):
    """FM3's own English names, marked as imported."""
    with zipfile.ZipFile(Path(source_root)/"StringTables/EN.zip") as z:
        table = ui_names.StringTable(archive_read(z, "Data_Car.str"))
    out = {}
    for field in ("DisplayName", "ModelShort"):
        text = table.texts.get(ui_names.reference(source_car[field]) & 65535)
        if not text:
            raise c.MappingError(f"No English {field} for {source_car['MediaName']}")
        out[field] = text+" (FM3)"
    return out


def native_wheel(target_root, dlc_wheels, wheel):
    """(origin, {Media/Wheels/... : bytes}) when FM4 already ships the wheel."""
    path = Path(target_root)/"Wheels"/(wheel+".zip")
    found = dlc_wheels.get(wheel.casefold())
    if not path.exists() and found is None:
        return None
    archive_path, origin = (path, None) if path.exists() else found
    payloads = {}
    with zipfile.ZipFile(archive_path) as z:
        for info in z.infolist():
            parts = integration.safe_member(info.filename).parts
            if info.is_dir():
                continue
            if path.exists():
                payloads[Path("Media/Wheels")/wheel/Path(*parts)] = archive_read(z, info)
            elif [p.casefold() for p in parts[:3]] == ["media", "wheels", wheel.casefold()]:
                payloads[Path("Media/Wheels")/wheel/Path(*parts[3:])] = archive_read(z, info)
    return origin, payloads


def build(source, target, out, helper, medias=None, rules=None, pi_model=None, content_root=None,
          scales=None, physics_scales=False, disc2=FM3_DISC2_DEFAULT, log=print, progress=None):
    """`progress`: called after each car with {index, total, car, status, error}."""
    source, target, out = (Path(p).resolve() for p in (source, target, out))
    for original in (source.parents[2], target.parents[2]):
        if out == original or out in original.parents or original in out.parents:
            raise c.MappingError("Package output must be outside original game directories")
    if out.exists():
        raise c.MappingError("Choose a new package directory")
    load = lambda p: json.loads(Path(p).read_text(encoding="utf-8")) if p else None
    rule_data, pi_data, scale_data = load(rules), load(pi_model), load(scales)
    source_root, target_root = source.parents[1], target.parents[1]
    reserved, registry, dlc_wheels, overlays = installed_content(content_root)
    sources = Sources(source_root, disc2)
    tables, _ = ui_names.winning_tables(target_root, content_root, archive_read, c.sha)
    taken_keys = {k for _, _, _, data in tables.values() for k in ui_names.StringTable(data).texts}
    files, reports = out/"files", out/"reports"
    media_root = files/"Media"
    (media_root/"DB").mkdir(parents=True)
    reports.mkdir()
    database = media_root/"DB/gamedb.slt"
    shutil.copyfile(target, database)
    manifest_data = (target_root/"zipmanifest.xml").read_bytes()
    inputs = {str(source):c.sha(source), str(target):c.sha(target)}
    cars, bindings, thumbnails, wheels, archives = [], {}, {}, {}, {}

    def ship(relative, data, replace=False):
        # replace: a package under this one (a stacked install) shipped the archive; `data`
        # holds its members too (stack.extend) and takes over its mount.
        nonlocal manifest_data
        if (target_root.parent/relative).exists() and not replace:
            raise c.MappingError(f"Refusing to replace an existing asset: {relative}")
        manifest_data = integration.extend_zip_manifest(manifest_data, {relative:data},
                                                        (relative,) if replace else ())
        (files/relative).parent.mkdir(parents=True, exist_ok=True)
        with (files/relative).open("xb") as f:
            f.write(data)
        archives[relative.as_posix()] = c.sha(files/relative)

    with closing(c.connect(source)) as a, closing(sqlite3.connect(database)) as work:
        work.row_factory = sqlite3.Row
        medias = list(medias or missing_cars(a, work, registry))
        for number, media in enumerate(medias, 1):
            record = {"media":media}
            cars.append(record)
            try:
                car_reports = reports/media
                car_reports.mkdir()
                source_car = c.extract_stock(a, media)["nodes"]["car"]["row"]
                label = names(source_root, source_car)
                src, plan = integration.build_plan(a, work, media, rule_data, label, pi_data, scale_data,
                                                   physics_scales, reserved, registry)
                collisions = offline_package.overlay_collisions(plan, overlays)
                car_row = plan["candidate"]["nodes"]["car"]["row"]
                for field, value in ui_names.rekey(plan["integration"]["localized_names"], taken_keys).items():
                    plan["integration"]["metadata_changes"].append(
                        {"role":"car", "column":field, "before":car_row[field], "after":value,
                         "reason":"string key already used by installed FM4 content"})
                    car_row[field] = value
                    for mapping in plan["mapping"]:
                        if mapping["role"] == "car" and mapping["target_column"] == field:
                            mapping["target_value"] = value
                requires = {x["requires"] for x in plan["external_dependencies"] if x.get("requires")}
                wheel = src["nodes"]["wheel"]["row"]["MediaName"]
                origin, members = sources.members("Cars", media)
                payloads = {Path("Media/Cars")/media/Path(*m.parts):d for m, d in members.items()}
                assets = [{"path":p.as_posix(), "bytes":len(d), "source":origin} for p, d in payloads.items()]
                references, wheel_status = None, "converted"
                native = native_wheel(target_root, dlc_wheels, wheel)
                if native is not None:
                    wheel_origin, references = native
                    wheel_status = "native_fm4" if wheel_origin is None else "installed_dlc"
                    if wheel_origin:
                        requires.add(wheel_origin)
                elif wheel.casefold() in wheels:
                    references, wheel_status = wheels[wheel.casefold()][1], "shared_in_package"
                else:
                    wheel_origin, members = sources.members("Wheels", wheel)
                    for m, d in members.items():
                        payloads[Path("Media/Wheels")/wheel/Path(*m.parts)] = d
                        assets.append({"path":f"Media/Wheels/{wheel}/{m.as_posix()}", "bytes":len(d),
                                       "source":wheel_origin})
                thumb_path = THUMBNAILS/f"Thumbnail_{source_car['Id']}.xds"
                with zipfile.ZipFile(source_root/"UI/Textures.zip") as z:
                    payloads[thumb_path] = archive_read(z, thumb_path.relative_to("Media/UI/Textures").as_posix())
                converted, asset_validation, appearance, thumbnail = integration.convert_assets(
                    payloads, target_root, media, wheel, helper, thumb_path, inputs, references)
                c.write_patch(car_reports/"stock.slt", work, plan["candidate"])
                validation = c.validate(plan["candidate"], work, car_reports/"stock.slt", src)
                if not validation["passed"]:
                    raise c.MappingError(str(validation["issues"]))
                rows = list(plan["candidate"]["nodes"].values())+plan["integration"]["presentation_rows"]
                with work:
                    inserted = integration.insert_rows(work, rows)
                    if c.extract_stock(work, media)["nodes"] != plan["candidate"]["nodes"]:
                        raise c.MappingError("Package database does not reproduce the planned stock graph")
                for field, row in plan["integration"]["localized_names"].items():
                    bindings[f"{media}/{field}"] = row
                thumbnails[thumb_path] = converted.pop(thumb_path)
                ship(Path("Media/Cars")/(media+".zip"),
                     integration.stored_zip(converted, Path("Media/Cars")/media))
                if wheel_status == "converted":
                    wheel_payloads = {p:d for p, d in converted.items() if p.is_relative_to(Path("Media/Wheels")/wheel)}
                    ship(Path("Media/Wheels")/(wheel+".zip"),
                         integration.stored_zip(wheel_payloads, Path("Media/Wheels")/wheel))
                    wheels[wheel.casefold()] = (media, wheel_payloads)
                for name, value in (("source_ir", src), ("result", plan), ("assets", assets),
                                    ("asset_validation", asset_validation),
                                    ("appearance_validation", appearance),
                                    ("ui_thumbnail_validation", thumbnail), ("validation", validation),
                                    ("dlc_collisions", collisions)):
                    c.dump(car_reports/(name+".json"), value)
                record.update(status="packaged", car_id=source_car["Id"], names=label, wheel=wheel,
                              wheel_source=wheel_status, requires=sorted(requires), merged_rows=inserted,
                              class_id=plan["candidate"]["nodes"]["car"]["row"]["ClassID"],
                              performance_index=plan["candidate"]["nodes"]["car"]["row"]["PerformanceIndex"])
                log(f"[{number}/{len(medias)}] {media}: packaged ({wheel_status})")
                if progress:
                    progress(dict(index=number, total=len(medias), car=media, status="packaged", error=None))
            except Exception as error:
                record.update(status="failed", error=f"{type(error).__name__}: {error}"[:2000])
                (reports/media).mkdir(exist_ok=True)
                (reports/media/"error.txt").write_text(traceback.format_exc(), encoding="utf-8")
                log(f"[{number}/{len(medias)}] {media}: FAILED {record['error'][:200]}")
                if progress:
                    progress(dict(index=number, total=len(medias), car=media, status="failed",
                                  error=record["error"]))
        packaged = [r for r in cars if r["status"] == "packaged"]
        if not packaged:
            raise c.MappingError("No car could be packaged")
        if work.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise c.MappingError("Package database failed integrity_check")
    merged, stacked = stack.extend(target_root.parent, THUMBNAILS.with_suffix(".zip"),
                                   {p.relative_to(THUMBNAILS).as_posix():d for p, d in thumbnails.items()})
    ship(THUMBNAILS.with_suffix(".zip"), integration.stored_zip({THUMBNAILS/n:d for n, d in merged.items()}, THUMBNAILS),
         stacked)
    name_archives, name_validation = ui_names.build_archives(
        source_root, target_root, bindings, archive_read, c.sha, content_root)
    inputs.update(name_validation["inputs"])
    priority = name_validation["mount"]["priority"]
    stacked = stack.mounted(manifest_data, ui_names.OVERRIDE) is not None
    manifest_data = integration.extend_zip_manifest(manifest_data, name_archives,
                                                    (ui_names.OVERRIDE,) if stacked else (),
                                                    {ui_names.OVERRIDE:priority})
    for relative, data in name_archives.items():
        with (files/relative).open("xb") as f:
            f.write(data)
        archives[relative.as_posix()] = c.sha(files/relative)
    with (media_root/"zipmanifest.xml").open("xb") as f:
        f.write(manifest_data)
    inputs.update(sources.inputs)
    for path, digest in inputs.items():
        if c.sha(path) != digest:
            raise c.MappingError(f"Input changed during packaging: {path}")
    c.dump(reports/"ui_name_validation.json", name_validation)
    manifest = {
        "package_type":"Offline file overlay; not a complete game disc",
        "cars":cars, "packaged":len(packaged), "failed":len(cars)-len(packaged),
        "requires":sorted({x for r in packaged for x in r["requires"]}),
        "inputs":inputs, "sources_unchanged":True, "overlays_checked":len(overlays),
        "options":{"rules":str(rules) if rules else None, "pi_model":str(pi_model) if pi_model else None,
                   "value_scales":str(scales) if scales else None, "physics_scales":physics_scales,
                   "content_root":str(content_root) if content_root else None},
        "merged_database_sha256":c.sha(database), "zip_manifest_sha256":c.sha(media_root/"zipmanifest.xml"),
        "archives":archives, "installed":False, "accepted":False, "runtime_tested":False,
        "files":{p.relative_to(files).as_posix():c.sha(p) for p in files.rglob("*") if p.is_file()},
    }
    c.dump(out/"manifest.json", manifest)
    return manifest


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--fm3", type=Path, default=c.FM3_DEFAULT)
    p.add_argument("--fm4", type=Path, default=c.FM4_DEFAULT)
    p.add_argument("--fm3-disc2", type=Path, default=FM3_DISC2_DEFAULT,
                   help="FM3 Disc 2 content packages (...\\4D53084D\\00000002)")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--model-helper", type=Path, required=True)
    p.add_argument("--media-name", action="append",
                   help="car to import (repeatable); default: every FM3 car FM4 and its DLC lack")
    p.add_argument("--rules", type=Path)
    p.add_argument("--pi-model", type=Path)
    p.add_argument("--content-root", type=Path,
                   help="installed content packages (...\\4D530910\\00000002)")
    p.add_argument("--value-scales", type=Path)
    p.add_argument("--physics-scales", action="store_true")
    a = p.parse_args()
    r = build(a.fm3, a.fm4, a.out, a.model_helper, a.media_name, a.rules, a.pi_model, a.content_root,
              a.value_scales, a.physics_scales, a.fm3_disc2, log=lambda s: print(s, flush=True))
    print(json.dumps({k:r[k] for k in ("packaged", "failed", "requires")}, indent=2))
