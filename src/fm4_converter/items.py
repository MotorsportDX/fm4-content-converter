"""Independent mod packages (`mod.json` format 2): what each car or track of a package adds.

A format 2 package is built on FM4 Disc 1 alone and never ships the files every package would
write (`gamedb.slt`, `zipmanifest.xml`, `stringtables.zip`, the shared archives). It lists its
items instead: a car, a track environment or a single layout, each with

- `identity`: the car IDs, track IDs and environment MediaNames it defines. Two packages that
  define the same identity hold the same car or track; `fm4_converter.compose` keeps the one of
  the newer game.
- `rows`: the database rows it inserts, `updates`: the rows of Disc 1 it changes (both as
  {table, row}); `renumber`: the keys `compose` may move when another item took them, with the
  columns of this item's rows that point at them.
- `strings`: its names ({table, key, page, symbol, texts, refs, reuse}): `compose` adds them to
  the string tables the game reads then, on a free key, and points `refs` at that key.
- `files`: whole files ({path: mount priority or None for a loose file}), and `members`: its
  members of the shared archives ({archive: [member names]}), both stored under `files/`.

`Recorder` captures the rows with temporary SQLite triggers while a builder inserts them into
its working database, so every row an item adds is listed, also those a builder writes
indirectly. See docs/mod-format.md.
"""
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
import xml.etree.ElementTree as ET
import zipfile

from .fm3.integration import archive_read

FORMAT, VERSION = "fm4-mod", 2
CONVERTER = "fm4-content-converter"
# A newer game's car or track replaces an older game's (compose).
PRIORITY = {"FM2": 20, "FM3": 30}
LOG = "fm4_items_log"


def qi(name):
    return '"' + name.replace('"', '""') + '"'


class Recorder:
    """Rows inserted into, or changed in, an open database between `start` and `take`."""

    def __init__(self, db):
        self.db = db
        tables = [r[0] for r in db.execute(
            "SELECT name FROM main.sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        db.execute(f"CREATE TEMP TABLE IF NOT EXISTS {LOG} (seq INTEGER PRIMARY KEY, tab TEXT, id INTEGER, op TEXT)")
        self.tables = tables
        for number, table in enumerate(tables):
            for op, event in (("i", "INSERT"), ("u", "UPDATE")):
                db.execute(f"CREATE TEMP TRIGGER IF NOT EXISTS fm4_items_{op}{number} AFTER {event} ON main.{qi(table)} "
                           f"BEGIN INSERT INTO {LOG} (tab, id, op) VALUES ({_literal(table)}, NEW.rowid, '{op}'); END")
        self.start()

    def start(self):
        self.db.execute(f"DELETE FROM {LOG}")

    def take(self):
        """(inserted, updated): [{table, row}] since `start`, in insertion order; a row inserted and
        then changed counts as inserted with its last values."""
        log = self.db.execute(f"SELECT tab, id, op FROM {LOG} ORDER BY seq").fetchall()
        inserted, updated = {}, {}
        for table, rowid, op in log:
            key = (table, rowid)
            if op == "i":
                inserted[key] = None
            elif key not in inserted:
                updated[key] = None
        out = ([], [])
        for target, keys in zip(out, (inserted, updated)):
            for table, rowid in keys:
                row = self.row(table, rowid)
                if row is not None:
                    target.append({"table": table, "row": row})
        self.start()
        return out

    def row(self, table, rowid):
        cursor = self.db.execute(f"SELECT * FROM main.{qi(table)} WHERE rowid=?", (rowid,))
        found = cursor.fetchone()
        if found is None:
            return None
        return dict(zip([d[0] for d in cursor.description], found))

    def close(self):
        for number in range(len(self.tables)):
            self.db.execute(f"DROP TRIGGER IF EXISTS temp.fm4_items_i{number}")
            self.db.execute(f"DROP TRIGGER IF EXISTS temp.fm4_items_u{number}")
        self.db.execute(f"DROP TABLE IF EXISTS temp.{LOG}")


def _literal(text):
    return "'" + text.replace("'", "''") + "'"


def item(key, kind, media, name=None, status="packaged", requires=(), identity=None, error=None):
    """An item record; the builder fills rows, updates, strings, files and members."""
    return dict(key=key, kind=kind, media=media, name=name, status=status, requires=sorted(requires),
                identity=identity or {}, rows=[], updates=[], renumber=[], strings=[], files={}, members={},
                error=error)


def car_identity(car_id, media):
    return {"cars": [int(car_id)], "car_media": [media]}


# A car's presentation rows carry an ID of their own that nothing refers to; builders give them
# Disc 1's next free ID, which another package's car can have taken too.
LEAF_KEYS = {"CarPartPositions": "ID", "Combo_Colors": "ID", "Combo_Colors_Exceptions": "ID"}
# Data_Car.str keys sit on this page (the upper word of an `_&decimal` reference).
DATA_CAR_PAGE = 0xCD49


def key_spec(table, column, rows, refs=()):
    """A key `compose` may move: the item rows (indexes) that hold it in `column`, and the
    [row index, column] pairs that refer to it."""
    return {"table": table, "column": column, "rows": sorted(set(rows)), "refs": [list(r) for r in refs]}


def graph_keys(graph, rows, car_id):
    """The movable keys of a car's stock graph (`converter.extract_stock` of the package database
    after the car is inserted) among the item's `rows`: every node but the car row and rows keyed
    by the car's ID, with the graph's edges as their references; and the presentation rows'
    own IDs (LEAF_KEYS)."""
    index = {}
    for number, entry in enumerate(rows):
        index.setdefault(entry["table"], []).append(number)

    def where(table, pk, value):
        return [n for n in index.get(table, ()) if rows[n]["row"].get(pk) == value]

    specs, by_node = {}, {}
    for role, node in graph["nodes"].items():
        table, pk = node["table"], node["pk"]
        value = node["row"][pk]
        if table == "Data_Car" or value == car_id:
            continue
        holders = where(table, pk, value)
        if not holders:
            continue   # a row the item does not insert (FM4's own, or one it updates)
        spec = specs.setdefault((table, pk, value), key_spec(table, pk, holders))
        by_node[role] = spec
    for edge in graph["edges"]:
        spec = by_node.get(edge["to"])
        source = graph["nodes"].get(edge["from"])
        if spec is None or source is None:
            continue
        for number in where(source["table"], source["pk"], source["row"][source["pk"]]):
            pair = [number, edge["column"]]
            if pair not in spec["refs"]:
                spec["refs"].append(pair)
    out = list(specs.values())
    for table, column in LEAF_KEYS.items():
        for number in index.get(table, ()):
            out.append(key_spec(table, column, [number]))
    return out


def reference_key(reference):
    if not isinstance(reference, str) or not reference.startswith("_&"):
        raise ValueError(f"Not a string reference: {reference!r}")
    return int(reference[2:])


def row_index(rows, table, column, value):
    found = [n for n, entry in enumerate(rows) if entry["table"] == table and entry["row"].get(column) == value]
    if len(found) != 1:
        raise ValueError(f"Expected one {table} row with {column}={value}, found {len(found)}")
    return found[0]


def string(table, reference, symbol, texts, refs, reuse=False):
    """An item string: `texts` {language code (lower case) or "*": text}; `refs`: [row index,
    column] of the item rows that hold its reference. `reuse`: a key FM4 already has is FM4's
    own name of the same thing, kept as it is."""
    full = reference_key(reference)
    return {"table": table, "key": full & 65535, "page": full >> 16, "symbol": symbol, "texts": dict(texts),
            "reuse": reuse, "refs": [list(r) for r in refs]}


def car_string(field, binding, rows, car_id):
    """A Data_Car name (`DisplayName` or `ModelShort`): one text for every language."""
    return string("Data_Car.str", binding["reference"], binding["symbol"], {"*": binding["text"]},
                  [[row_index(rows, "Data_Car", "Id", car_id), field]])


def mounts(manifest):
    """{guest path (case-folded): priority} of a zipmanifest.xml (bytes)."""
    return {node.attrib["path"].casefold(): int(node.attrib["priority"])
            for node in ET.fromstring(manifest).findall("Zip")}


def guest(relative):
    return "game:\\" + str(PurePosixPath(relative)).replace("/", "\\").lower()


def file_sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def converter_version():
    try:
        from importlib.metadata import version
        return version(CONVERTER)
    except Exception:   # noqa: BLE001 - an uninstalled checkout still writes a mod
        return None


def write(out, stage_files, items, archives, header):
    """Write the format 2 package `out` from a builder's staged files.

    `stage_files`: the folder the builder wrote its files into (FM4 Disc 1 layout); only the
    files and archive members the items name are taken from it. `archives`: {shared archive
    path: {"priority": mount priority, "root": the folder its members sit in}}; each item's
    `members` name members of these archives, which are stored as `files/<archive>/<member>`.
    `header`: the mod.json fields of the package (id, name, kind, source_game, sources, ...).
    Returns mod.json."""
    out, stage_files = Path(out), Path(stage_files)
    files = out / "files"
    files.mkdir(parents=True, exist_ok=True)
    opened = {}

    def archive(relative):
        if relative not in opened:
            with zipfile.ZipFile(stage_files / relative) as z:
                opened[relative] = {i.filename.casefold(): (i.filename, archive_read(z, i))
                                    for i in z.infolist() if not i.is_dir()}
        return opened[relative]

    for record in items:
        if record["status"] != "packaged":
            continue
        for relative in record["files"]:
            source, target = stage_files / relative, files / relative
            if not source.is_file():
                raise ValueError(f"{record['key']}: no staged file {relative}")
            if not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
        for relative, names in record["members"].items():
            if relative not in archives:
                raise ValueError(f"{record['key']}: {relative} is not a shared archive of the package")
            content = archive(relative)
            kept = []
            for name in names:
                found = content.get(name.casefold())
                if found is None:
                    raise ValueError(f"{record['key']}: no member {name} in {relative}")
                target = files / relative / found[0]
                target.parent.mkdir(parents=True, exist_ok=True)
                if not target.exists():
                    target.write_bytes(found[1])
                kept.append(found[0])
            record["members"][relative] = kept
    (out / "items.json").write_text(json.dumps(items, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    entries = {p.relative_to(files).as_posix(): dict(sha256=file_sha(p), size=p.stat().st_size)
               for p in sorted(files.rglob("*")) if p.is_file()}
    packaged = [r for r in items if r["status"] == "packaged"]
    if not packaged:
        raise ValueError("The package has no item")
    mod = {
        "format": FORMAT, "format_version": VERSION,
        **header,
        "priority": PRIORITY[header["source_game"]],
        "created": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "converter": {"name": CONVERTER, "version": converter_version()},
        "experimental": True,
        "files_root": "files",
        "files": entries,
        "items_file": "items.json", "items_sha256": file_sha(out / "items.json"),
        "archives": archives,
        "packaged": len(packaged), "failed": sum(r["status"] == "failed" for r in items),
        "skipped": sum(r["status"] == "skipped" for r in items),
        "requires": sorted({x for r in packaged for x in r["requires"]}),
        "cars": [_summary(r) for r in items if r["kind"] == "car"],
        "tracks": [_summary(r) for r in items if r["kind"] != "car"],
    }
    (out / "mod.json").write_text(json.dumps(mod, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return mod


def _summary(record):
    return {k: record.get(k) for k in ("key", "media", "name", "status", "requires", "identity", "error")}


class ModError(ValueError):
    pass


def load(package):
    package = Path(package)
    mod = json.loads((package / "mod.json").read_text(encoding="utf-8"))
    if mod.get("format") != FORMAT:
        raise ModError("Not an fm4-mod package")
    if mod.get("format_version") != VERSION:
        raise ModError(f"{package.name}: fm4-mod version {mod.get('format_version')}; convert it again")
    return mod


def load_items(package, mod=None):
    package = Path(package)
    mod = mod or load(package)
    path = package / mod["items_file"]
    if file_sha(path) != mod["items_sha256"]:
        raise ModError(f"{package.name}: {mod['items_file']} changed")
    return json.loads(path.read_text(encoding="utf-8"))


def verify(package):
    """Every listed file present with its size and SHA-256, nothing else in files/, and the item
    list unchanged. Returns mod.json; raises ModError on the first difference."""
    package = Path(package)
    mod = load(package)
    root = package / mod["files_root"]
    for relative, entry in mod["files"].items():
        parts = PurePosixPath(relative)
        if parts.is_absolute() or ".." in parts.parts or ":" in relative:
            raise ModError(f"Unsafe path {relative}")
        path = root / parts
        if not path.is_file() or path.stat().st_size != entry["size"] or file_sha(path) != entry["sha256"]:
            raise ModError(f"{relative} is missing or changed")
    extra = sorted({p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()} - set(mod["files"]))
    if extra:
        raise ModError(f"Files not listed in mod.json: {extra[:5]}")
    load_items(package, mod)
    return mod


def open_db(path):
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    return closing(db)
