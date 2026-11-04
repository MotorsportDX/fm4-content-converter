"""Default locations of the FM2 and FM4 discs read by the FM2 converter."""
from pathlib import Path

from ..fm3 import converter as c
from ..paths import PROJECT_ROOT

FM2_MEDIA = Path(r'D:\Data\FM2\USA\Forza Motorsport 2 (USA)\Media')
FM2_DB = FM2_MEDIA / 'DB/gamedb.slt'
FM2_CARS = FM2_MEDIA / 'cars'
FM2_WHEELS = FM2_MEDIA / 'wheels'
FM2_BONUS_DISC = Path(r'D:\Data\FM2\USA\Forza Motorsport 2 (USA) (Bonus Disc)')
# The FM2 DLC as a Media folder, written by `fm2.dlc`. When present, packages read it next to the disc.
FM2_DLC = PROJECT_ROOT / 'outputs/car-fm2-dlc/Media'
FM3_CARS = Path(r'D:\Data\FM3\USA\Forza Motorsport 3 (USA) (Disc 1) (Play Disc)\Media\cars')
FM4_CARS = Path(c.FM4_DEFAULT).parents[1] / 'cars'
# Installed FM4 DLC packs whose keys and registry rows a package must respect.
CONTENT = Path(r'I:\FM4-build-usa\user-data\0000000000000000\4D530910\00000002')


def zips(root):
    """{lower-case archive stem: path} of a disc folder such as Media/cars."""
    return {p.stem.casefold(): p for p in Path(root).glob('*.zip')}


def disc_zip(root, name):
    """The archive `name` in `root`, matched case-insensitively."""
    found = zips(root).get(name.casefold())
    if found is None:
        raise c.MappingError(f'No {name}.zip in {root}')
    return found


def fm2_db(dlc=FM2_DLC):
    """The FM2 database with the DLC patches (`fm2.dlc`) when built, else the disc's."""
    merged = Path(dlc) / 'DB/gamedb.slt'
    return merged if merged.exists() else FM2_DB


def fm2_zips(kind, dlc=FM2_DLC):
    """{lower-case stem: path} of the disc's Media/<kind> archives and the DLC's ('cars', 'wheels')."""
    disc, extra = zips(FM2_MEDIA / kind), zips(Path(dlc) / kind)
    clash = sorted(disc.keys() & extra.keys())
    if clash:
        raise c.MappingError(f'DLC archives also on the disc: {clash}')
    return {**disc, **extra}


def fm2_zip(kind, name, dlc=FM2_DLC):
    found = fm2_zips(kind, dlc).get(name.casefold())
    if found is None:
        raise c.MappingError(f'No FM2 {kind} archive {name}')
    return found
