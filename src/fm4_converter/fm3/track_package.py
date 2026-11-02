"""FM3 track layouts whose geometry FM4 still ships, as an FM4 test overlay.

Scope: a layout that only adds a ribbon folder (cameras, CollObjs) on top of
geometry FM4 already has (`Tracks.ReverseIndex`), e.g. CrownJewel 170, the
reverse Extreme Circuit FM4 dropped. FM4's database still carries the start grid,
merges, pit zone, split and graffiti rows for such IDs; this module refuses a
layout whose dependent rows FM4 lacks instead of synthesizing them. Visual track
conversion (RMB/BIX/PVS) is out of scope here.

The output is a `files/` overlay for `test_disc.py`: a merged gamedb.slt, ZIPs
of the ribbon XML, FM3 AI files and missing audio (mounted at their folders by
zipmanifest.xml; see mounted_archive) and a `Media/stringtables.zip` Tracks.str
override. CPU only; no game process, no install.

Runtime (Motorsport DX, 2 November 2026): CrownJewel 170 races with these ZIPs;
with the same files loose the title crashed loading the AI line
(research/tracks-2026-11-02/REPORT.md).
"""
from __future__ import annotations

from contextlib import closing
from pathlib import Path
import io
import re
import shutil
import sqlite3
import zipfile

from . import converter as c
from . import integration
from . import ui_names
from .integration import archive_read


# Copied from the FM3 row; every other FM4 column comes from the FM4 layout
# that already uses the same geometry ribbon (same circuit, logos, environment).
FROM_SOURCE = ("id", "DisplayName", "ShortDisplayName", "RibbonIndex", "ReverseIndex", "Length",
               "DefaultStartGridPositionsId", "FlyingStartPosId", "MPSortOrder", "WinningsScalar",
               "QuickRaceLapCount")
NAME_FIELDS = ("DisplayName", "ShortDisplayName")
# Rows FM4 must already hold for the layout ID (they are not generated here).
DEPENDENTS = (("TrackStartingMerges", "Tracks_id"), ("TrackPittingZones", "Tracks_id"),
              ("SplitPoints", "TrackId"), ("GraffitiPoints", "TrackId"))
GEOMETRY_SUFFIXES = (".col", ".pvs", ".crowd")


def track_row(db, layout):
    row = db.execute("SELECT * FROM Tracks WHERE id=?", (layout,)).fetchone()
    return dict(row) if row else None


def plan_row(source_db, target_db, layout):
    """FM4 Tracks row for an FM3 layout plus the evidence for each choice."""
    src = track_row(source_db, layout)
    if src is None:
        raise c.MappingError(f"FM3 has no track {layout}")
    if track_row(target_db, layout) is not None:
        raise c.MappingError(f"FM4 already has track {layout}")
    rib, geometry = src["RibbonIndex"], src["ReverseIndex"]
    if rib == geometry:
        raise c.MappingError("Layout has its own geometry ribbon; only geometry-sharing layouts are supported")
    templates = [dict(r) for r in target_db.execute(
        "SELECT * FROM Tracks WHERE MediaName=? COLLATE NOCASE AND RibbonIndex=? AND ReverseIndex=?",
        (src["MediaName"], geometry, geometry))]
    if len(templates) != 1:
        raise c.MappingError("Need exactly one FM4 forward layout on the geometry ribbon")
    template = templates[0]
    if template["EnvironmentId"] != src["EnvironmentId"]:
        raise c.MappingError("FM3 and FM4 environment IDs differ")
    row = dict(template)
    for column in FROM_SOURCE:
        row[column] = src[column]
    row["MediaName"] = template["MediaName"]
    # FM4 marks a layout reverse when it drives another ribbon's geometry.
    row["IsReverse"] = int(row["RibbonIndex"] != row["ReverseIndex"])
    if target_db.execute("SELECT 1 FROM Tracks WHERE MPSortOrder=?", (row["MPSortOrder"],)).fetchone():
        raise c.MappingError("MPSortOrder already used in FM4")
    for column in ("DefaultStartGridPositionsId", "FlyingStartPosId"):
        if not target_db.execute("SELECT count(*) FROM StartGridPositions WHERE id=?", (row[column],)).fetchone()[0]:
            raise c.MappingError(f"FM4 has no StartGridPositions {row[column]} for {column}")
    dependents = {}
    for table, column in DEPENDENTS:
        fm3 = sorted(tuple(r) for r in source_db.execute(f"SELECT * FROM {table} WHERE {column}=?", (layout,)))
        fm4 = [tuple(r) for r in target_db.execute(f"SELECT * FROM {table} WHERE {column}=?", (layout,))]
        if not fm4 and fm3:
            raise c.MappingError(f"FM4 lacks the {table} rows of layout {layout}")
        # FM4 prefixes some tables with its own row ID; compare the FM3 columns.
        same = sorted(r[-len(fm3[0]):] for r in fm4) == fm3 if fm3 and fm4 else fm3 == fm4
        dependents[table] = {"fm3_rows":len(fm3), "fm4_rows":len(fm4), "fm4_equals_fm3":same}
    shared = sorted(set(src) & set(row))
    return row, {
        "source_row":src, "template_id":template["id"], "from_source":list(FROM_SOURCE),
        "from_template":[k for k in row if k not in FROM_SOURCE and k not in ("IsReverse", "MediaName")],
        "derived":{"IsReverse":"RibbonIndex != ReverseIndex"},
        "differs_from_fm3":{k:{"fm3":src[k], "fm4":row[k]} for k in shared if src[k] != row[k]},
        "dependents":dependents,
    }


def find(folder, name):
    """Case-insensitive child lookup (both discs mix spellings)."""
    if not folder.is_dir():
        return None
    return next((p for p in folder.iterdir() if p.name.casefold() == name.casefold()), None)


OBJ = re.compile(rb'\t<Obj(\d+) PhysicsType="([^"]+)" GraphicsName="#(\d+)">\r?\n'
                 rb'\t\t<Pos x="([^"]+)" y="([^"]+)" z="([^"]+)"/>.*?</Obj\1>\r?\n', re.DOTALL)


def collobj_entries(path):
    data = path.read_bytes()
    entries = list(OBJ.finditer(data))
    head = data[:entries[0].start()] if entries else data
    if not entries or b"".join(m.group(0) for m in entries) != data[len(head):len(data)-len(b"</CollObjs>\r\n")] \
            or not data.endswith(b"</CollObjs>\r\n"):
        raise c.MappingError(f"Unrecognized CollObjs layout: {path}")
    return head, entries


def graphics_mapping(fm3_track, fm4_track):
    """FM3 -> FM4 GraphicsName indices of the track's collidable objects.

    FM4 renumbered the objects (FM4 dropped those only FM3's dropped layouts used),
    so an FM3 index can name another object or none. A pair is taken only where a
    ribbon both games ship places an object of the same type at byte-identical
    coordinates; the pairs must be unique and order-preserving."""
    mapping = {}
    for fm3_ribbon in sorted(p for p in fm3_track.iterdir() if p.is_dir()):
        fm4_ribbon = find(fm4_track, fm3_ribbon.name)
        a, b = find(fm3_ribbon, "CollObjs.xml"), find(fm4_ribbon, "CollObjs.xml") if fm4_ribbon else None
        if a is None or b is None:
            continue
        native = {}
        for m in collobj_entries(b)[1]:
            native.setdefault((m.group(2), m.group(4, 5, 6)), set()).add(int(m.group(3)))
        for m in collobj_entries(a)[1]:
            hit = native.get((m.group(2), m.group(4, 5, 6)))
            if hit and len(hit) == 1:
                index = next(iter(hit))
                if mapping.setdefault(int(m.group(3)), index) != index:
                    raise c.MappingError("Conflicting GraphicsName pairs")
    keys = sorted(mapping)
    if any(mapping[x] >= mapping[y] for x, y in zip(keys, keys[1:])):
        raise c.MappingError("GraphicsName pairs are not order-preserving")
    return mapping


def remap_collobjs(path, mapping):
    """FM3 CollObjs.xml with FM4 GraphicsName indices; objects without a proven
    FM4 index are left out (FM4's track model may no longer contain them)."""
    head, entries = collobj_entries(path)
    kept, dropped = [], []
    for m in entries:
        index = mapping.get(int(m.group(3)))
        if index is None:
            dropped.append({"obj":int(m.group(1)), "type":m.group(2).decode(), "fm3_graphics":int(m.group(3)),
                            "pos":[float(v) for v in m.group(4, 5, 6)]})
            continue
        number = len(kept)
        block = m.group(0)
        block = re.sub(rb'^\t<Obj\d+ ', b'\t<Obj%d ' % number, block)
        block = re.sub(rb'GraphicsName="#\d+"', b'GraphicsName="#%d"' % index, block, count=1)
        block = re.sub(rb'</Obj\d+>(\r?\n)$', rb'</Obj%d>\1' % number, block)
        kept.append(block)
    if not kept:
        raise c.MappingError("No CollObjs object could be mapped")
    return head + b"".join(kept) + b"</CollObjs>\r\n", {"kept":len(kept), "dropped":dropped}


def ribbon_files(fm3_tracks, fm4_tracks, media, ribbon, geometry):
    """Ribbon folder payloads. A file FM3 shares byte-for-byte with its geometry
    ribbon is taken from FM4's geometry ribbon (Turn 10's FM4 version of it);
    an FM3 CollObjs.xml gets FM4 GraphicsName indices (see graphics_mapping)."""
    source = find(find(fm3_tracks, media), f"Ribbon_{ribbon:02d}")
    target_track = find(fm4_tracks, media)
    if source is None or target_track is None:
        raise c.MappingError("Ribbon or track folder missing")
    if find(target_track, source.name) is not None:
        raise c.MappingError("FM4 already has this ribbon folder")
    fm3_geometry = find(find(fm3_tracks, media), f"Ribbon_{geometry:02d}")
    fm4_geometry = find(target_track, f"Ribbon_{geometry:02d}")
    for suffix in GEOMETRY_SUFFIXES:
        name = f"{media}_track_{geometry:02d}{suffix}" if suffix != ".pvs" else f"{media}_{geometry:02d}.pvs"
        if find(fm4_geometry, name) is None:
            raise c.MappingError(f"FM4 lacks geometry file {name}")
    payloads, records = {}, []
    for path in sorted(source.iterdir()):
        if path.suffix.casefold() in GEOMETRY_SUFFIXES:
            raise c.MappingError("Ribbon carries its own geometry; out of scope")
        data, origin = path.read_bytes(), "fm3"
        twin = find(fm3_geometry, path.name)
        native = find(fm4_geometry, path.name)
        remap = None
        if twin is not None and native is not None and twin.read_bytes() == data:
            data, origin = native.read_bytes(), "fm4_geometry_ribbon"
        elif path.name.casefold() == "collobjs.xml":
            data, remap = remap_collobjs(path, graphics_mapping(find(fm3_tracks, media), target_track))
            origin = "fm3_graphics_remapped"
        relative = Path("Media/tracks")/target_track.name/source.name/path.name
        payloads[relative] = data
        records.append({"path":relative.as_posix(), "origin":origin, "fm3":str(path),
                        "fm4":str(native) if origin == "fm4_geometry_ribbon" else None, "bytes":len(data),
                        **({"collobjs":remap} if remap else {})})
    return payloads, records


def audio_files(fm4_audio, media, ribbon, geometry):
    """FM4 audio kinds its ribbon folder lacks, copied from the geometry ribbon.

    FM4 added <media>ribbon_NNdecisionzones.xml (music zones by lap fraction) to
    every raceable ribbon; ribbon folders of dropped FM3 layouts still hold FM3's
    two files only. Several FM4 reverse layouts (Nurburgring 2-4, FujimiKaido
    1-4, 10, 11) use their geometry ribbon's zones byte-for-byte."""
    folder, source = find(fm4_audio, f"Ribbon_{ribbon:02d}"), find(fm4_audio, f"Ribbon_{geometry:02d}")
    if folder is None or source is None:
        raise c.MappingError("FM4 has no track audio for this ribbon or its geometry ribbon")
    prefix = f"{media}ribbon_{geometry:02d}".casefold()
    payloads, records = {}, []
    for path in sorted(source.iterdir()):
        if not path.name.casefold().startswith(prefix):
            raise c.MappingError(f"Unexpected audio file {path.name}")
        name = f"{media}ribbon_{ribbon:02d}{path.name[len(prefix):]}".lower()
        if find(folder, name) is not None:
            continue
        relative = Path("Media/audio/tracks")/fm4_audio.name/folder.name/name
        payloads[relative] = path.read_bytes()
        records.append({"path":relative.as_posix(), "origin":"fm4_geometry_ribbon", "fm4":str(path),
                        "bytes":len(payloads[relative])})
    return payloads, records


AI_NAME = r"{media}_{ribbon:02d}(_r)?\.(geo|irt|pit|seg|bin)"


def ai_files(fm3_ai, fm4_ai, media, ribbon):
    """FM3 AI line/segment files are copied as-is: FM4 kept them byte-identical
    for the layouts both games share (Tsukuba, CrownJewel 10/18)."""
    pattern = re.compile(AI_NAME.format(media=re.escape(media), ribbon=ribbon), re.IGNORECASE)
    payloads, records = {}, []
    for path in sorted(p for p in fm3_ai.rglob("*") if p.is_file()):
        relative = path.relative_to(fm3_ai)
        folder = relative.parts[:-1]
        hit = pattern.fullmatch(path.name) and (not folder or folder[0].casefold() in ("level1", "level2", "level3"))
        profile = (len(folder) == 2 and folder[0].casefold() == "segmentprofiles"
                   and re.fullmatch(rf"{re.escape(media)}_{ribbon:02d}(_r)?", folder[1], re.IGNORECASE))
        if not (hit or profile):
            continue
        existing = fm4_ai.joinpath(*relative.parts)
        if existing.exists():
            raise c.MappingError(f"FM4 already has AI file {relative.as_posix()}")
        target = Path("Media/AI/Tracks")/relative
        payloads[target] = path.read_bytes()
        records.append({"path":target.as_posix(), "fm3":str(path), "bytes":len(payloads[target])})
    kinds = {Path(r["path"]).suffix.casefold() for r in records}
    if not {".geo", ".irt", ".seg"} <= kinds:
        raise c.MappingError("FM3 AI line, IRT or segment file missing")
    return payloads, records


def name_archive(fm3_root, fm4_root, row, content_root):
    """Tracks.str override: each winning FM4 table plus the layout's two names,
    in that language when FM3 has it, otherwise English."""
    fm3_tables = {}
    for path in sorted((fm3_root/"StringTables").glob("*.zip")):
        with zipfile.ZipFile(path) as z:
            member = next((m for m in z.namelist() if m.casefold() == "tracks.str"), None)
            if member:
                fm3_tables[path.stem.casefold()] = ui_names.StringTable(archive_read(z, member))
    english = fm3_tables["en"]
    keys = {}
    for field in NAME_FIELDS:
        key = ui_names.reference(row[field])
        symbol = f"IDS_{field}_{row['id']}"
        if english.names.get(key & 65535) != symbol:
            raise c.MappingError(f"FM3 Tracks.str key of {field} is not {symbol}")
        keys[field] = (key, symbol)
    tables, inputs = ui_names.winning_tables(fm4_root, content_root, archive_read, c.sha, "Tracks.str")
    stream, languages = io.BytesIO(), []
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as output:
        for code, (priority, language, origin, data) in sorted(tables.items()):
            source = fm3_tables.get(code, english)
            additions = [(key, symbol, source.texts.get(key & 65535) or english.texts[key & 65535])
                         for key, symbol in keys.values()]
            table = ui_names.StringTable(data)
            encoded = table.add(additions)
            if any(ui_names.StringTable(encoded).texts[k] != v for k, v in table.texts.items()):
                raise c.MappingError("Existing localized text changed")
            output.writestr(zipfile.ZipInfo(f"{language}/Tracks.str", (1980, 1, 1, 0, 0, 0)), encoded)
            languages.append({"language":language, "winning_table":origin, "winning_priority":priority,
                              "text_language":code if code in fm3_tables else "en",
                              "added":{s:t for _, s, t in additions}, "existing_preserved":len(table.texts)})
    priority = max(r["winning_priority"] for r in languages)+1
    return stream.getvalue(), priority, {"languages":languages, "inputs":inputs,
                                         "mount":{"path":"game:\\media\\stringtables.zip", "priority":priority}}


def installed_track_ids(content_root):
    """Track IDs added by DB patches of installed packs (e.g. Launch Track Pack)."""
    ids = set()
    if not content_root:
        return ids
    for path in sorted(Path(content_root).glob("*/Media/DLCZips/*_pri_*.zip")):
        with zipfile.ZipFile(path) as z:
            for member in z.namelist():
                if not member.casefold().endswith("_merge.slt"):
                    continue
                import tempfile
                with tempfile.TemporaryDirectory() as tmp:
                    patch = Path(tmp)/"merge.slt"
                    patch.write_bytes(archive_read(z, member))
                    with closing(c.connect(patch)) as db:
                        if db.execute("SELECT 1 FROM sqlite_master WHERE name='Tracks'").fetchone():
                            ids |= {r[0] for r in db.execute("SELECT id FROM Tracks")}
    return ids


def mounted_archive(folder, payloads):
    """`<folder>.zip` holding `payloads` (paths under `folder`), for a zipmanifest
    mount at `<folder>\\`.

    FM4 does not find new loose files: with CrownJewel_19_r.geo loose in
    media\\AI\\Tracks the title searched only the DLC roots for it and crashed on
    the missing file, while the same files in a mounted ZIP loaded (Motorsport
    DX, 2 November 2026). Native loose files open without that search; the
    title's own list of disc files (likely hash.manifest) is the suspected cause."""
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as z:
        for path, data in sorted(payloads.items()):
            member = Path(path).relative_to(folder).as_posix()
            z.writestr(zipfile.ZipInfo(member, (1980, 1, 1, 0, 0, 0)), data)
    return Path(f"{folder}.zip"), stream.getvalue()


def build(layout, out, source=c.FM3_DEFAULT, target=c.FM4_DEFAULT, content_root=None):
    source, target, out = (Path(p).resolve() for p in (source, target, out))
    fm3_root, fm4_root = source.parents[1], target.parents[1]
    for original in (fm3_root.parent, fm4_root.parent):
        if out == original or original in out.parents or out in original.parents:
            raise c.MappingError("Package output must be outside original game directories")
    if out.exists():
        raise c.MappingError("Choose a new package directory")
    inputs = {str(source):c.sha(source), str(target):c.sha(target)}
    with closing(c.connect(source)) as a, closing(c.connect(target)) as b:
        row, evidence = plan_row(a, b, layout)
    if layout in installed_track_ids(content_root):
        raise c.MappingError(f"An installed pack already defines track {layout}")
    media = row["MediaName"]
    audio = find(find(find(fm4_root, "audio"), "Tracks"), media)
    if audio is None:
        raise c.MappingError("FM4 has no track audio for this track")
    ribbon, ribbon_records = ribbon_files(find(fm3_root, "Tracks"), find(fm4_root, "tracks"), media,
                                          row["RibbonIndex"], row["ReverseIndex"])
    ai, ai_records = ai_files(fm3_root/"AI/Tracks", fm4_root/"AI/Tracks", media, row["RibbonIndex"])
    sound, audio_records = audio_files(audio, media, row["RibbonIndex"], row["ReverseIndex"])
    payloads = {}
    for group, folder, group_records in ((ribbon, Path(next(iter(ribbon))).parent, ribbon_records),
                                         (ai, Path("Media/AI/Tracks"), ai_records),
                                         (sound, Path(next(iter(sound))).parent if sound else None, audio_records)):
        if not group:
            continue
        archive, data = mounted_archive(folder, group)
        if (fm4_root.parent/archive).exists():
            raise c.MappingError(f"FM4 already has {archive.as_posix()}")
        payloads[archive] = data
        for record in group_records:
            record["archive"] = archive.as_posix()
    names, priority, name_validation = name_archive(fm3_root, fm4_root, row, content_root)
    inputs.update(name_validation.pop("inputs"))
    manifest_data = integration.extend_zip_manifest((fm4_root/"zipmanifest.xml").read_bytes(),
                                                    {ui_names.OVERRIDE:names, **payloads}, (),
                                                    {ui_names.OVERRIDE:priority})
    files = out/"files"
    database = files/"Media/DB/gamedb.slt"
    database.parent.mkdir(parents=True)
    shutil.copyfile(target, database)
    with closing(sqlite3.connect(database)) as db:
        with db:
            columns = list(row)
            db.execute(f"INSERT INTO Tracks ({','.join(map(c.qi, columns))}) VALUES ({','.join('?'*len(columns))})",
                       [row[k] for k in columns])
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise c.MappingError("Merged database failed integrity_check")
        db.row_factory = sqlite3.Row
        if track_row(db, layout) != row:
            raise c.MappingError("Merged Tracks row does not read back")
    for relative, data in {**payloads, ui_names.OVERRIDE:names}.items():
        (files/relative).parent.mkdir(parents=True, exist_ok=True)
        with (files/relative).open("xb") as f:
            f.write(data)
    with (files/"Media/zipmanifest.xml").open("xb") as f:
        f.write(manifest_data)
    for path, digest in inputs.items():
        if c.sha(path) != digest:
            raise c.MappingError(f"Input changed during packaging: {path}")
    reports = out/"reports"
    reports.mkdir()
    c.dump(reports/"track_row.json", {"row":row, **evidence})
    c.dump(reports/"files.json", {"ribbon":ribbon_records, "ai":ai_records, "audio":audio_records})
    c.dump(reports/"ui_name_validation.json", name_validation)
    manifest = {
        "package_type":"Offline file overlay; not a complete game disc",
        "layout":layout, "media":media, "ribbon":row["RibbonIndex"], "geometry_ribbon":row["ReverseIndex"],
        "inputs":inputs, "sources_unchanged":True,
        "content_root":str(content_root) if content_root else None,
        "scope":("Tracks row + ribbon XML + FM3 AI + missing audio kinds from the geometry ribbon, "
                 "each group in a ZIP mounted at its folder, + Tracks.str override; geometry, visuals, "
                 "other audio and dependent DB rows are FM4's own. The stringtables.zip override is "
                 "bound to the given "
                 "content set and cannot be combined with a car package's Data_Car.str override as-is."),
        "installed":False, "accepted":False, "runtime_tested":False,
        "files":{p.relative_to(files).as_posix():c.sha(p) for p in sorted(files.rglob("*")) if p.is_file()},
    }
    c.dump(out/"manifest.json", manifest)
    return manifest


def main():
    import argparse, json
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--layout", type=int, required=True, help="FM3 Tracks.id, e.g. 170")
    p.add_argument("--fm3", type=Path, default=c.FM3_DEFAULT)
    p.add_argument("--fm4", type=Path, default=c.FM4_DEFAULT)
    p.add_argument("--content-root", type=Path, help="installed FM4 content (...\\4D530910\\00000002)")
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    manifest = build(a.layout, a.out, a.fm3, a.fm4, a.content_root)
    print(json.dumps({k:manifest[k] for k in ("layout", "media", "ribbon", "geometry_ribbon")}
                     | {"files":len(manifest["files"])}, indent=2))


if __name__ == "__main__":
    main()
