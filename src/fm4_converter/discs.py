"""Game discs given as an extracted folder or an Xbox 360 disc image (.iso).

`Disc` reads the title ID and disc number from `default.xex`, so a wrong disc is refused
before any conversion. `Disc.root` returns a folder the converters can read: the folder
itself, or the files a role needs extracted from the image into a cache folder.
"""
from pathlib import Path, PurePosixPath
import struct

from .archives.xiso import XISO, is_iso

# Title IDs from the execution info of each game's default.xex.
FM2, FM2_BONUS, FM3, FM4 = 0x4D5307EA, 0xFFED2000, 0x4D53084D, 0x4D530910
TITLES = {FM2: "Forza Motorsport 2", FM2_BONUS: "Forza Motorsport 2 Bonus Disc",
          FM3: "Forza Motorsport 3", FM4: "Forza Motorsport 4"}
EXECUTION_INFO = 0x00040006

# role: (title ID, disc number, disc paths the converters read)
ROLES = {
    "fm3-disc1": (FM3, 1, ["Media/DB", "Media/Cars", "Media/Wheels", "Media/StringTables",
                           "Media/UI/Textures.zip"]),
    "fm3-disc2": (FM3, 2, ["Content/0000000000000000/4D53084D/00000002"]),
    "fm2-disc": (FM2, 1, ["Media/DB", "Media/cars", "Media/wheels", "Media/StringTables",
                          "Media/UI/Textures.zip"]),
    "fm2-bonus": (FM2_BONUS, 1, ["content/0000000000000000/FFED2000/FFFFFFFF"]),
    "fm4-disc1": (FM4, 1, None),
}
# What the track conversion (fm2.track_env) reads of the FM2 disc.
FM2_TRACK_PATHS = ["Media/DB", "Media/StringTables", "Media/UI/Textures.zip", "Media/tracks/newyork",
                   "Media/tracks/testtrackinfield",
                   "Media/AI/Tracks", "Media/Audio/Tracks/newyork", "Media/Audio/Tracks/testtrackinfield"]
# What the track conversion (fm3.track_env) reads of FM3 Disc 1, beyond the database and names.
FM3_TRACK_PATHS = ["Media/DB", "Media/StringTables", "Media/UI/Textures.zip", "Media/Tracks/NewYork",
                   "Media/Tracks/LeMans", "Media/Tracks/CrownJewel", "Media/AI/Tracks",
                   "Media/Audio/Tracks/NewYork", "Media/Audio/Tracks/LeMans", "Media/Audio/Tracks/CrownJewel"]


class DiscError(ValueError):
    pass


def execution_info(xex):
    """(title ID, disc number, disc count, media ID) from a XEX2 header."""
    if xex[:4] != b"XEX2":
        raise DiscError("default.xex is not an Xbox 360 executable")
    for i in range(struct.unpack_from(">I", xex, 0x14)[0]):
        key, value = struct.unpack_from(">II", xex, 0x18 + 8*i)
        if key == EXECUTION_INFO:
            media, _, _, title, _, _, number, count = struct.unpack_from(">IIIIBBBB", xex, value)
            return title, number, count, media
    raise DiscError("default.xex has no execution info")


class Disc:
    def __init__(self, path, role=None):
        """`role` None: identify the disc; `role` is then the matching role, or None."""
        if role is not None and role not in ROLES:
            raise DiscError(f"Unknown disc role {role}")
        self.path, self.role = Path(path), role
        if not self.path.exists():
            raise DiscError(f"{self.path} does not exist")
        self.image = is_iso(self.path)
        if not self.image and not (self.path / "default.xex").is_file() and self.path.name.casefold() == "media":
            self.path = self.path.parent   # the Media folder was chosen instead of the disc folder
        if self.image:
            with XISO(self.path) as iso:
                xex = iso.read("default.xex")
        elif (self.path / "default.xex").is_file():
            xex = (self.path / "default.xex").read_bytes()
        else:
            raise DiscError(f"{self.path} is neither a disc image (.iso) nor a disc folder with default.xex")
        self.title, self.number, self.count, self.media_id = execution_info(xex)
        if role is None:
            self.role = next((r for r, (t, n, _) in ROLES.items() if (t, n) == (self.title, self.number)), None)
            return
        title, number, _ = ROLES[role]
        if (self.title, self.number) != (title, number):
            found = TITLES.get(self.title, f"title {self.title:08X}")
            raise DiscError(f"{self.path} is {found} disc {self.number}; expected {TITLES[title]} disc {number}")

    def describe(self):
        return dict(role=self.role, game=TITLES.get(self.title), path=str(self.path),
                    kind="iso" if self.image else "folder", title_id=f"{self.title:08X}",
                    disc_number=self.number, disc_count=self.count, media_id=f"{self.media_id:08X}")

    def root(self, cache=None, progress=None, prefixes=None, name=None):
        """A folder with the disc layout. An image is extracted (only the role's paths, or
        `prefixes`) into `cache/<name or role>`; a later call reuses the files already there."""
        prefixes = prefixes or ROLES[self.role][2]
        if not self.image:
            missing = [p for p in prefixes or () if not (self.path / PurePosixPath(p)).exists()]
            if missing:
                raise DiscError(f"{self.path} lacks {', '.join(missing)}")
            return self.path
        if prefixes is None:
            raise DiscError(f"Give the extracted {TITLES[ROLES[self.role][0]]} disc folder, not an image")
        if cache is None:
            raise DiscError("Extracting a disc image needs a cache folder")
        out = Path(cache) / (name or self.role)
        with XISO(self.path) as iso:
            missing = [p for p in prefixes if not iso.files(p)]
            if missing:
                raise DiscError(f"{self.path} lacks {', '.join(missing)}")
            iso.extract(prefixes, out, progress)
        return out
