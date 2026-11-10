"""Compose independent mod packages (format 2) over FM4 Disc 1 into one overlay.

FM4 reads one database, one archive list and one name override. Each format 2 package was built
on FM4 Disc 1 alone (`fm4_converter.items`), so any set of them plays together once composed:

1. Items: a newer game's item replaces an older game's that shares an identity (a car ID or
   MediaName, a track ID, an environment): the package with the higher `priority` wins (FM3
   over FM2). An installed FM4 DLC pack that defines the car or track wins over every package,
   and an item whose `requires` names a pack that is not installed is left out.
2. Database: Disc 1's `gamedb.slt` with the winners' rows and updates. Keys an item lets move
   (`renumber`) get the next free key when another row, or an installed DLC pack, holds theirs.
   Any other key that is taken stops the compose.
3. Names: per string table, the winners' names on their own keys when free (a key FM4 already
   has is reused when the item says so), else on the highest free key; the rows that refer to
   them are pointed at that key. `Media/stringtables.zip` carries these tables over the ones the
   game reads now (Disc 1, Disc 2 and the installed DLC), one priority above them.
4. Archives: the shared archives (thumbnails, car audio, track AI, UI folders) hold the winners'
   members, over Disc 1's members when Disc 1 has that archive; the winners' whole files are
   linked; `zipmanifest.xml` mounts them all.

The overlay is written into a new folder in FM4 Disc 1's layout, with `compose.json`, the report:
the winners, the items left out and why, and every file the overlay holds.

  python -m fm4_converter.compose --fm4 <FM4 Disc 1> --out <new folder> [--content-root <...>]
      <package> [<package> ...]
"""
import argparse
import io
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
import struct
import sys
import xml.etree.ElementTree as ET
import zipfile

from . import items as it
from .fm3 import batch_package, ui_names
from .fm3 import converter as c
from .fm3.integration import archive_read

OVERRIDE = ui_names.OVERRIDE


class ComposeError(ValueError):
    pass


def identities(record):
    ident = record.get("identity") or {}
    out = {("car", int(v)) for v in ident.get("cars", ())}
    out |= {("car_media", v.casefold()) for v in ident.get("car_media", ())}
    out |= {("track", int(v)) for v in ident.get("tracks", ())}
    out |= {("environment", v.casefold()) for v in ident.get("environments", ())}
    return out


def installed(content_root):
    """(identities the installed DLC packs define, their origins, reserved keys per table)."""
    reserved, registry, _, overlays = batch_package.installed_content(content_root)
    defined = {("car", int(r["Id"])) for _, r in registry.get("Data_Car", ())}
    defined |= {("car_media", r["MediaName"].casefold()) for _, r in registry.get("Data_Car", ())}
    defined |= {("track", int(r["id"])) for _, r in registry.get("Tracks", ())}
    defined |= {("environment", r["MediaName"].casefold()) for _, r in registry.get("Environments", ())}
    origins = {f"{p.parents[2].name}/{p.name}" for p in overlays}
    return defined, origins, reserved


def choose(packages, dlc, origins):
    """(winners [(package, mod, item)] in priority order, left out [{key, package, reason}])."""
    ordered = sorted(packages, key=lambda x: (x[1]["priority"], x[1].get("created", "")))
    eligible, out = [], []
    for number, (folder, mod, records) in enumerate(ordered):
        for record in records:
            if record["status"] != "packaged":
                continue
            # The DLC pack's own car or track wins; an item that needs a missing pack is left
            # out before the packages are compared, so an older game's item can stand in for it.
            if identities(record) & dlc:
                out.append(dict(key=record["key"], package=mod["id"], reason="an installed DLC pack has it"))
                continue
            missing = [r for r in record.get("requires", ()) if r not in origins]
            if missing:
                out.append(dict(key=record["key"], package=mod["id"],
                                reason="needs the DLC pack " + ", ".join(missing)))
                continue
            eligible.append((number, folder, mod, record))
    owner = {}
    for number, _, _, record in eligible:
        for identity in identities(record):
            owner[identity] = number   # ascending priority: the last package that has it wins
    winners = []
    for number, folder, mod, record in eligible:
        lost = sorted({owner[i] for i in identities(record) if owner[i] != number})
        if lost:
            out.append(dict(key=record["key"], package=mod["id"], reason=f"replaced by {ordered[lost[-1]][1]['id']}"))
            continue
        winners.append((folder, mod, record))
    return winners, out


def primary_key(db, table):
    keys = [r[1] for r in db.execute(f"PRAGMA table_info({c.qi(table)})") if r[5]]
    return keys[0] if len(keys) == 1 else None


def renumber(db, record, reserved):
    """Move the item's movable keys (`renumber`) that the database or an installed DLC pack holds
    to the next free key, in the rows that hold them and the rows that refer to them."""
    rows = record["rows"]
    pending, taken = {}, {}
    for spec in record.get("renumber", ()):
        for number in spec["rows"]:
            pending.setdefault(spec["table"], set()).add(rows[number]["row"][spec["column"]])
    moved = []
    for spec in record.get("renumber", ()):
        table, column = spec["table"], spec["column"]
        if spec.get("block"):
            # A block of values (Tracks.MPSortOrder): moved together to the next free block.
            values = [rows[n]["row"][column] for n in spec["rows"]]
            used = {r[0] for r in db.execute(f"SELECT {c.qi(column)} FROM {c.qi(table)}") if r[0] is not None}
            if used & set(values):
                low, step = min(values), spec["block"]
                start = (max(used) // step + 1) * step
                for n in spec["rows"]:
                    rows[n]["row"][column] = start + rows[n]["row"][column] - low
                moved.append({"table": table, "column": column, "from": low, "to": start})
            continue
        if (table, column) not in taken:
            taken[table, column] = {r[0] for r in db.execute(f"SELECT {c.qi(column)} FROM {c.qi(table)}")}
            taken[table, column] |= set(reserved.get(table, ()))
        held = taken[table, column]
        old = rows[spec["rows"][0]]["row"][column]
        if old not in held:
            held.add(old)
            continue
        new = old + 1
        while new in held or new in pending.get(table, ()):
            new += 1
        held.add(new)
        for number in spec["rows"]:
            rows[number]["row"][column] = new
        for number, ref in spec["refs"]:
            if rows[number]["row"].get(ref) != old:
                raise ComposeError(f"{record['key']}: {rows[number]['table']}.{ref} does not hold {table} {old}")
            rows[number]["row"][ref] = new
        moved.append({"table": table, "column": column, "from": old, "to": new})
    if moved:
        record["moved"] = moved


def insert(db, record):
    for entry in record["rows"]:
        table, row = entry["table"], entry["row"]
        key = primary_key(db, table)
        if key is not None:
            found = db.execute(f"SELECT * FROM {c.qi(table)} WHERE {c.qi(key)}=?", (row[key],)).fetchone()
            if found is not None:
                if dict(found) == row:
                    continue
                raise ComposeError(f"{record['key']}: {table} {key} {row[key]} is taken")
        db.execute(f"INSERT INTO {c.qi(table)} ({','.join(map(c.qi, row))}) VALUES ({','.join('?' * len(row))})",
                   tuple(row.values()))
    for entry in record["updates"]:
        table, row = entry["table"], entry["row"]
        key = primary_key(db, table)
        if key is None:
            raise ComposeError(f"{record['key']}: an update of {table}, which has no primary key")
        columns = [k for k in row if k != key]
        db.execute(f"UPDATE {c.qi(table)} SET " + ",".join(f"{c.qi(k)}=?" for k in columns)
                   + f" WHERE {c.qi(key)}=?", [row[k] for k in columns] + [row[key]])


class Names:
    """The winners' names, per string table, on free keys of the tables the game reads now."""

    def __init__(self, disc_media, content_root):
        self.disc_media, self.content_root = disc_media, content_root
        self.tables, self.priority = {}, 0

    def table(self, name):
        if name not in self.tables:
            winning, _ = ui_names.winning_tables(self.disc_media, self.content_root, archive_read, c.sha, name)
            self.priority = max(self.priority, max(entry[0] for entry in winning.values()))
            taken = set()
            for _, _, _, data in winning.values():
                taken |= set(ui_names.StringTable(data).texts)
            english = set(ui_names.StringTable(winning["en"][3]).texts)
            symbols = set()
            for _, _, _, data in winning.values():
                symbols |= set(ui_names.StringTable(data).names.values())
            self.tables[name] = {"winning": winning, "taken": taken, "english": english, "symbols": symbols,
                                 "additions": [], "moved": 0, "reused": 0}
        return self.tables[name]

    def assign(self, record):
        """Give each name of the item its key and write the reference into the item's rows."""
        rows = record["rows"]
        for string in record.get("strings", ()):
            table = self.table(string["table"])
            key = string["key"] & 65535
            if string.get("reuse") and key in table["english"]:
                table["reused"] += 1
            else:
                if key in table["taken"] or key in (0, 65535):
                    key = next((k for k in range(65534, 0, -1) if k not in table["taken"]), None)
                    if key is None:
                        raise ComposeError(f"No free key in {string['table']}")
                    table["moved"] += 1
                table["taken"].add(key)
                # A symbol the tables already have (a DLC pack's car of the same ID) gets a suffix.
                symbol, number = string["symbol"], 1
                while symbol in table["symbols"]:
                    number += 1
                    symbol = f"{string['symbol']}_{number}"
                table["symbols"].add(symbol)
                table["additions"].append(((string["page"] << 16) | key, symbol, string["texts"]))
            reference = f"_&{(string['page'] << 16) | key}"
            for number, column in string["refs"]:
                rows[number]["row"][column] = reference

    def archive(self):
        """(Media/stringtables.zip bytes, its priority, report); (None, None, report) without names."""
        report = {name: {"added": len(t["additions"]), "moved": t["moved"], "reused": t["reused"]}
                  for name, t in self.tables.items()}
        if not any(t["additions"] for t in self.tables.values()):
            return None, None, report
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as out:
            for name, table in sorted(self.tables.items()):
                if not table["additions"]:
                    continue
                for code, (_, language, _, data) in sorted(table["winning"].items()):
                    rows = [(full, symbol, texts.get(code) or texts.get("en") or texts["*"])
                            for full, symbol, texts in table["additions"]]
                    out.writestr(zipfile.ZipInfo(f"{language}/{name}", (1980, 1, 1, 0, 0, 0)),
                                 ui_names.StringTable(data).add(rows))
        return stream.getvalue(), self.priority + 1, report


def stored_zip(members):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as z:
        for name, data in sorted(members.items(), key=lambda x: x[0].casefold()):
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            z.writestr(info, data)
    return stream.getvalue()


def directory(path):
    """(dirstart, dirsize, entries) of a ZIP file in zipmanifest.xml's convention: FM4's own
    manifest counts the 22-byte end record in dirsize."""
    with open(path, "rb") as f:
        f.seek(-22, 2)
        end = f.read(22)
    if end[:4] != b"PK\x05\x06":
        raise ComposeError(f"{path}: no ZIP end record (a ZIP comment or ZIP64 is not mounted)")
    disk, cd_disk, n_disk, count, size, start, comment = struct.unpack_from("<4H2IH", end, 4)
    if disk or cd_disk or n_disk != count or comment:
        raise ComposeError(f"{path}: not a single-disk ZIP32")
    return start, size + 22, count


def manifest(original, mounts):
    """Disc 1's zipmanifest.xml (bytes) with `mounts` ({relative path: (priority, ZIP file)}):
    a path Disc 1 already mounts is taken over, the others are added."""
    tree = ET.fromstring(original)
    if tree.tag != "ZipFiles" or tree.attrib.get("version") != "3":
        raise ComposeError("Unsupported zipmanifest.xml")
    nodes = {node.attrib["path"].casefold(): node for node in tree.findall("Zip")}
    for relative, (priority, path) in sorted(mounts.items()):
        start, size, count = directory(path)
        guest = it.guest(relative)
        node = nodes.get(guest.casefold())
        if node is None:
            node = ET.SubElement(tree, "Zip", {"version": "1", "path": guest})
            nodes[guest.casefold()] = node
        node.attrib.update(priority=str(priority), dirstart=str(start), dirsize=str(size), direntries=str(count))
    return ET.tostring(tree, encoding="utf-8", xml_declaration=True)


def link(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(source, target)
    except OSError:
        shutil.copyfile(source, target)


def compose(fm4, packages, out, content_root=None):
    """Write the overlay of `packages` (folders) over the FM4 Disc 1 folder `fm4` into the new
    folder `out`; returns the report (also `out/compose.json`)."""
    fm4, out = Path(fm4), Path(out)
    if out.exists():
        raise ComposeError(f"{out} exists; choose a new folder")
    disc_media = fm4 / "Media"
    loaded = []
    for folder in packages:
        mod = it.verify(folder)
        loaded.append((Path(folder), mod, it.load_items(folder, mod)))
    ids = [mod["id"] for _, mod, _ in loaded]
    if len(set(ids)) != len(ids):
        raise ComposeError(f"Two packages share an id: {ids}")
    dlc, origins, reserved = installed(content_root)
    winners, left_out = choose(loaded, dlc, origins)
    stage = out.with_name(out.name + ".stage")
    shutil.rmtree(stage, ignore_errors=True)
    media = stage / "Media"
    (media / "DB").mkdir(parents=True)
    database = media / "DB/gamedb.slt"
    shutil.copyfile(disc_media / "DB/gamedb.slt", database)
    db = sqlite3.connect(database)
    db.row_factory = sqlite3.Row
    try:
        names = Names(disc_media, content_root)
        with db:
            for _, _, record in winners:
                renumber(db, record, reserved)
                names.assign(record)
                insert(db, record)
        strings, strings_priority, string_report = names.archive()
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ComposeError("The composed database failed integrity_check")
    finally:
        db.close()
    mounts, written = {}, {"Media/DB/gamedb.slt": "composed"}
    # Whole files: the winner of the highest priority writes a path several winners name.
    whole = {}
    for folder, mod, record in winners:
        for relative, priority in record["files"].items():
            whole[relative.casefold()] = (folder / mod["files_root"] / relative, relative, priority, mod["id"])
    for source, relative, priority, mod_id in whole.values():
        if (fm4 / relative).exists():
            raise ComposeError(f"{mod_id}: {relative} is a file of FM4 Disc 1")
        link(source, stage / relative)
        written[relative] = mod_id
        if priority is not None:
            mounts[relative] = (priority, stage / relative)
    # Shared archives: Disc 1's members, then the winners' in priority order.
    shared = {}
    for folder, mod, record in winners:
        for relative, members in record["members"].items():
            info = mod["archives"][relative]
            entry = shared.setdefault(relative.casefold(), {"relative": relative, "priority": 0, "members": {}})
            entry["priority"] = max(entry["priority"], info["priority"])
            for name in members:
                entry["members"][name.casefold()] = (name, folder / mod["files_root"] / relative / name)
    for entry in shared.values():
        relative = entry["relative"]
        content = {}
        if (fm4 / relative).is_file():
            with zipfile.ZipFile(fm4 / relative) as z:
                content = {i.filename: archive_read(z, i) for i in z.infolist() if not i.is_dir()}
        folded = {name.casefold(): name for name in content}
        for key, (name, path) in entry["members"].items():
            content.pop(folded.get(key, ""), None)
            content[name] = path.read_bytes()
        target = stage / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(stored_zip(content))
        written[relative] = "composed"
        mounts[relative] = (entry["priority"], target)
    if strings is not None:
        (stage / OVERRIDE).write_bytes(strings)
        written[OVERRIDE.as_posix()] = "composed"
        mounts[OVERRIDE.as_posix()] = (strings_priority, stage / OVERRIDE)
    (media / "zipmanifest.xml").write_bytes(manifest((disc_media / "zipmanifest.xml").read_bytes(), mounts))
    written["Media/zipmanifest.xml"] = "composed"
    report = {
        "fm4": str(fm4), "content_root": str(content_root) if content_root else None,
        "packages": [{"id": mod["id"], "priority": mod["priority"], "created": mod.get("created"),
                      "folder": str(folder)} for folder, mod, _ in loaded],
        "winners": [{"key": r["key"], "package": mod["id"], "media": r["media"], "kind": r["kind"],
                     **({"moved": r["moved"]} if r.get("moved") else {})} for _, mod, r in winners],
        "left_out": left_out,
        "names": string_report, "names_priority": strings_priority,
        "files": written,
    }
    (stage / "compose.json").write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(stage, out)
    return report


def main(argv=None):
    p = argparse.ArgumentParser(prog="fm4-compose", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--fm4", required=True, help="extracted FM4 Disc 1 folder")
    p.add_argument("--out", required=True, help="new overlay folder")
    p.add_argument("--content-root", help="installed FM4 DLC packs (...\\4D530910\\00000002)")
    p.add_argument("--json", action="store_true", help="print the report as JSON")
    p.add_argument("packages", nargs="+")
    a = p.parse_args(argv)
    try:
        report = compose(a.fm4, a.packages, a.out, a.content_root)
    except (ComposeError, it.ModError, OSError, ValueError) as error:
        print(json.dumps({"ok": False, "error": f"{type(error).__name__}: {error}"}))
        return 1
    if a.json:
        print(json.dumps({"ok": True, **report}, ensure_ascii=False))
    else:
        print(f"{len(report['winners'])} items composed, {len(report['left_out'])} left out")
    return 0


if __name__ == "__main__":
    sys.exit(main())
