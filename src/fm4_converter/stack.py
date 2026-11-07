"""Packages built on a disc that already carries other packages: a stacked install.

A launcher installs several packages (the FM3 cars, the FM2 cars, the FM3 tracks) together by
building each one on the disc the packages before it make: `--fm4` is then a folder with FM4
Disc 1 and those packages' files over it, and the new package is converted against that disc,
as against a plain Disc 1. Its keys, string keys and car IDs then avoid the earlier packages'
rows, and every file it ships is either new or a whole replacement of the disc's file.

The archives that every package ships at the same path (CUMULATIVE) are extended instead of
replaced: the new archive holds the base disc's members plus this package's, and takes over
the base's mount in `zipmanifest.xml`. A package built this way plays only with the packages
under it; `mod.json`'s `built_against` records the base disc's database and manifest, which a
launcher checks against the files the packages under it write. See docs/mod-format.md.
"""
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile

from .fm3.integration import archive_read

# Archives a package adds outside FM4's own files: a later package extends them.
STRINGS = Path("Media/stringtables.zip")
THUMBNAILS = Path("Media/UI/Textures/Thumbnails.zip")
CAR_AUDIO = Path("Media/audio/Cars.zip")
CUMULATIVE = (STRINGS, THUMBNAILS, CAR_AUDIO)


def guest_path(relative):
    """`zipmanifest.xml`'s path of a disc file: game:\\media\\...\\name.zip, lower case."""
    return "game:\\" + str(Path(relative)).replace("/", "\\").lower()


def members(disc, relative):
    """{member name: bytes} of an archive the base disc carries at `relative`, else {}."""
    path = Path(disc) / relative
    if not path.is_file():
        return {}
    with zipfile.ZipFile(path) as z:
        return {i.filename: archive_read(z, i) for i in z.infolist() if not i.is_dir()}


def mounted(manifest, relative):
    """The priority `zipmanifest.xml` (bytes) mounts `relative` at, or None."""
    guest = guest_path(relative).casefold()
    for node in ET.fromstring(manifest).findall("Zip"):
        if node.attrib["path"].casefold() == guest:
            return int(node.attrib["priority"])
    return None


def extend(disc, relative, payloads):
    """The members of the base disc's archive at `relative` (posix name -> bytes), with
    `payloads` added; a member of the same name (case-insensitive) is replaced. Returns
    ({name: bytes}, replaced: whether the base disc had the archive)."""
    base = members(disc, relative)
    merged = {name: data for name, data in base.items()
              if name.casefold() not in {n.casefold() for n in payloads}}
    merged.update(payloads)
    return merged, bool(base)
