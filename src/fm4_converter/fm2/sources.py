"""Default locations of the FM2 and FM4 discs read by the FM2 converter."""
from pathlib import Path

from ..fm3 import converter as c

FM2_MEDIA = Path(r'D:\Data\FM2\USA\Forza Motorsport 2 (USA)\Media')
FM2_DB = FM2_MEDIA / 'DB/gamedb.slt'
FM2_CARS = FM2_MEDIA / 'cars'
FM2_WHEELS = FM2_MEDIA / 'wheels'
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
