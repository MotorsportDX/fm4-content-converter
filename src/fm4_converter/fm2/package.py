"""One offline FM4 overlay with FM2-only cars (REPORT sections 8-14).

Per car: FM4 models from `models` (main, _lod0, _cockpit and the stock wheel), FM2 body and wheel
textures with FM4 fetch constants (`asset_conversion.convert_texture`; FM2 XDS headers equal FM3's),
_lod0 atlases = the LOD1 atlases because _lod0 is built from the LOD1 meshes with the same UVs,
FM2 carattribs.xml and physics/maxdata.xml, the donor's calipers and rotors, cockpit PaintScale
values in shadersettings.xml (`with_cockpit_paint_scales`), the FM2 thumbnail in an FM4 UI atlas
and the FM2 English names + " (FM2)". The database row graph is the donor's stock graph with new
keys, `Data_Car.Id` = the FM2 Id, the FM2 MediaName and year, and FM2 physics where the `physics`
study chose it.

All cars go into ONE database, one Data_Car.str per language, one thumbnail atlas and one
zipmanifest, as `fm3.batch_package`. Cars are planned one after another against the growing
package database, so new keys never collide; installed DLC keys stay reserved.

- Donor: `physics.donor` (same make and drive type, nearest mass and power) among FM4 disc cars with
  _lod0, _cockpit, four calipers and rotors, the FM2 model's steering side and drive type, a race
  car only for race cars, and a steering wheel near the FM2 one (`choose_donor`). The cockpit camera
  and driver position follow the donor (REPORT 14.5, 15.3). `--donor CAR=DONOR` picks one car's
  donor from the same pool, with the same steering side.
- `MakeID`: FM2's when FM4 or an installed DLC has a make with the same ID and manufacturer code
  (the DLC goes to `requires`); otherwise the donor's, recorded.
- Wheels FM4 already ships are used as they are; a wheel several FM2 cars share is shipped once.
- Audio: the native `<car>_CMT.xml` when it exists. Otherwise the donor's CMT is copied under the
  car's name into `Media/audio/Cars.zip` (mount `audio\\cars`, entry `CarModelTuning/<car>_CMT.xml`)
  at a priority above `carmodeltuning.zip`, the same pattern as `Media/stringtables.zip`. The
  engine sound stays the donor `Data_Engine`'s.

Failed cars are recorded with their reason; the other cars are still packaged. No game is run.

  python -m fm4_converter.fm2.package --out <new package folder> [--cars JAG_XK_07 ...]
                                      [--donor JAG_XK_07=JAG_XKRS_09 ...]
"""
from contextlib import closing
from pathlib import Path, PureWindowsPath
import argparse, hashlib, io, json, shutil, sqlite3, traceback, zipfile

from . import carbin, models as fm4_models, physics, sources
from ..archives import forza_zip
from ..fm3 import appearance_audit, batch_package, carbin_audit, integration, ui_names, ui_thumbnail
from ..fm3 import converter as c
from ..fm3.asset_conversion import convert_texture
from ..fm3.integration import archive_read
from ..fm3.texture_audit import Texture
from ..paths import PROJECT_ROOT

CONTENT = sources.CONTENT
OUT = PROJECT_ROOT / 'outputs/car-fm2-batch-2026-11-04'
INVENTORY = PROJECT_ROOT / 'outputs/car-fm2-research-2026-11-02/inventory.json'
STUDY = physics.OUT / 'study.json'
CARS, WHEELS, THUMBNAILS = Path('Media/Cars'), Path('Media/Wheels'), batch_package.THUMBNAILS
# Data_Car.Thumbnail as FM4 writes it, e.g. game:\Media\UI\Textures\Thumbnails\Thumbnail_1473.xds.
THUMBNAIL_PATH = 'game:\\' + str(PureWindowsPath(THUMBNAILS)) + '\\Thumbnail_{}.xds'
BODY_TEXTURES = ('nodamage', 'damage', 'lights', 'damagelights')
# FM4 Data_Car.str keys use the upper word 0xCD49 (e.g. _&3444170456).
STRING_PAGE = 0xCD49
# Car ownership column of the presentation tables; tables with their own ID key get new IDs.
PRESENTATION = {'CarPartPositions': 'Ordinal', 'CarExceptions': 'CarID',
                'CameraOverrides': 'CarId', 'Combo_Colors': 'Ordinal'}
AUDIO = Path('Media/audio/Cars.zip')
AUDIO_ROOT = Path('Media/audio/Cars')
AUDIO_PRIORITY = 96   # carmodeltuning.zip is mounted at priority 95


def sha(data):
    return hashlib.sha256(data).hexdigest()


def find(members, name):
    found = [k for k in members if k.casefold() == name.casefold()]
    if len(found) != 1:
        raise c.MappingError(f'Expected one {name}, got {found}')
    return found[0]


def fm2_only():
    inventory = json.loads(INVENTORY.read_text(encoding='utf-8'))
    return [x['MediaName'] for x in inventory['cars'] if x['route'] == 'fm2_only']


def thumbnail(data, template):
    """FM4 UI atlas from an FM2 thumbnail. FM2 alpha is already a cutout, so FM3's white matte is
    not removed and the FM3->FM4 colour curve is not applied (measured on FM3 renders)."""
    import numpy as np
    from PIL import Image
    t = Texture(data)
    if (t.width, t.height, t.codec) != (256, 128, 'DXT5'):
        raise c.MappingError('Unreviewed FM2 thumbnail format')
    cutout = Image.frombytes('RGBA', (t.width, t.height), t.read_level(0), 'bcn', 3)
    alpha = np.array(cutout)[:, :, 3]
    border = np.concatenate([alpha[0], alpha[-1], alpha[:, 0], alpha[:, -1]])
    if alpha.max() < 255 or (border > 0).mean() > ui_thumbnail.MAX_CROPPED_BORDER:
        raise c.MappingError('FM2 thumbnail alpha is not a car cutout')
    atlas = Image.new('RGBA', (768, 288))
    atlas.paste(ui_thumbnail.fit_view(cutout, (608, 288), ui_thumbnail.LARGE_LAYOUT), (0, 0))
    small = ui_thumbnail.fit_view(cutout, (288, 160), ui_thumbnail.SMALL_LAYOUT)
    atlas.paste(small.transpose(Image.Transpose.ROTATE_90), (608, 0))
    encoded = ui_thumbnail.encode(atlas, template)
    return encoded, dict(source=[t.width, t.height, t.codec], source_sha256=sha(data), target_sha256=sha(encoded),
                         alpha_border_share=float((border > 0).mean()), fm4_tone=False,
                         texture=Texture(encoded).audit())


def assets(car, donor, models, fm2_zip, donor_zip, wheel):
    """{Media/Cars/<car>/... and Media/Wheels/<wheel>/...: bytes}, the origin of each file and the
    FM2 files not shipped. `wheel` None: the wheel is already shipped by FM4 or another car."""
    root, payloads, origin = CARS / car, {}, {}

    def put(name, data, source):
        payloads[root / name] = data
        origin[(root / name).as_posix()] = source
    for kind in ('', '_lod0', '_cockpit'):
        name = f'{car.lower()}{kind}.carbin'
        put(name, (models / name).read_bytes(), 'fm2.models')
    with zipfile.ZipFile(fm2_zip) as z:
        fm2 = {i.filename: z.read(i) for i in z.infolist() if not i.is_dir()}
    for texture in BODY_TEXTURES:
        data = convert_texture(fm2[find(fm2, texture + '.xds')], texture + '.xds')
        put(texture + '.xds', data, f'FM2 {texture}.xds, FM4 colour fetch constants')
        put(texture + '_lod0.xds', data, f'FM2 {texture}.xds (LOD0 meshes use the LOD1 UVs)')
        if texture == 'nodamage':
            # FM2 cockpit meshes (now cockpit_* techniques) use the body atlas UVs.
            put('interior_lod0.xds', data, 'FM2 Nodamage.xds (cockpit meshes use the body atlas UVs)')
    # CarAttribs.xml: three FM2 cars do not carry it, and the old FM2 (CarAttributes, Driver)
    # versions (3, 3) and (3, 4) have no FM4 precedent. Both ship without the file, as native FM4
    # cars without carattribs.xml (`appearance_audit.driver_attributes`).
    attribs = [k for k in fm2 if k.casefold() == 'carattribs.xml']
    if attribs:
        attributes = appearance_audit.xml(fm2[attribs[0]])
        driver = attributes.find('Driver')
        version = (attributes.get('Version'), driver.get('Version') if driver is not None else None)
        if version in appearance_audit.NATIVE_LAYOUTS:
            put('carattribs.xml', fm2[attribs[0]], 'FM2 CarAttribs.xml')
        else:
            origin['carattribs.xml not shipped'] = f'FM2 CarAttributes/Driver version {version} has no FM4 precedent'
    else:
        origin['carattribs.xml not shipped'] = 'FM2 archive has no CarAttribs.xml'
    put('physics/maxdata.xml', fm2[find(fm2, 'Physics/MAXData.xml')], 'FM2 Physics/MAXData.xml')
    with zipfile.ZipFile(donor_zip) as z:
        for info in z.infolist():
            name = info.filename.lower()
            if name.startswith(donor.lower() + '_') and ('_caliper' in name or '_rotor' in name):
                put(car.lower() + name[len(donor):], archive_read(z, info), f'donor {info.filename}')
    if sum('_caliper' in k or '_rotor' in k for k in origin) != 8:
        raise c.MappingError('Donor must have four calipers and four rotors')
    skipped = sorted(k for k in fm2 if not any(k.casefold() == f.casefold() for f in
                     [t + '.xds' for t in BODY_TEXTURES] + ['CarAttribs.xml', 'Physics/MAXData.xml', car.lower() + '.carbin']))
    if wheel is None:
        return payloads, origin, skipped
    # FM2 stock wheel: model from fm2.models, FM2 textures; wheel LOD 0 uses the LOD 1 UVs.
    wheel_root = WHEELS / wheel
    payloads[wheel_root / f'{wheel.lower()}.carbin'] = (models / 'wheel' / f'{wheel.lower()}.carbin').read_bytes()
    origin[(wheel_root / f'{wheel.lower()}.carbin').as_posix()] = 'fm2.models (FM2 wheel)'
    with zipfile.ZipFile(sources.fm2_zip('wheels', wheel)) as z:
        rims = {i.filename: z.read(i) for i in z.infolist() if not i.is_dir()}
    for name in [n for n in rims if n.lower().endswith('.xds')]:
        data = convert_texture(rims[name], name)
        payloads[wheel_root / name.lower()] = data
        origin[(wheel_root / name.lower()).as_posix()] = f'FM2 wheel {name}, FM4 colour fetch constants'
        if name.lower() == 'wheel.xds':
            payloads[wheel_root / 'wheel_lod0.xds'] = data
            origin[(wheel_root / 'wheel_lod0.xds').as_posix()] = 'FM2 wheel wheel.xds (LOD 0 uses the LOD 1 UVs)'
    return payloads, origin, skipped


def clone_stock(work, donor, media, car_id, year, reserved):
    """The donor's stock graph with new keys (free keys from 2000, skipping DLC keys)."""
    graph = c.extract_stock(work, donor)
    occupied, allocation = {}, {}
    for role, node in sorted(graph['nodes'].items()):
        table, key = node['table'], node['row'][node['pk']]
        if table not in occupied:
            occupied[table] = {r[0] for r in work.execute(f"SELECT {c.qi(node['pk'])} FROM {c.qi(table)}")}
            occupied[table] |= set(reserved.get(table, ()))
        if (table, key) in allocation:
            continue
        value = car_id if role == 'car' else 2000
        while role != 'car' and value in occupied[table]:
            value += 1
        if value in occupied[table]:
            raise c.MappingError(f'Key already used: {table} {value}')
        allocation[table, key] = value
        occupied[table].add(value)
    nodes = {}
    for role, node in graph['nodes'].items():
        row = dict(node['row'])
        row[node['pk']] = allocation[node['table'], row[node['pk']]]
        nodes[role] = dict(node, row=row)
    for edge in graph['edges']:
        parent = graph['nodes'][edge['to']]
        nodes[edge['from']]['row'][edge['column']] = allocation[parent['table'], parent['row'][parent['pk']]]
    car = nodes['car']['row']
    # Car Select finds the thumbnail by Id, the pre-race car card by this path (it showed the donor).
    car.update(MediaName=media, Year=year, ModelId=car_id, ContentId=0, IsInstalled=1, IsPurchased=1,
               IsArcade=1, IsUnicorn=0, IsDrivable=1, HasCarExperience=0, IsCarExperienceUnlocked=0,
               Thumbnail=THUMBNAIL_PATH.format(car_id))
    rows = [{'table': n['table'], 'row': n['row']} for n in nodes.values()]
    donor_id = graph['nodes']['car']['row']['Id']
    for table, column in PRESENTATION.items():
        own = 'ID' in {x['name'] for x in c.schema(work)[table]['columns']}
        next_id = 1 + max([work.execute(f'SELECT MAX(ID) FROM {table}').fetchone()[0] or 0,
                           *reserved.get(table, ())]) if own else None
        for original in c.rows(work, table, c.qi(column) + '=?', (donor_id,)):
            row = dict(original, **{column: car_id})
            if own:
                row['ID'], next_id = next_id, next_id + 1
            rows.append({'table': table, 'row': row})
    return graph, nodes, rows


def free_key(work, table, pk, reserved, rows):
    """First free key from 2000, as clone_stock: unused by the database, DLC packs and package rows."""
    occupied = {r[0] for r in work.execute(f'SELECT {c.qi(pk)} FROM {c.qi(table)}')}
    occupied |= set(reserved.get(table, ())) | {r['row'][pk] for r in rows if r['table'] == table}
    value = 2000
    while value in occupied:
        value += 1
    return value


def names(car_id, label, taken):
    """Two free (highest) Data_Car.str keys for DisplayName and ModelShort."""
    keys = {}
    for field in ('DisplayName', 'ModelShort'):
        free = next(k for k in range(65534, 0, -1) if k not in taken)
        taken.add(free)
        keys[field] = dict(reference=f'_&{STRING_PAGE << 16 | free}', symbol=f'IDS_{field}_{car_id}', text=label[field])
    return keys


def string_archive(target_root, content_root, keys):
    tables, inputs = ui_names.winning_tables(target_root, content_root, archive_read, c.sha)
    additions = [(ui_names.reference(k['reference']), k['symbol'], k['text']) for k in keys.values()]
    stream, reports = io.BytesIO(), []
    with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_STORED) as output:
        for _, (priority, language, origin, data) in sorted(tables.items()):
            table = ui_names.StringTable(data)
            encoded = table.add(additions)
            checked = ui_names.StringTable(encoded)
            if any(checked.texts[k] != v for k, v in table.texts.items()):
                raise c.MappingError('Existing localized text changed')
            output.writestr(zipfile.ZipInfo(f'{language}/Data_Car.str', (1980, 1, 1, 0, 0, 0)), encoded)
            reports.append(dict(language=language, winning_table=origin, winning_priority=priority))
    priority = max(r['winning_priority'] for r in reports) + 1
    return stream.getvalue(), priority, dict(inputs=inputs, languages=reports, priority=priority)


def donor_pool(fm4):
    """FM4 disc cars that can be donors: _lod0/_cockpit headers, four calipers and rotors; `wheel` =
    origin of the steering_wheel section in _cockpit, `steer` = its x (negative = left-hand drive),
    `race` = a race car (CarTypeID RACE)."""
    discs = sources.zips(sources.FM4_CARS)

    def usable(media):
        path = discs.get(media.casefold())
        if path is None:
            return False
        with zipfile.ZipFile(path) as z:
            members = [i.filename.lower() for i in z.infolist()]
            own = [m for m in members if m.startswith(media.lower() + '_')]
            if not ({f'{media.lower()}_lod0.carbin', f'{media.lower()}_cockpit.carbin'} <= set(members) and
                    sum('_caliper' in m for m in own) == 4 and sum('_rotor' in m for m in own) == 4):
                return False
            # The donor's close-up headers are copied into the models; AUD_2_R15TDI_09 has non-finite floats there.
            try:
                heads = {k: carbin_audit.parse(forza_zip.read(z, f'{media.lower()}_{k}.carbin'), 'FM4')
                         for k in ('lod0', 'cockpit')}
            except carbin_audit.FormatError:
                return False
        wheel = [tuple(s['bounds'][:3]) for s in heads['cockpit']['sections'] if s['name'] == 'steering_wheel']
        return wheel[0] if len(wheel) == 1 else False
    pool = []
    for d in physics.fm4_index(fm4):
        wheel = usable(d['media'])
        if wheel is not False:
            race = fm4.execute('SELECT CarTypeID FROM Data_Car WHERE Id=?', (d['id'],)).fetchone()[0] == RACE
            pool.append({**d, 'wheel': wheel, 'steer': wheel[0], 'race': race})
    return pool


def fm2_wheel(car, fm2_zip):
    """Origin of the FM2 model's steering_wheel section (same axis convention as FM4), or None."""
    with zipfile.ZipFile(fm2_zip) as z:
        model = carbin.parse(z.read(next(n for n in z.namelist() if n.lower() == car.lower() + '.carbin')))
    wheel = [tuple(s.origin[:3]) for s in model.sections if s.name == 'steering_wheel']
    return wheel[0] if len(wheel) == 1 else None


def same_side(pool, steer):
    """Donors whose steering wheel is on the same side as `steer`."""
    return [d for d in pool if (d['steer'] > 0) == (steer > 0)]


# CarTypeID in FM2 and FM4: 1 production, 2 tuner, 3 race.
RACE = 3
# The cockpit camera follows the donor, the cockpit geometry the FM2 model. dz/dy = FM2 steering wheel
# origin minus the donor's in metres; +z points to the rear, so dz > 0 puts the FM2 wheel nearer the
# seat. In game dz -0.31..+0.17 looked right; +0.18..+0.35 put the camera inside or in front of the
# wheel, -0.59 behind the seat, and dy +0.08 hid the hands (REPORT 15.3). The window keeps a margin.
WHEEL_DZ = (-0.25, 0.10)
WHEEL_DY = 0.07


def wheel_offset(wheel, donor):
    """(dz, dy) of the FM2 steering wheel origin against the donor's."""
    return wheel[2] - donor['wheel'][2], wheel[1] - donor['wheel'][1]


def outside(wheel, donor):
    """How far (metres) the FM2 wheel lies outside the WHEEL_DZ/WHEEL_DY window of the donor; 0 inside."""
    dz, dy = wheel_offset(wheel, donor)
    return max(WHEEL_DZ[0] - dz, dz - WHEEL_DZ[1], 0) + max(abs(dy) - WHEEL_DY, 0)


def choose_donor(pool, source, car_id, wheel, race, manual=None):
    """(donor pool entry, 'automatic' or 'manual').

    Automatic: donors with the steering side and drive type of the FM2 car, race donors for race cars
    and non-race donors otherwise (when there is one), then those whose steering wheel lies in the
    WHEEL_DZ/WHEEL_DY window (or the nearest one when none does), then `physics.donor`: same make,
    nearest mass and power. Manual: in the pool with the same steering side; the window is not
    enforced, and the offset is reported by the caller."""
    side = same_side(pool, wheel[0])
    if manual is None:
        drive = [d for d in side if d['drive'] == source['nodes']['drivetrain']['DrivetypeID']] or side
        kind = [d for d in drive if d['race'] == race] or drive
        seated = [d for d in kind if not outside(wheel, d)] or [min(kind, key=lambda d: (outside(wheel, d), d['id']))]
        return physics.donor(seated, source, car_id), 'automatic'
    found = [d for d in pool if d['media'].casefold() == manual.casefold()]
    if not found:
        raise c.MappingError(f'{manual} is not a usable donor: an FM4 disc car with _lod0, _cockpit, '
                             'four calipers and rotors and readable close-up headers')
    if found[0] not in side:
        raise c.MappingError(f'{manual} has the steering wheel on the other side; the cockpit camera '
                             'would sit on the passenger seat')
    return found[0], 'manual'


def parse_donors(pairs):
    """{car casefold: donor} from CAR=DONOR arguments."""
    donors = {}
    for pair in pairs or ():
        car, sep, donor = pair.partition('=')
        if not (sep and car and donor):
            raise c.MappingError(f'Expected CAR=DONOR, got {pair!r}')
        if car.casefold() in donors:
            raise c.MappingError(f'Two donors for {car}')
        donors[car.casefold()] = donor
    return donors


def models_for(car, donor, root, helper=fm4_models.HELPER):
    """The `models` folder for (car, donor); built when missing."""
    folder = root / f'{car.lower()}--{donor.lower()}'
    if not (folder / 'report.json').exists():
        if folder.exists():
            shutil.rmtree(folder)
        try:
            fm4_models.build(car, donor, folder, helper)
        except (RuntimeError, carbin.FormatError, carbin_audit.FormatError) as error:
            raise c.MappingError(f'fm2.models failed: {type(error).__name__}: {error}') from error
    return folder


def make_for(fm2_db, work, registry, fm2_make):
    """(MakeID, origin) when FM4 or an installed DLC has FM2's make; (None, reason) otherwise."""
    code = fm2_db.execute('SELECT ManufacturerCode FROM List_CarMake WHERE ID=?', (fm2_make,)).fetchone()[0]
    row = work.execute('SELECT ManufacturerCode FROM List_CarMake WHERE ID=?', (fm2_make,)).fetchone()
    if row is not None:
        return (fm2_make, None) if row[0] == code else (None, f'FM4 make {fm2_make} is {row[0]}, FM2 {code}')
    for origin, dlc in registry.get('List_CarMake', ()):
        if dlc['ID'] == fm2_make and dlc['ManufacturerCode'] == code:
            return fm2_make, origin
    return None, f'no FM4 make {code}'


def build(out, cars=None, target=c.FM4_DEFAULT, content_root=CONTENT, study=STUDY, models_root=OUT / 'models',
          helper=fm4_models.HELPER, donors=None):
    """`donors`: {car casefold: donor MediaName} replacing the automatic donor of those cars."""
    target, out = Path(target).resolve(), Path(out).resolve()
    cars, donors = list(cars or fm2_only()), dict(donors or {})
    unknown = sorted(set(donors) - {car.casefold() for car in cars})
    if unknown:
        raise c.MappingError(f'Donor given for cars that are not packaged: {unknown}')
    target_root, disc = target.parents[1], target.parents[2]
    if out.exists():
        raise c.MappingError('Choose a new package directory')
    if out == disc or disc in out.parents:
        raise c.MappingError('Package output must be outside the original disc')
    study_data = json.loads(Path(study).read_text(encoding='utf-8'))
    reserved, registry, dlc_wheels, overlays = batch_package.installed_content(content_root)
    files, reports = out / 'files', out / 'reports'
    (files / 'Media/DB').mkdir(parents=True)
    reports.mkdir()
    database = files / 'Media/DB/gamedb.slt'
    shutil.copyfile(target, database)
    # The FM2 disc, and the FM2 DLC (`fm2.dlc`) when built: its Data_Car.str adds the DLC names.
    fm2_zips, fm2_database = sources.fm2_zips('cars'), sources.fm2_db()
    media = [m for m in (sources.FM2_DLC, sources.FM2_MEDIA) if (m / 'UI/Textures.zip').exists()]
    inputs = {str(p): c.sha(p) for p in (target, fm2_database, study, *(m / 'StringTables/EN.zip' for m in media),
                                          *(m / 'UI/Textures.zip' for m in media),
                                          target_root / 'audio/Cars/CarModelTuning.zip')}
    fm2_text = {}
    for m in reversed(media):
        with zipfile.ZipFile(m / 'StringTables/EN.zip') as z:
            fm2_text.update(ui_names.StringTable(z.read('Data_Car.str')).texts)
    with zipfile.ZipFile(target_root / 'audio/Cars/CarModelTuning.zip') as z:
        tuning = {i.filename.casefold(): archive_read(z, i) for i in z.infolist()}
    with zipfile.ZipFile(target_root / 'UI/Textures.zip') as z:
        controls = [archive_read(z, f'Thumbnails/Thumbnail_{n}.xds') for n in (1002, 1003, 1305)]
    if len({b[:52] for b in controls}) != 1:
        raise c.MappingError('Native thumbnail control headers disagree')

    payloads, origins, keys, thumbs, audio, shipped_wheels = {}, {}, {}, {}, {}, {}
    packaged, failed = [], []
    with closing(c.connect(fm2_database)) as fm2_db, closing(sqlite3.connect(database)) as work:
        work.row_factory = sqlite3.Row
        pool = donor_pool(work)
        tables, _ = ui_names.winning_tables(target_root, content_root, archive_read, c.sha)
        taken = {k for _, _, _, data in tables.values() for k in ui_names.StringTable(data).texts}
        for car in cars:
            log, car_keys = {'media': car}, {}
            try:
                fm2_car = c.one(c.rows(fm2_db, 'Data_Car', 'MediaName=?', (car,)), f'FM2 {car}')
                car_id = fm2_car['Id']
                if car.lower() not in fm2_zips:
                    raise c.MappingError('No FM2 car archive on the disc')
                if c.rows(work, 'Data_Car', 'Id=? OR lower(MediaName)=lower(?)', (car_id, car)) or \
                        car_id in reserved.get('Data_Car', ()):
                    raise c.MappingError('The FM2 car identity already exists in FM4 or an installed DLC')
                source = physics.extract(fm2_db, car_id, work)
                # The cockpit camera and driver position follow the donor: a donor with the wheel on the
                # other side puts the camera on the passenger seat (Evo IX with an Eclipse donor, REPORT 14.5).
                steering = fm2_wheel(car, fm2_zips[car.lower()])
                if steering is None:
                    raise c.MappingError('FM2 model has no single steering_wheel section')
                chosen, log['donor_choice'] = choose_donor(pool, source, car_id, steering,
                                                           fm2_car['CarTypeID'] == RACE, donors.get(car.casefold()))
                donor = chosen['media']
                dz, dy = wheel_offset(steering, chosen)
                log['steering'] = 'right' if steering[0] > 0 else 'left'
                log['donor'] = donor
                log['wheel_offset'] = {'dz': round(dz, 3), 'dy': round(dy, 3),
                                       'in_window': not outside(steering, chosen)}
                models = models_for(car, donor, Path(models_root), helper)
                prototype = json.loads((models / 'report.json').read_text(encoding='utf-8'))
                requires = set()

                graph, nodes, rows = clone_stock(work, donor, car, car_id, fm2_car['Year'], reserved)
                # FM4 keeps orphan TireMod_FrictionScale rows for some Ids (Ordinal 288 = FM2 Camaro SS);
                # extract_stock binds them to the car with that Id, so the row joins the graph.
                orphans = {}
                if 'tire.modifier' not in nodes:
                    found = c.rows(work, 'TireMod_FrictionScale', 'Ordinal=?', (car_id,))
                    if found:
                        orphans['tire.modifier'] = dict(found[0])
                        nodes['tire.modifier'] = {'table': 'TireMod_FrictionScale', 'pk': 'Ordinal',
                                                  'row': dict(found[0])}
                        log['existing_rows'] = {'tire.modifier': dict(found[0])}
                make, why = make_for(fm2_db, work, registry, fm2_car['MakeID'])
                if make is None:
                    log['make'] = {'kept_donor': nodes['car']['row']['MakeID'], 'reason': why}
                else:
                    nodes['car']['row']['MakeID'] = make
                    log['make'] = {'fm2': make, 'requires': why}
                    if why:
                        requires.add(why)
                applied = physics.apply(nodes, source, study_data, work)
                removed = {id(nodes.pop(role)['row']) for role in applied['removed_roles']}
                rows = [r for r in rows if id(r['row']) not in removed]
                for role in applied['added_roles']:
                    node = nodes[role]
                    node['row'][node['pk']] = free_key(work, node['table'], node['pk'], reserved, rows)
                    rows.append({'table': node['table'], 'row': node['row']})

                # Wheel: FM4's (disc or installed DLC), another car's in this package, or the converted FM2 wheel.
                wheel = prototype['wheel']['media']
                nodes['wheel']['row']['MediaName'] = wheel
                native = batch_package.native_wheel(target_root, dlc_wheels, wheel)
                if native is not None:
                    wheel_origin, references = native
                    log['wheel'] = 'native_fm4' if wheel_origin is None else 'installed_dlc'
                    if wheel_origin:
                        requires.add(wheel_origin)
                elif wheel.casefold() in shipped_wheels:
                    references, log['wheel'] = shipped_wheels[wheel.casefold()], 'shared_in_package'
                else:
                    references, log['wheel'] = None, 'converted_fm2'

                label = {f: fm2_text[ui_names.reference(fm2_car[f]) & 65535] + ' (FM2)'
                         for f in ('DisplayName', 'ModelShort')}
                car_keys = names(car_id, label, taken)
                for field, key in car_keys.items():
                    nodes['car']['row'][field] = key['reference']

                donor_zip = sources.disc_zip(sources.FM4_CARS, donor)
                car_payloads, origin, skipped = assets(car, donor, models, fm2_zips[car.lower()], donor_zip,
                                                       wheel if log['wheel'] == 'converted_fm2' else None)
                source_payloads = dict(car_payloads)
                car_payloads, paint = appearance_audit.with_cockpit_paint_scales(car_payloads, car)
                appearance = appearance_audit.audit(source_payloads, {**(references or {}), **car_payloads},
                                                    target_root, car, wheel, archive_read)
                for model in ('', '_lod0', '_cockpit'):
                    carbin_audit.parse(car_payloads[CARS / car / f'{car.lower()}{model}.carbin'], 'FM4')
                name = f'Thumbnails/Thumbnail_{car_id}.xds'
                for m in media:
                    with zipfile.ZipFile(m / 'UI/Textures.zip') as z:
                        if name in z.namelist():
                            thumb, thumb_report = thumbnail(z.read(name), controls[0])
                            break
                else:
                    raise c.MappingError(f'No FM2 {name}')

                if (car + '_CMT.xml').casefold() in tuning:
                    log['audio'] = 'native_fm4'
                else:
                    audio[AUDIO_ROOT / 'CarModelTuning' / f'{car}_CMT.xml'] = tuning[(donor + '_CMT.xml').casefold()]
                    log['audio'] = f'donor {donor}_CMT.xml'

                with work:
                    inserted = integration.insert_rows(work, rows)
                    for role, before in orphans.items():
                        node = nodes[role]
                        if node['row'] != before:
                            columns = [k for k in node['row'] if k != node['pk']]
                            work.execute(f'UPDATE {c.qi(node["table"])} SET ' +
                                         ','.join(f'{c.qi(k)}=?' for k in columns) + f' WHERE {c.qi(node["pk"])}=?',
                                         [node['row'][k] for k in columns] + [node['row'][node['pk']]])
                    replay = c.extract_stock(work, car)['nodes']
                    if {r: n['row'] for r, n in replay.items()} != {r: n['row'] for r, n in nodes.items()}:
                        raise c.MappingError('Package database does not reproduce the planned stock graph')
            except Exception as error:   # noqa: BLE001 - one failed car does not stop the package
                taken.difference_update(ui_names.reference(k['reference']) & 65535 for k in car_keys.values())
                failed.append({**log, 'error': f'{type(error).__name__}: {error}',
                               'trace': traceback.format_exc().splitlines()[-3:]})
                print('FAILED', car, failed[-1]['error'], flush=True)
                continue
            payloads.update(car_payloads)
            origins.update(origin)
            if log['wheel'] == 'converted_fm2':
                shipped_wheels[wheel.casefold()] = {p: d for p, d in car_payloads.items() if p.is_relative_to(WHEELS / wheel)}
            thumbs[THUMBNAILS / f'Thumbnail_{car_id}.xds'] = thumb
            keys.update({f'{car}/{f}': k for f, k in car_keys.items()})
            car_row = dict(nodes['car']['row'])
            entry = {**log, 'status': 'packaged', 'car_id': car_id, 'names': label, 'wheel_media': wheel,
                     'class_id': car_row['ClassID'], 'performance_index': car_row['PerformanceIndex'],
                     'pi_rule': next((e.get('rule') for e in applied['changed'] if e['column'] == 'PerformanceIndex'),
                                     'donor'),
                     'physics': {'changed': len(applied['changed']), 'removed_roles': applied['removed_roles'],
                                 'added_roles': applied['added_roles']},
                     'requires': sorted(requires), 'merged_rows': inserted}
            packaged.append(entry)
            car_reports = reports / 'cars' / car
            car_reports.mkdir(parents=True)
            c.dump(car_reports / 'physics.json', applied)
            c.dump(car_reports / 'database.json', dict(donor=donor, car=car_row, names=car_keys,
                                                       allocation={r: [n['table'], n['row'][n['pk']]]
                                                                   for r, n in nodes.items()},
                                                       presentation_rows=[r for r in rows if r['table'] in PRESENTATION]))
            c.dump(car_reports / 'appearance_validation.json', appearance)
            c.dump(car_reports / 'ui_thumbnail_validation.json', thumb_report)
            c.dump(car_reports / 'assets.json', dict(origin=origin, fm2_files_not_shipped=skipped,
                                                     cockpit_paint_scales=paint))
            inputs.update(appearance['inputs'])
            print('packaged', car, donor, log['wheel'], log['audio'], car_row['ClassID'], flush=True)
        if work.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise c.MappingError('Package database failed integrity_check')

    if not packaged:
        raise c.MappingError('No car could be packaged')
    strings, priority, string_report = string_archive(target_root, content_root, keys)
    inputs.update(string_report.pop('inputs'))
    archives = {CARS / (e['media'] + '.zip'): integration.stored_zip(payloads, CARS / e['media']) for e in packaged}
    archives.update({WHEELS / (w + '.zip'): integration.stored_zip(payloads, WHEELS / w)
                     for w in {e['wheel_media'] for e in packaged if e['wheel'] == 'converted_fm2'}})
    archives[THUMBNAILS.with_suffix('.zip')] = integration.stored_zip(thumbs, THUMBNAILS)
    archives[ui_names.OVERRIDE] = strings
    priorities = {ui_names.OVERRIDE: priority}
    if audio:
        archives[AUDIO] = integration.stored_zip(audio, AUDIO_ROOT)
        priorities[AUDIO] = AUDIO_PRIORITY
    for relative in archives:
        if (disc / relative).exists():
            raise c.MappingError(f'Refusing to replace an existing asset: {relative}')
    manifest_data = integration.extend_zip_manifest((target_root / 'zipmanifest.xml').read_bytes(), archives, (),
                                                    priorities)
    for relative, data in {**archives, Path('Media/zipmanifest.xml'): manifest_data}.items():
        (files / relative).parent.mkdir(parents=True, exist_ok=True)
        with (files / relative).open('xb') as f:
            f.write(data)
    for path, digest in inputs.items():
        if c.sha(path) != digest:
            raise c.MappingError(f'Input changed during packaging: {path}')
    c.dump(reports / 'ui_name_validation.json', string_report)
    c.dump(reports / 'failed.json', failed)
    manifest = {
        'package_type': 'Offline file overlay; not a complete game disc',
        'cars': packaged, 'failed': [{k: f[k] for k in ('media', 'error')} for f in failed],
        'packaged_count': len(packaged), 'failed_count': len(failed),
        'requires': sorted({x for e in packaged for x in e['requires']}),
        'inputs': inputs, 'sources_unchanged': True, 'overlays_checked': len(overlays),
        'content_root': str(content_root), 'study': str(study),
        'audio_override': {'archive': AUDIO.as_posix(), 'priority': AUDIO_PRIORITY,
                           'entries': sorted(p.relative_to(AUDIO_ROOT).as_posix() for p in audio)},
        'donor_values': ['physics groups not chosen by the FM2 study', 'List_Wheels row except MediaName',
                         'CarPartPositions', 'CameraOverrides', 'CarExceptions', 'Combo_Colors', 'calipers',
                         'rotors', '_lod0/_cockpit headers', 'Data_Engine audio', 'CMT audio tuning when FM4 has none',
                         'MakeID when FM4 has no matching make'],
        'merged_database_sha256': c.sha(database), 'zip_manifest_sha256': c.sha(files / 'Media/zipmanifest.xml'),
        'archives': {p.as_posix(): sha(d) for p, d in archives.items()},
        'installed': False, 'accepted': False, 'runtime_tested': False,
        'files': {p.relative_to(files).as_posix(): c.sha(p) for p in files.rglob('*') if p.is_file()},
    }
    c.dump(out / 'manifest.json', manifest)
    return manifest


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--out', type=Path, required=True, help='new package folder')
    p.add_argument('--cars', nargs='*', help='FM2 MediaNames (default: every fm2_only car of the inventory)')
    p.add_argument('--fm4', type=Path, default=c.FM4_DEFAULT)
    p.add_argument('--content-root', type=Path, default=CONTENT)
    p.add_argument('--study', type=Path, default=STUDY)
    p.add_argument('--models-root', type=Path, default=OUT / 'models')
    p.add_argument('--helper', type=Path, default=fm4_models.HELPER, help='reviewed CPU-only carbin-cpu.exe')
    p.add_argument('--donor', action='append', metavar='CAR=DONOR',
                   help='FM4 donor for one car instead of the automatic choice (same pool and steering side)')
    a = p.parse_args()
    m = build(a.out, a.cars, a.fm4, a.content_root, a.study, a.models_root, a.helper, parse_donors(a.donor))
    print(json.dumps({k: m[k] for k in ('packaged_count', 'failed_count', 'requires', 'failed')}, indent=1))


if __name__ == '__main__':
    main()
