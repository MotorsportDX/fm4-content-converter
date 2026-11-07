"""The mod package format a launcher installs: `mod.json` beside the converter's `files/`.

`files/` mirrors the FM4 Disc 1 layout (`Media/...`). `mod.json` is the only file a launcher
needs to read; the converter's own `manifest.json` and `reports/` stay for review. See
docs/mod-format.md for the fields and the rules a launcher follows.

A file a mod `replaces` exists on FM4 Disc 1 (the merged database, `zipmanifest.xml`); a
file it `adds` does not. Two mods that write the same path cannot be installed together
until a launcher can merge them, so `writes` lists both for a quick conflict check.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath

FORMAT = "fm4-mod"
CONVERTER = "fm4-content-converter"
VERSION = 1


class ModError(ValueError):
    pass


def file_sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def converter_version():
    try:
        from importlib.metadata import version
        return version(CONVERTER)
    except Exception:   # noqa: BLE001 - an uninstalled checkout still writes a mod
        return None


def describe(package, mod_id, name, source, fm4_root, cars, requires, sources, built_against, notes=(),
             base_packages=(), kind="car-overlay"):
    """Write `package/mod.json` for a converter package and return it.

    `cars`: [{media, name, status, requires, error}]; `sources`: the discs read
    (`discs.Disc.describe`); `built_against`: the FM4 inputs the package depends on;
    `base_packages`: [{id, created}] of the packages `fm4_root` carried (a stacked install);
    `kind`: "car-overlay", or "track-overlay", whose `cars` are its environments (also as
    `tracks`)."""
    package, fm4_root = Path(package), Path(fm4_root)
    files = package / "files"
    entries, replaces, adds = {}, [], []
    for path in sorted(p for p in files.rglob("*") if p.is_file()):
        relative = path.relative_to(files).as_posix()
        entries[relative] = dict(sha256=file_sha(path), size=path.stat().st_size)
        (replaces if (fm4_root / relative).exists() else adds).append(relative)
    if not entries:
        raise ModError("The package has no files")
    mod = {
        "format": FORMAT, "format_version": VERSION,
        "id": mod_id, "name": name, "kind": kind, "source_game": source,
        "created": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "converter": {"name": CONVERTER, "version": converter_version()},
        "experimental": True,
        "files_root": "files",
        "replaces": replaces, "adds": adds, "writes": sorted(entries),
        "files": entries,
        "cars": [] if kind == "track-overlay" else cars,
        **({"tracks": cars} if kind == "track-overlay" else {}),
        "packaged": sum(c["status"] == "packaged" for c in cars),
        "failed": sum(c["status"] == "failed" for c in cars),
        "requires": sorted(requires),
        "sources": sources,
        "built_against": built_against,
        "base_packages": list(base_packages),
        "notes": list(notes),
    }
    (package / "mod.json").write_text(json.dumps(mod, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return mod


def load(package):
    mod = json.loads((Path(package) / "mod.json").read_text(encoding="utf-8"))
    if mod.get("format") != FORMAT:
        raise ModError("Not an fm4-mod package")
    if mod.get("format_version") != VERSION:
        raise ModError(f"Unsupported fm4-mod version {mod.get('format_version')}")
    return mod


def verify(package):
    """Check every listed file's size and SHA-256, and that no other file is in files/.
    Returns the mod; raises ModError on the first difference."""
    package = Path(package)
    mod = load(package)
    root = package / mod["files_root"]
    for relative, entry in mod["files"].items():
        parts = PurePosixPath(relative)
        if parts.is_absolute() or ".." in parts.parts:
            raise ModError(f"Unsafe path {relative}")
        path = root / parts
        if not path.is_file() or path.stat().st_size != entry["size"] or file_sha(path) != entry["sha256"]:
            raise ModError(f"{relative} is missing or changed")
    extra = sorted({p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()} - set(mod["files"]))
    if extra:
        raise ModError(f"Files not listed in mod.json: {extra[:5]}")
    return mod


def conflicts(mods):
    """{path: [mod ids]} of paths written by more than one mod."""
    writers = {}
    for mod in mods:
        for path in mod["writes"]:
            writers.setdefault(path.casefold(), []).append(mod["id"])
    return {path: ids for path, ids in writers.items() if len(ids) > 1}
