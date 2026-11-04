"""FM2 -> FM4 stock physics: extractor, study of the cars both games ship, and rules (REPORT section 10).

`extract(db, car_id)` reads the FM2 stock configuration (IsStock=1, Ordinal/EngineID relations)
and lays it out in FM4 roles, tables and column names like `converter.extract_stock`. FM4 columns
without an FM2 source stay unset; in a package they keep the donor's value.

`study` follows the FM3 path's `value_scales` method: FM2 and FM4 pairs with the same Id,
MediaName, year and make; the training/validation split is grouped by FM2 engine (1/5 validation);
candidates are chosen by 5-fold engine-grouped CV on training and frozen before validation.

`CMHeight` is estimated from FM2's CMHeight, the weighted stock ride height and the bounding box
of the FM2 `.carbin` model (`cm_study`, REPORT 11.1), PerformanceIndex by a hinge model on stored
FM2 results (`pi_study`, REPORT 13). FM2 aspiration parts the donor lacks are installed as new
stock rows (`apply`, REPORT 11.2).
"""
from collections import Counter, defaultdict
from contextlib import closing
from functools import lru_cache
import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics
import zipfile

from . import carbin, sources
from ..fm3 import converter as c, value_scales as vs
from ..paths import PROJECT_ROOT

FM2_DB = sources.FM2_DB
OUT = PROJECT_ROOT / 'outputs/car-fm2-research-2026-11-02/physics'
SALT = 'fm2-fm4-calibration-v1'

# FM2 part table -> FM4 role (= FM4 table name in converter.extract_stock), same column names.
PARTS = [
    ('List_UpgradeEngine', 'Ordinal', 'List_UpgradeEngine'),
    ('List_UpgradeWeight', 'Ordinal', 'List_UpgradeCarBodyWeight'),
    ('List_UpgradeFlywheel', 'Ordinal', 'List_UpgradeEngineFlywheel'),
    ('List_UpgradeClutch', 'Ordinal', 'List_UpgradeDrivetrainClutch'),
    ('List_UpgradeDifferential', 'Ordinal', 'List_UpgradeDrivetrainDifferential'),
    ('List_UpgradeDriveline', 'Ordinal', 'List_UpgradeDrivetrainDriveline'),
    ('List_UpgradeTransmission', 'Ordinal', 'List_UpgradeDrivetrainTransmission'),
    ('List_UpgradeSpringDamper', 'Ordinal', 'List_UpgradeSpringDamper'),
    ('List_UpgradeBrakes', 'Ordinal', 'List_UpgradeBrakes'),
    ('List_UpgradeTireCompound', 'Ordinal', 'List_UpgradeTireCompound'),
    ('List_UpgradeRearWing', 'Ordinal', 'List_UpgradeRearWing'),
    ('List_UpgradeFrontBumper', 'Ordinal', 'List_UpgradeCarBodyFrontBumper'),
    ('List_UpgradeRearBumper', 'Ordinal', 'List_UpgradeCarBodyRearBumper'),
    ('List_UpgradeHood', 'Ordinal', 'List_UpgradeCarBodyHood'),
    ('List_UpgradeSideSkirt', 'Ordinal', 'List_UpgradeCarBodySideSkirt'),
    ('List_UpgradeEngineCamValves', 'EngineID', 'List_UpgradeEngineCamshaft'),
    ('List_UpgradeEngineBlock', 'EngineID', 'List_UpgradeEngineDisplacement'),
    ('List_UpgradeEngineExhaust', 'EngineID', 'List_UpgradeEngineExhaust'),
    ('List_UpgradeEngineFuelSystem', 'EngineID', 'List_UpgradeEngineFuelSystem'),
    ('List_UpgradeEngineIgnition', 'EngineID', 'List_UpgradeEngineIgnition'),
    ('List_UpgradeEngineIntake', 'EngineID', 'List_UpgradeEngineIntake'),
    ('List_UpgradeEngineIntercooler', 'EngineID', 'List_UpgradeEngineIntercooler'),
    ('List_UpgradeEngineCSC', 'EngineID', 'List_UpgradeEngineCSC'),
    ('List_UpgradeEngineDSC', 'EngineID', 'List_UpgradeEngineDSC'),
    ('List_UpgradeEngineTurbo', 'EngineID', 'turbo'),
]
# One FM2 row splits into two FM4 roles per axle: {role: {FM4 column: FM2 column}}.
SPLIT = [
    ('List_UpgradeTireWidth', {'List_UpgradeCarBodyTireWidthFront': {'FrontTireWidth': 'FrontTireWidth'},
                               'List_UpgradeCarBodyTireWidthRear': {'RearTireWidth': 'RearTireWidth'}}),
    ('List_UpgradeRimSize', {'List_UpgradeRimSizeFront': {'FrontWheelDiameter': 'FrontWheelDiameter'},
                             'List_UpgradeRimSizeRear': {'RearWheelDiameter': 'RearWheelDiameter'}}),
]
COMMON_PART = ('MassDiff', 'DragScale', 'WindInstabilityScale', 'Price', 'ManufacturerID', 'Level')
# FM4 columns that FM2 keeps in another table or name: role -> {FM4 column: (FM2 role, FM2 column)}.
MOVED = {
    'car': {'DriveTypeID': ('engine', 'DriveTypeID'), 'NumGears': ('car', 'StockGears'),
            'FrontTireWidthMM': ('car', 'StockTire-FrontWidth-mm'),
            'FrontTireAspect': ('car', 'StockTire-FrontAspect-pct'),
            'FrontWheelDiameterIN': ('car', 'StockTire-FrontWheel-in'),
            'RearTireWidthMM': ('car', 'StockTire-RearWidth-mm'),
            'RearTireAspect': ('car', 'StockTire-RearAspect-pct'),
            'RearWheelDiameterIN': ('car', 'StockTire-RearWheel-in'),
            'WeightDistribution': ('car', 'FrontWeight-pct'), 'Displacement': ('engine', 'Disp_cc'),
            'CylinderID': ('engine', 'CylinderID'), 'EngineConfigID': ('engine', 'ConfigID'),
            'AspirationTypeId': ('engine', 'AspirationID_Stock'),
            'FrontStockRideHeight': ('car', 'ModelFrontStockRideHeight'),
            'RearStockRideHeight': ('car', 'ModelRearStockRideHeight')},
    'body': {k: ('car', k) for k in ('ModelWheelbase', 'ModelFrontTrackOuter', 'ModelRearTrackOuter',
                                     'ModelFrontStockRideHeight', 'ModelRearStockRideHeight',
                                     'BottomCenterWheelbasePosx', 'BottomCenterWheelbasePosy')}
            | {'BottomCenterWheelbasePosZ': ('car', 'BottomCenterWheelbasePosz')},
    'drivetrain': {'DrivetypeID': ('engine', 'DriveTypeID')},
    'engine': {'Carbureted': ('List_UpgradeEngineFuelSystem', 'Carbureted')},
    'List_UpgradeEngineDisplacement': {'Disp': ('engine', 'Disp_cc')},
}
# Row keys and references to other rows: not compared (their values are row numbers, not physics).
KEYS = {'Id', 'ID', 'Ordinal', 'EngineID', 'CarBodyID', 'CarBodyId', 'CarbodyId', 'DrivetrainID',
        'DrivetrainId', 'IsStock', 'AeroPhysicsID', 'AntiSwayPhysicsID', 'FrontSpringDamperPhysicsID',
        'RearSpringDamperPhysicsID', 'TorqueCurveFullThrottleID', 'TorqueCurveZeroThrottleID',
        'SpringDamperPhysicsID', 'AntiSwayPhysicsID', 'AeroPhysicsID', 'TorqueCurveID', 'StockWheelID',
        'PartsStringID', 'PartsStringId', 'DisplayName', 'ModelShort', 'MediaName', 'EngineName',
        'Thumbnail', 'ContentId', 'ModelId', 'PowertrainId', 'WheelID', 'Id'}


def rows(db, table, where, args):
    return [dict(r) for r in db.execute(f'SELECT * FROM {c.qi(table)} WHERE {where}', args)]


def stock(db, table, scope, value):
    return c.one(rows(db, table, f'{c.qi(scope)}=? AND IsStock=1', (value,)), f'{table} {value}')


def auto_steer(fm4, car):
    """The FM4 AutoSteerOverrides row with the same STM thresholds as FM2 (as the FM3 converter)."""
    found = rows(fm4, 'AutoSteerOverrides', 'STMSlipMin=? AND STMSlipMax=?',
                 (car['AssistsSTMSlipDefMin'], car['AssistsSTMSlipDefMax']))
    payloads = {json.dumps({k: v for k, v in r.items() if k != 'Id'}, sort_keys=True) for r in found}
    return min(r['Id'] for r in found) if len(payloads) == 1 else None


@lru_cache(maxsize=1)
def fm2_zips():
    return sources.fm2_zips('cars')


def model_bounds(media):
    """(min, max) Y of the FM2 main model's LOD1 vertices, position + section origin, in metres.

    Max matches FM4's PristineBoundingBoxMaxY of the same car (median difference 0 over 184
    pairs). Min does not: the FM4 bounding box reaches +-0.27 m below the FM2 body."""
    with zipfile.ZipFile(fm2_zips()[media.casefold()]) as z:
        name = c.one([i.filename for i in z.infolist() if i.filename.casefold() == media.casefold() + '.carbin'],
                     f'{media}.carbin')
        model = carbin.parse(z.read(name))
    ys = [(model.glass if s.buffer == 'glass' else model.body)[i][0][1] + s.origin[1]
          for s in model.sections for sub in s.subsections if sub.lod == 1 for i in sub.indices if i >= 0]
    if not ys:
        raise c.MappingError(f'{media}: no LOD1 vertices')
    return min(ys), max(ys)


def extract(db, car_id, fm4=None):
    """FM2 stock configuration in FM4 roles/tables/columns. Raw FM2 values, no rules. With `fm4`,
    `AutoSteerOverrideID` is looked up from the FM2 STM thresholds. `bounds` = `model_bounds`."""
    car = c.one(rows(db, 'Data_Car', 'Id=?', (car_id,)), f'Data_Car {car_id}')
    choice = stock(db, 'List_UpgradeEngine', 'Ordinal', car_id)
    engine = c.one(rows(db, 'Data_Engine', 'EngineID=?', (choice['EngineID'],)), 'Data_Engine')
    source = {'car': car, 'engine': engine}
    for table, scope, role in PARTS:
        found = rows(db, table, f'{c.qi(scope)}=? AND IsStock=1',
                     (car_id if scope == 'Ordinal' else engine['EngineID'],))
        if len(found) > 1:
            raise c.MappingError(f'{table}: more than one stock row')
        if found:
            source[role] = found[0]
    for table, roles in SPLIT:
        part = stock(db, table, 'Ordinal', car_id)
        for role, columns in roles.items():
            source[role] = {**{k: part[k] for k in COMMON_PART if k in part},
                            **{k: part[v] for k, v in columns.items()}}
    sway = stock(db, 'List_UpgradeAntiSway', 'Ordinal', car_id)
    links = [('spring.front', 'List_SpringDamperPhysics', 'SpringDamperPhysicsID',
              source['List_UpgradeSpringDamper']['FrontSpringDamperPhysicsID']),
             ('spring.rear', 'List_SpringDamperPhysics', 'SpringDamperPhysicsID',
              source['List_UpgradeSpringDamper']['RearSpringDamperPhysicsID']),
             ('antiroll.front', 'List_AntiSwayPhysics', 'AntiSwayPhysicsID', sway['FrontAntiSwayPhysicsID']),
             ('antiroll.rear', 'List_AntiSwayPhysics', 'AntiSwayPhysicsID', sway['RearAntiSwayPhysicsID']),
             ('torque.full', 'List_TorqueCurve', 'TorqueCurveID',
              source['List_UpgradeEngineCamshaft']['TorqueCurveFullThrottleID']),
             ('torque.zero', 'List_TorqueCurve', 'TorqueCurveID',
              source['List_UpgradeEngineCamshaft']['TorqueCurveZeroThrottleID']),
             ('wheel', 'List_Wheels', 'ID', car['StockWheelID'])]
    for role, part in (('aero.front', 'List_UpgradeCarBodyFrontBumper'), ('aero.rear', 'List_UpgradeRearWing')):
        if part in source:
            links.append((role, 'List_AeroPhysics', 'AeroPhysicsID', source[part]['AeroPhysicsID']))
    for role, table, column, value in links:
        source[role] = c.one(rows(db, table, f'{c.qi(column)}=?', (value,)), role)
    modifier = rows(db, 'TireMod_FrictionScale', 'Ordinal=?', (car_id,))
    if modifier:
        source['tire.modifier'] = c.one(modifier, 'tire modifier')
    nodes = {role: dict(row) for role, row in source.items() if role != 'torque.zero'}
    nodes['body'] = {}
    nodes['drivetrain'] = {}
    for role, moved in MOVED.items():
        for target, (origin, column) in moved.items():
            if origin in source and column in source[origin]:
                nodes[role][target] = source[origin][column]
    # FM4 keeps the zero-throttle curve scale on the full-throttle curve (as on the FM3 path).
    nodes['torque.full']['ZeroThrottleTorqueScale'] = source['torque.zero']['TorqueScale']
    if fm4 is not None:
        steer = auto_steer(fm4, car)
        if steer is not None:
            nodes['car']['AutoSteerOverrideID'] = steer
    return {'car_id': car_id, 'media_name': car['MediaName'], 'engine_id': engine['EngineID'],
            'nodes': nodes, 'torque_zero': source['torque.zero'], 'bounds': model_bounds(car['MediaName'])}


def fm4_nodes(db, media):
    graph = c.extract_stock(db, media)
    nodes = {}
    for role, node in graph['nodes'].items():
        if role in ('List_UpgradeEngineTurboSingle', 'List_UpgradeEngineTurboTwin'):
            role = 'turbo'
        nodes[role] = {'table': node['table'], 'row': node['row']}
    return nodes


def pairs(fm2, fm4):
    a = {r['Id']: r for r in rows(fm2, 'Data_Car', '1', ())}
    b = {r['Id']: r for r in rows(fm4, 'Data_Car', '1', ())}
    out, excluded = [], []
    for identity in sorted(a.keys() & b.keys()):
        x, y = a[identity], b[identity]
        if (x['MediaName'], x['Year'], x['MakeID']) != (y['MediaName'], y['Year'], y['MakeID']):
            excluded.append({'id': identity, 'fm2': x['MediaName'], 'fm4': y['MediaName'],
                             'reason': 'identity_or_year_mismatch'})
            continue
        engine = stock(fm2, 'List_UpgradeEngine', 'Ordinal', identity)['EngineID']
        bucket = int(hashlib.sha256(f'{SALT}:{engine}'.encode()).hexdigest()[:8], 16) % 5
        out.append({'id': identity, 'media': x['MediaName'], 'engine': engine,
                    'split': 'validation' if bucket == 0 else 'training'})
    return out, excluded


def torque_curve(nodes):
    """Effective full-throttle curve (rpm, Nm x GameTorqueScale); sample i at i * MaxRPM / (N - 1)."""
    curve, cam = nodes['torque.full'], nodes['List_UpgradeEngineCamshaft']
    n, top = curve['NumTorqueValues'], cam['TorqueCurveMaxRPM']
    scale = curve['TorqueScale'] * nodes['car']['GameTorqueScale']
    return [(i * top / (n - 1), scale * curve[f'v{i}']) for i in range(n)]


def curve_error(candidate, reference):
    """Mean |torque difference| on the reference rpm grid, divided by the reference peak torque."""
    def at(curve, rpm):
        if rpm >= curve[-1][0]:
            return curve[-1][1]
        for (r0, t0), (r1, t1) in zip(curve, curve[1:]):
            if r0 <= rpm <= r1:
                return t0 + (t1 - t0) * (rpm - r0) / (r1 - r0)
    peak = max(t for _, t in reference)
    return sum(abs(at(candidate, r) - t) for r, t in reference) / len(reference) / peak


def flat(nodes):
    """fm4_nodes -> {role: row}, the same shape as extract()['nodes']."""
    return {role: node['row'] for role, node in nodes.items()}


def fm4_index(fm4):
    out = []
    for car in rows(fm4, 'Data_Car', 'IsDrivable=1', ()):
        try:
            nodes = flat(fm4_nodes(fm4, car['MediaName']))
        except c.MappingError:
            continue
        out.append({'id': car['Id'], 'media': car['MediaName'], 'make': car['MakeID'],
                    'drive': nodes['drivetrain']['DrivetypeID'], 'mass': nodes['List_UpgradeCarBodyWeight']['Mass'],
                    'power': nodes['engine']['EngineGraphingMaxPower'], 'nodes': nodes})
    return out


def donor(index, source, exclude_id):
    """Donor as in packages: an FM4 car of the same make and drive type, nearest in mass and power."""
    nodes = source['nodes']
    mass, power = nodes['List_UpgradeCarBodyWeight']['Mass'], nodes['engine']['EngineGraphingMaxPower']
    pool = [d for d in index if d['id'] != exclude_id and d['drive'] == nodes['drivetrain']['DrivetypeID']]
    pool = [d for d in pool if d['make'] == nodes['car']['MakeID']] or pool
    return min(pool, key=lambda d: (abs(math.log(d['mass'] / mass)) + abs(math.log(d['power'] / power)), d['id']))


WEIGHT = 'List_UpgradeCarBodyWeight'
TABLES = {'spring.front': 'List_SpringDamperPhysics', 'spring.rear': 'List_SpringDamperPhysics',
          'antiroll.front': 'List_AntiSwayPhysics', 'antiroll.rear': 'List_AntiSwayPhysics',
          'aero.front': 'List_AeroPhysics', 'aero.rear': 'List_AeroPhysics', 'torque.full': 'List_TorqueCurve',
          'wheel': 'List_Wheels', 'tire.modifier': 'TireMod_FrictionScale', 'car': 'Data_Car',
          'body': 'Data_CarBody', 'engine': 'Data_Engine', 'drivetrain': 'Data_Drivetrain'}


def fm4_table(role, nodes=None):
    if role == 'turbo' and nodes:
        return nodes['turbo']['table']
    return TABLES.get(role, role)


def observations(fm2, fm4):
    found, excluded = pairs(fm2, fm4)
    index = fm4_index(fm4)
    obs, curves, cm, pi, missing = [], [], [], [], Counter()
    for pair in found:
        source = extract(fm2, pair['id'], fm4)
        native = fm4_nodes(fm4, pair['media'])
        target = flat(native)
        chosen = donor(index, source, pair['id'])
        pair['donor'] = chosen['media']
        features = cm_features(source['nodes'], source['bounds'])
        cm.append({'media': pair['media'], 'split': pair['split'], 'engine': pair['engine'], 'features': features,
                   'y': target[WEIGHT]['CMHeight']})
        pi.append({'media': pair['media'], 'split': pair['split'], 'engine': pair['engine'],
                   'car': pi_car(source['nodes']['car']), 'y': target['car']['PerformanceIndex']})
        for role, row in source['nodes'].items():
            if role not in target:
                missing[role] += 1
                continue
            for column, value in row.items():
                if column in KEYS or column not in target[role] or \
                        role.startswith('torque') and column[:1] == 'v' and column[1:].isdigit():
                    continue
                obs.append({'media': pair['media'], 'split': pair['split'], 'engine': pair['engine'],
                            'drive': source['nodes']['drivetrain']['DrivetypeID'], 'role': role, 'table': native[role]['table'], 'column': column, 'x': value,
                            'y': target[role][column], 'd': chosen['nodes'].get(role, {}).get(column)})
                if role == WEIGHT and column == 'CMHeight':
                    obs[-1]['cm'] = features
                if role == 'car' and column == 'PerformanceIndex':
                    obs[-1]['pi'] = pi[-1]['car']
        reference = torque_curve(target)
        curves.append({'media': pair['media'], 'split': pair['split'], 'engine': pair['engine'],
                       'fm2': curve_error(torque_curve(source['nodes']), reference),
                       'donor': curve_error(torque_curve(chosen['nodes']), reference),
                       'samples': (source['nodes']['torque.full']['NumTorqueValues'],
                                   target['torque.full']['NumTorqueValues'])})
    return {'pairs': found, 'excluded': excluded, 'observations': obs, 'curves': curves, 'cm': cm, 'pi': pi,
            'roles_missing_in_fm4': dict(missing),
            'conventions': drive_conventions(index) | table_conventions(fm4)}


TIRES = {'FrontTireWidthMM', 'FrontTireAspect', 'FrontWheelDiameterIN', 'RearTireWidthMM', 'RearTireAspect',
         'RearWheelDiameterIN'}


def group(role, column):
    """Columns that must come from the same source: tuning triplets, both axles, gears, the torque
    curve with GameTorqueScale, body aero with GameDragScale, mass. Stored performance metadata
    (ratings, Sim*, engine graphs) does not change physics and is decided per column."""
    if c.category(fm4_table(role), column) == 'stored_performance_metadata':
        return f'{role}.{column}'
    if role == 'car':
        if column in ('CurbWeight', 'WeightDistribution'):
            return 'mass'
        if column == 'NumGears':
            return 'transmission'
        if column in ('FrontStockRideHeight', 'RearStockRideHeight'):
            return 'springs'
        if column == 'GameTorqueScale':
            return 'torque'
        if column.startswith('BodyAero') or column == 'GameDragScale':
            return 'body_aero'
        return 'tires' if column in TIRES else 'car.' + column
    if role == 'List_UpgradeCarBodyWeight':
        return 'mass'
    if role in ('torque.full', 'List_UpgradeEngineCamshaft', 'List_UpgradeEngineDisplacement'):
        return 'torque'
    if role == 'List_UpgradeDrivetrainTransmission':
        return 'transmission'
    if role.startswith(('List_UpgradeRimSize', 'List_UpgradeCarBodyTireWidth')):
        return 'tires'
    for prefix, name in (('spring.', 'springs'), ('antiroll.', 'antiroll'), ('aero.', 'aero_parts')):
        if role.startswith(prefix):
            return name
    if role in COUPLED or role == 'body':
        return role
    return f'{role}.{column}'


# Parts whose columns work together (boost scales, per-axle LSD); other part columns are decided alone.
COUPLED = {'turbo', 'List_UpgradeEngineCSC', 'List_UpgradeEngineDSC', 'List_UpgradeDrivetrainDifferential'}


def drive_conventions(index):
    """Differential columns with a single FM4 value on >= 99% of cars of a drive type
    (e.g. centre LSD 0 on every RWD car)."""
    out = {}
    for column in ('FrontLimitedSlipTorqueAccel', 'FrontLimitedSlipTorqueDecel', 'RearLimitedSlipTorqueAccel',
                   'RearLimitedSlipTorqueDecel', 'CenterLimitedSlipTorqueAccel', 'CenterLimitedSlipTorqueDecel'):
        for drive in sorted({d['drive'] for d in index}):
            values = Counter(d['nodes']['List_UpgradeDrivetrainDifferential'][column] for d in index
                             if d['drive'] == drive and 'List_UpgradeDrivetrainDifferential' in d['nodes'])
            value, n = values.most_common(1)[0]
            if n / sum(values.values()) >= vs.POLICY['constant_coverage']:
                out[f'{drive}:{column}'] = {'value': value, 'cars': sum(values.values()), 'coverage': n / sum(values.values())}
    return out


def table_conventions(fm4):
    """Aspiration part columns with a single FM4 value on >= 99% of their table's stock rows, e.g.
    TorqueDropOffRPM0 9000 on every stock turbo/SC (FM2: 8000), part price and mass 0."""
    out = {}
    for table in ASPIRATION:
        stock_rows = rows(fm4, table, 'IsStock=1', ())
        for column in stock_rows[0]:
            if column in KEYS:
                continue
            value, n = Counter(r[column] for r in stock_rows).most_common(1)[0]
            if n / len(stock_rows) >= vs.POLICY['constant_coverage']:
                out[f'{table}:{column}'] = {'value': value, 'cars': len(stock_rows), 'coverage': n / len(stock_rows)}
    return out


def errors(items, predict, continuous):
    """Normalised error: MAE / mean |FM4| (continuous) or 1 - match rate (categories)."""
    if continuous:
        scale = sum(abs(r['y']) for r in items) / len(items) or 1.0
        return sum(abs(predict(r) - r['y']) for r in items) / len(items) / scale
    return sum(not vs.same(predict(r), r['y']) for r in items) / len(items)


def convention(conventions, drive, table, column):
    if table == 'List_UpgradeDrivetrainDifferential':
        return conventions.get(f'{drive}:{column}')
    return conventions.get(f'{table}:{column}')


def engine_folds(items, k=vs.POLICY['folds']):
    """Engine-grouped CV folds on training. The salt differs from the split's, because the split
    hash puts every training engine outside bucket 0."""
    fold = lambda e: int(hashlib.sha256(f'{SALT}:cv:{e}'.encode()).hexdigest()[:8], 16) % k
    return [([i for i in items if fold(i['engine']) != f], [i for i in items if fold(i['engine']) == f])
            for f in range(k)]


# CMHeight: the FM3 coordinate formula (code_semantics, no fit) and a fixed linear menu; chosen by CV.
CM_CANDIDATES = [('coordinate', ()), ('linear', ('cm_height',)), ('linear', ('cm_height', 'stock_height')),
                 ('linear', ('cm_height', 'stock_height', 'bbox_height')),
                 ('linear', ('cm_height', 'stock_height', 'block_height')),
                 ('linear', ('cm_height', 'stock_height', 'bbox_height', 'block_height'))]


def cm_features(nodes, bounds):
    """CMHeight features of an FM2 source. `stock_height` = front/rear stock ride height weighted by
    CMBackFront, which FM4 subtracts from CMHeight (docs/fm3.md, coordinate adapter); `bbox_height`
    from the model."""
    car, weight = nodes['car'], nodes[WEIGHT]
    front, rear = car['FrontStockRideHeight'], car['RearStockRideHeight']
    return {'cm_height': weight['CMHeight'], 'stock_height': rear + (front - rear) * weight['CMBackFront'],
            'bbox_height': bounds[1] - bounds[0], 'block_height': weight['BlockDimY']}


def cm_fit(items, kind, features):
    import numpy as np
    model = {'kind': kind, 'features': list(features),
             'domain': {f: [min(i['features'][f] for i in items), max(i['features'][f] for i in items)]
                        for f in features}}
    if kind == 'linear':
        x = np.array([[1.0] + [i['features'][f] for f in features] for i in items])
        model['coef'] = [float(b) for b in np.linalg.lstsq(x, np.array([i['y'] for i in items]), rcond=None)[0]]
    return model


def cm_predict(model, features):
    """(value, feature outside the training domain or None). Outside the domain: coordinate formula."""
    coordinate = features['cm_height'] + features['stock_height']
    for f in model['features']:
        low, high = model['domain'][f]
        if not low <= features[f] <= high:
            return round(coordinate, 4), f
    if model['kind'] == 'coordinate':
        return round(coordinate, 4), None
    return round(model['coef'][0] + sum(b * features[f] for b, f in zip(model['coef'][1:], model['features'])), 4), None


def cm_study(items, rule):
    """Choose the CMHeight candidate by engine-grouped CV on training, then validate. Accepted when
    the validation MAE is below the `value_scales` linear rule and the coordinate formula."""
    train = [i for i in items if i['split'] == 'training']
    valid = [i for i in items if i['split'] == 'validation']
    mae = lambda model, part: statistics.mean(abs(cm_predict(model, i['features'])[0] - i['y']) for i in part)
    candidates = []
    for kind, features in CM_CANDIDATES:
        cv = [abs(cm_predict(cm_fit(fit, kind, features), i['features'])[0] - i['y'])
              for fit, held in engine_folds(train) if held for i in held]
        candidates.append({'kind': kind, 'features': list(features), 'cv_mae': statistics.mean(cv),
                           'cv_p90': sorted(cv)[math.ceil(.9 * len(cv)) - 1]})
    best = min(candidates, key=lambda e: (e['cv_mae'], len(e['features'])))
    model = cm_fit(train, best['kind'], best['features'])
    model['validation_mae'] = mae(model, valid)
    errors = sorted(abs(cm_predict(model, i['features'])[0] - i['y']) for i in valid)
    model['validation_p90'] = errors[math.ceil(.9 * len(errors)) - 1]
    model['abstained_validation'] = sum(cm_predict(model, i['features'])[1] is not None for i in valid)
    ruled = lambda x: vs.predict(rule, x) if rule and vs.in_domain(rule, x) else x
    baselines = {'coordinate': mae(cm_fit(train, 'coordinate', ()), valid),
                 'value_scales_rule': statistics.mean(abs(ruled(i['features']['cm_height']) - i['y']) for i in valid),
                 'fm2_identity': statistics.mean(abs(i['features']['cm_height'] - i['y']) for i in valid)}
    model['accepted'] = model['validation_mae'] <= baselines['coordinate'] and \
        model['validation_mae'] < min(baselines['value_scales_rule'], baselines['fm2_identity'])
    return {**model, 'candidates': candidates, 'validation_baselines': baselines,
            'pairs': {'training': len(train), 'validation': len(valid)}}


# PerformanceIndex: FM4 classes are only 0.06-0.14 wide, so the value_scales linear rule (MAE 0.027)
# often misses by one class. Candidates: a hinge on FM2 PI at the FM2 class bounds (as the FM3 PI
# study), plus stored FM2 simulation results; ordered from the simplest.
PI_SIM = ('SimTopSpeed', 'SimTimeTo60MPH', 'SimTimeTo100MPH', 'SimTimeQuarterMile', 'SimSpeedQuarterMile',
          'SimLatGees60MPH', 'SimLatGees120MPH', 'SimBrakeDistance60MPH', 'SimBrakeDistance100MPH')
PI_CANDIDATES = [('linear', ()), ('hinge', ()),
                 ('hinge', ('SimSpeedQuarterMile', 'SimLatGees60MPH', 'SimBrakeDistance60MPH', 'Year')),
                 ('hinge', PI_SIM), ('hinge', PI_SIM + ('Year',))]
PI_KNOTS = (0.265, 0.3565, 0.4596, 0.585, 0.72)   # FM2 CarClasses.MaxPerformanceIndex D..S
PI_TOLERANCE = 1.05   # simplest candidate within 5% of the best CV MAE, as performance_index


def pi_car(car):
    return {f: car[f] for f in ('PerformanceIndex', 'Year') + PI_SIM}


def pi_basis(model, car):
    x = car['PerformanceIndex']
    return [1.0, x] + [max(0.0, x - k) for k in model['knots']] + [float(car[f]) for f in model['features']]


def pi_fit(items, kind, features):
    import numpy as np
    pis = [i['car']['PerformanceIndex'] for i in items]
    model = {'kind': kind, 'features': list(features),
             'knots': [k for k in PI_KNOTS if min(pis) < k < max(pis)] if kind == 'hinge' else [],
             'domain': {f: [min(i['car'][f] for i in items), max(i['car'][f] for i in items)]
                        for f in ('PerformanceIndex',) + tuple(features)}}
    x = np.array([pi_basis(model, i['car']) for i in items])
    model['coef'] = [float(b) for b in np.linalg.lstsq(x, np.array([i['y'] for i in items]), rcond=None)[0]]
    return model


def pi_monotone(model):
    """The mapped PI must rise with FM2 PI on every hinge segment."""
    slope = model['coef'][1]
    for w in model['coef'][2:2 + len(model['knots'])]:
        if slope <= 0:
            return False
        slope += w
    return slope > 0


def pi_predict(model, car):
    """(PI, feature outside the training domain or None). Outside the domain there is no prediction."""
    for f, (low, high) in model['domain'].items():
        if not low <= car[f] <= high:
            return None, f
    return round(sum(b * v for b, v in zip(model['coef'], pi_basis(model, car))), 6), None


def pi_study(items, rule, bounds):
    """Choose the PI model by engine-grouped CV on training, then measure validation. Accepted when
    monotone and its validation MAE and class match are no worse than the value_scales linear rule."""
    from ..fm3 import performance_index as pim
    train = [i for i in items if i['split'] == 'training']
    valid = [i for i in items if i['split'] == 'validation']
    ruled = lambda i: vs.predict(rule, i['car']['PerformanceIndex']) \
        if rule and vs.in_domain(rule, i['car']['PerformanceIndex']) else i['car']['PerformanceIndex']

    def score(predict, part):
        pairs = [(predict(i), i['y']) for i in part]
        used = [(p, y) for p, y in pairs if p is not None]
        cls = lambda v: pim.class_for(min(max(v, 1e-6), bounds[-1][1]), bounds)
        return {'n': len(used), 'abstained': len(pairs) - len(used),
                'mae': statistics.mean(abs(p - y) for p, y in used),
                'class_match_rate': statistics.mean(cls(p) == cls(y) for p, y in used)}

    candidates = []
    for kind, features in PI_CANDIDATES:
        cv, monotone = [], True
        for fit, held in engine_folds(train):
            if fit and held:
                model = pi_fit(fit, kind, features)
                monotone &= pi_monotone(model)
                cv += [(pi_predict(model, i['car'])[0] or ruled(i), i['y']) for i in held]
        candidates.append({'kind': kind, 'features': list(features), 'monotone_every_fold': monotone,
                           'cv_mae': statistics.mean(abs(p - y) for p, y in cv)})
    eligible = [e for e in candidates if e['monotone_every_fold']]
    best = min(e['cv_mae'] for e in eligible)
    chosen = next(e for e in eligible if e['cv_mae'] <= best * PI_TOLERANCE)
    model = pi_fit(train, chosen['kind'], chosen['features'])   # frozen before validation is read
    model['validation'] = score(lambda i: pi_predict(model, i['car'])[0] or ruled(i), valid)
    model['validation_baselines'] = {'value_scales_rule': score(ruled, valid),
                                     'fm2_identity': score(lambda i: i['car']['PerformanceIndex'], valid)}
    base = model['validation_baselines']['value_scales_rule']
    model['accepted'] = pi_monotone(model) and model['validation']['mae'] < base['mae'] and \
        model['validation']['class_match_rate'] >= base['class_match_rate']
    return {**model, 'candidates': candidates, 'pairs': {'training': len(train), 'validation': len(valid)}}


def part_scales(observations, conventions):
    """Median FM4/FM2 ratio for continuous aspiration part columns without a convention (e.g.
    PowerMaxScale). The `value_scales` study rejects them because FM4 splits turbos into single and
    twin tables (< 30 rows each). Accepted when training CV MAE and validation MAE beat identity."""
    out = {}
    columns = defaultdict(list)
    for r in observations:
        if r['table'] in ASPIRATION and not convention(conventions, r['drive'], r['table'], r['column']) and \
                vs.number(r['x']) and vs.number(r['y']) and r['x'] > 0 and r['column'] not in ('Level',):
            columns[r['table'], r['column']].append(r)
    for (table, column), items in sorted(columns.items()):
        train = [r for r in items if r['split'] == 'training']
        valid = [r for r in items if r['split'] == 'validation']
        if len(train) < 10 or len(valid) < 3:
            continue
        ratio = lambda part: statistics.median(r['y'] / r['x'] for r in part)
        cv = {'identity': [], 'ratio': []}
        for fit, held in engine_folds(train):
            if fit and held:
                k = ratio(fit)
                cv['identity'] += [abs(r['x'] - r['y']) for r in held]
                cv['ratio'] += [abs(k * r['x'] - r['y']) for r in held]
        k = ratio(train)
        entry = {'ratio': k, 'domain': [min(r['x'] for r in train), max(r['x'] for r in train)],
                 'cv_mae': {n: statistics.mean(v) for n, v in cv.items()},
                 'validation_mae': {'identity': statistics.mean(abs(r['x'] - r['y']) for r in valid),
                                    'ratio': statistics.mean(abs(k * r['x'] - r['y']) for r in valid)},
                 'rows': {'training': len(train), 'validation': len(valid)}}
        entry['accepted'] = entry['cv_mae']['ratio'] < entry['cv_mae']['identity'] and \
            entry['validation_mae']['ratio'] < entry['validation_mae']['identity']
        out[f'{table}:{column}'] = entry
    return out


def decide(observations, curves, rules, conventions, cm=None, scales=None, pi=None):
    """Per group: FM2 values (identity or an accepted rule) against the donor. Chosen on training
    and confirmed on validation; FM2 is used only when it is no worse on both."""
    accepted = {(r['table'], r['column']): r for r in rules}

    def fm2_value(r):
        fixed = convention(conventions, r['drive'], r['table'], r['column'])
        if fixed:
            return fixed['value']
        if 'cm' in r and cm and cm['accepted']:
            return cm_predict(cm, r['cm'])[0]
        if 'pi' in r and pi and pi['accepted'] and pi_predict(pi, r['pi'])[0] is not None:
            return pi_predict(pi, r['pi'])[0]
        scale = (scales or {}).get(f"{r['table']}:{r['column']}")
        if scale and scale['accepted']:
            return scale['ratio'] * r['x']
        rule = accepted.get((r['table'], r['column']))
        return vs.predict(rule, r['x']) if rule and vs.in_domain(rule, r['x']) else r['x']

    columns = defaultdict(list)
    for r in observations:
        if r['d'] is not None:
            columns[group(r['role'], r['column']), r['role'], r['column']].append(r)
    groups = defaultdict(dict)
    for (name, role, column), items in sorted(columns.items()):
        # As value_scales: integers with <= 50 values are categories.
        continuous = all(vs.number(r['x']) and vs.number(r['y']) and vs.number(r['d']) for r in items) and not \
            (all(isinstance(r[k], int) for r in items for k in 'xyd') and len({r['y'] for r in items}) <= 50)
        entry = {'continuous': continuous, 'category': c.category(items[0]['table'], column),
                 'rule': accepted.get((items[0]['table'], column), {}).get('kind', 'identity')}
        for split in ('training', 'validation'):
            part = [r for r in items if r['split'] == split]
            if part:
                entry[split] = {'n': len(part), 'fm2': errors(part, fm2_value, continuous),
                                'donor': errors(part, lambda r: r['d'], continuous)}
        groups[name][f'{role}.{column}'] = entry
    curve = {'continuous': True, 'category': 'physics', 'rule': 'identity'}
    for split in ('training', 'validation'):
        part = [e for e in curves if e['split'] == split]
        curve[split] = {'n': len(part), 'fm2': statistics.mean(e['fm2'] for e in part),
                        'donor': statistics.mean(e['donor'] for e in part)}
    groups['torque']['torque.full.curve'] = curve
    # Group score: mean FM2 error share, fm2 / (fm2 + donor), over columns where not both errors
    # are zero. Scale-free, so near-zero columns do not dominate; 0.5 = tie.
    decisions = {}
    for name, members in sorted(groups.items()):
        out = {'columns': members}
        for split in ('training', 'validation'):
            scored = [e[split] for e in members.values() if split in e and e[split]['fm2'] + e[split]['donor'] > 0]
            out[split] = {'fm2_share': statistics.mean(s['fm2'] / (s['fm2'] + s['donor']) for s in scored),
                          'columns': len(scored)} if scored else None
        train, valid = out['training'], out['validation']
        out['source'] = 'donor' if train and valid and (train['fm2_share'] > 0.5 or valid['fm2_share'] > 0.5) \
            else 'fm2'
        out['physics'] = any(e['category'] == 'physics' for e in members.values())
        decisions[name] = out
    return decisions


def study(fm2, fm4):
    data = observations(fm2, fm4)
    result = vs.study(None, fm4, rows=data['observations'], salt=SALT)
    for entry in result['columns']:
        if entry['status'] == 'not_systematic' and entry['training_difference_rate'] >= \
                vs.POLICY['min_training_difference']:
            entry['status'] = 'too_few_rows'
    rule = next((r for r in result['rules'] if (r['table'], r['column']) == (WEIGHT, 'CMHeight')), None)
    cm = cm_study(data['cm'], rule)
    from ..fm3 import performance_index as pim
    pi_rule = next((r for r in result['rules'] if (r['table'], r['column']) == ('Data_Car', 'PerformanceIndex')), None)
    pi = pi_study(data['pi'], pi_rule, pim.classes(fm4))
    scales = part_scales(data['observations'], data['conventions'])
    decisions = decide(data['observations'], data['curves'], result['rules'], data['conventions'], cm, scales, pi)
    summary = {'pairs': Counter(p['split'] for p in data['pairs']), 'excluded': data['excluded'],
               'donors': {p['media']: p['donor'] for p in data['pairs']},
               'roles_missing_in_fm4': data['roles_missing_in_fm4'], 'curves': data['curves']}
    return {**result, 'conventions': data['conventions'], 'cm_height': cm, 'performance_index': pi,
            'part_scales': scales,
            'decisions': decisions, 'summary': summary}


# Data_Car columns owned by the package or donor: identity, family, the donor's caliper model and
# colour, livery mask, price. ClassID is rewritten from PerformanceIndex.
PACKAGE_OWNED = {'Year', 'MakeID', 'IsPurchased', 'IsUnicorn', 'AIPlayerID', 'FamilyModelID', 'FamilyBodyID',
                 'CaliperAngleFront', 'CaliperAngleRear', 'CaliperRGBFront', 'CaliperRGBRear', 'HasLivery',
                 'WingMask', 'MaterialTypeID', 'BaseRarity', 'BaseCost', 'ClassID'}
TURBO = ('List_UpgradeEngineTurboSingle', 'List_UpgradeEngineTurboTwin')
ASPIRATION = TURBO + ('List_UpgradeEngineCSC', 'List_UpgradeEngineDSC', 'List_UpgradeEngineIntercooler')
# Stock aspiration part tables per AspirationTypeId on the 503 FM4 cars (no exception): single
# turbo 81, twin 56, DSC 26, CSC 3, each with a stock intercooler. FM4 has no stock quad turbo (4)
# or turbo + SC (7) car.
ASPIRATION_PARTS = {1: (), 2: (TURBO[0], 'List_UpgradeEngineIntercooler'),
                    3: (TURBO[1], 'List_UpgradeEngineIntercooler'),
                    5: ('List_UpgradeEngineDSC', 'List_UpgradeEngineIntercooler'),
                    6: ('List_UpgradeEngineCSC', 'List_UpgradeEngineIntercooler')}
# FM2 AspirationTypeId without an FM4 stock layout -> the FM4 one. FM4 stores the real quad-turbo
# Bugatti Veyron and EB110 SS as twin turbo (3); FM2's only quad turbo is CHR_ME412_05.
STOCK_ASPIRATION = {4: 3}
TRIPLETS = {'List_SpringDamperPhysics': ('SpringRate', 'DampenBumpRate', 'DampenReboundRate', 'RideHeight'),
            'List_AntiSwayPhysics': ('SwaybarStiffness',)}


def fm2_part_value(table, column, value, study, drive):
    """An FM2 part column value in FM4: table convention, part scale, accepted rule or identity."""
    fixed = convention(study['conventions'], drive, table, column)
    if fixed:
        return fixed['value'], 'convention'
    scale = study.get('part_scales', {}).get(f'{table}:{column}')
    if scale and scale['accepted']:
        return scale['ratio'] * value, 'part_scale'
    rule = next((r for r in study['rules'] if (r['table'], r['column']) == (table, column)), None)
    if rule is not None and vs.in_domain(rule, value):
        return vs.predict(rule, value), rule['kind']
    return value, 'identity'


def new_part(table, fm2_row, engine_id, study, drive, fm4):
    """A new stock row for an FM2 aspiration part the donor lacks. The package fills in the key."""
    schema = c.schema(fm4)[table]
    row, origin = {}, {}
    by_name = {k.casefold(): k for k in fm2_row}   # FM2 writes `Massdiff` in the intercooler table
    for column in (x['name'] for x in schema['columns']):
        if column == c.pk(schema):
            row[column] = None
        elif column == 'EngineID':
            row[column] = engine_id
        elif column == 'IsStock':
            row[column] = 1
        elif convention(study['conventions'], drive, table, column):
            row[column] = convention(study['conventions'], drive, table, column)['value']
            origin[column] = 'convention'
        elif column.casefold() in by_name:
            row[column], origin[column] = fm2_part_value(table, column, fm2_row[by_name[column.casefold()]], study, drive)
        else:
            raise c.MappingError(f'{table}.{column}: no FM2 value and no FM4 convention')
    return {'table': table, 'pk': c.pk(schema), 'row': row}, origin


def apply(nodes, source, study, fm4):
    """Write FM2 physics into a cloned donor stock graph (`package.clone_stock`).

    Groups that the study found closer to real FM4 through FM2 take FM2 values (through an accepted
    rule if any); other groups keep the donor's. Aspiration parts follow the FM2 car's
    AspirationTypeId: donor parts the FM2 car lacks (or a turbo in the other single/twin table) are
    removed, FM2 parts the donor lacks are installed as new stock rows with key None
    (`added_roles`). `nodes` is changed in place; returns the change log and the removed/added roles."""
    from ..fm3 import performance_index
    rules = {(r['table'], r['column']): r for r in study['rules']}
    decisions = {name: d['source'] for name, d in study['decisions'].items()}
    cm = study.get('cm_height')
    pi = study.get('performance_index')
    drive = source['nodes']['drivetrain']['DrivetypeID']
    log = {'changed': [], 'kept_donor': [], 'abstained': [], 'unknown_enum': [], 'removed_roles': [],
           'added_roles': [], 'installed': []}
    aspiration = source['nodes']['car']['AspirationTypeId']
    if aspiration in STOCK_ASPIRATION:
        mapped = STOCK_ASPIRATION[aspiration]
        log['aspiration_mapped'] = {'fm2': aspiration, 'fm4': mapped}
        nodes_in = source['nodes']
        source = {**source, 'nodes': {**nodes_in, 'car': {**nodes_in['car'], 'AspirationTypeId': mapped},
                                      'engine': {**nodes_in['engine'], 'AspirationID_Stock': mapped}}}
        aspiration = mapped
    if aspiration not in ASPIRATION_PARTS:
        raise c.MappingError(f'FM4 has no stock part layout for AspirationTypeId {aspiration}')
    wanted = ASPIRATION_PARTS[aspiration]
    fm2_roles = {r for r in ('turbo', 'List_UpgradeEngineCSC', 'List_UpgradeEngineDSC',
                             'List_UpgradeEngineIntercooler') if r in source['nodes']}
    if {'turbo' if t in TURBO else t for t in wanted} != fm2_roles:
        raise c.MappingError(f'FM2 aspiration parts {sorted(fm2_roles)} do not match AspirationTypeId {aspiration}')
    # Donor parts outside the FM2 aspiration layout are left alone; a donor turbo in the other table is replaced.
    roles = {('turbo' if r in TURBO else r): r for r in nodes if r not in ASPIRATION or r in wanted}
    for role, row in source['nodes'].items():
        if role not in roles:
            continue
        table, out = nodes[roles[role]]['table'], nodes[roles[role]]['row']
        for column, value in row.items():
            if column in KEYS or column not in out or role == 'car' and column in PACKAGE_OWNED or \
                    role == 'torque.full' and column[:1] == 'v' and column[1:].isdigit():
                continue
            entry = {'role': role, 'column': column, 'group': group(role, column), 'donor': out[column], 'fm2': value}
            if decisions.get(entry['group']) != 'fm2':
                log['kept_donor'].append(entry)
                continue
            new, rule = value, rules.get((table, column))
            fixed = convention(study['conventions'], drive, table, column)
            scale = study.get('part_scales', {}).get(f'{table}:{column}')
            if fixed:
                new, entry['rule'] = fixed['value'], 'convention'
            elif role == WEIGHT and column == 'CMHeight' and cm and cm['accepted']:
                new, outside = cm_predict(cm, cm_features(source['nodes'], source['bounds']))
                entry['rule'] = 'cm_height_' + (cm['kind'] if outside is None else 'coordinate')
                if outside is not None:
                    entry['outside_domain'] = outside
            elif role == 'car' and column == 'PerformanceIndex' and pi and pi['accepted'] and                     pi_predict(pi, pi_car(row))[0] is not None:
                new, entry['rule'] = pi_predict(pi, pi_car(row))[0], 'pi_' + pi['kind']
            elif scale and scale['accepted']:
                new, entry['rule'] = scale['ratio'] * value, 'part_scale'
            elif rule is not None:
                if vs.in_domain(rule, value):
                    new, entry['rule'] = vs.predict(rule, value), rule['kind']
                else:
                    log['abstained'].append(entry)
            if column.endswith(('ID', 'Id')) and fm4.execute(
                    f'SELECT 1 FROM {c.qi(table)} WHERE {c.qi(column)}=? LIMIT 1', (new,)).fetchone() is None:
                log['unknown_enum'].append(entry)
                continue
            if new != out[column]:
                out[column] = entry['after'] = new
                log['changed'].append(entry)
    # Stock triplets that FM2 does not let you tune (Min = Def = Max) stay so, as 384/503 FM4 stock
    # suspensions; a separate rule for Max must not open a tuning range.
    for role in ('spring.front', 'spring.rear', 'antiroll.front', 'antiroll.rear'):
        if decisions.get(group(role, 'DefSpringRate')) != 'fm2':
            continue
        fm2, out = source['nodes'][role], nodes[role]['row']
        for stem in TRIPLETS[nodes[role]['table']]:
            if fm2['Min' + stem] == fm2['Def' + stem] == fm2['Max' + stem]:
                for prefix in ('Min', 'Max'):
                    if out[prefix + stem] != out['Def' + stem]:
                        log['changed'].append({'role': role, 'column': prefix + stem, 'group': group(role, stem),
                                               'donor': out[prefix + stem], 'fm2': fm2[prefix + stem],
                                               'after': out['Def' + stem], 'rule': 'fixed_stock_triplet'})
                        out[prefix + stem] = out['Def' + stem]
    # A Max rule (e.g. rebound 20 -> 11.96) can fall below the identity-copied FM2 Def. FM4 has no
    # Def > Max (2/2686 rows); Def is mapped to the same relative position in the new range. On the
    # 6 training axles with this conflict: MAE 1.61 against 3.93 for clamping to Max, 5.54 identity.
    for role in ('spring.front', 'spring.rear', 'antiroll.front', 'antiroll.rear'):
        if decisions.get(group(role, 'DefSpringRate')) != 'fm2':
            continue
        fm2, out = source['nodes'][role], nodes[role]['row']
        for stem in TRIPLETS[nodes[role]['table']]:
            low, mid, high = (out[p + stem] for p in ('Min', 'Def', 'Max'))
            src_low, src_high = fm2['Min' + stem], fm2['Max' + stem]
            if low <= mid <= high or src_high <= src_low:
                continue
            new = round(low + (fm2['Def' + stem] - src_low) * (high - low) / (src_high - src_low), 6)
            log['changed'].append({'role': role, 'column': 'Def' + stem, 'group': group(role, stem), 'before': mid,
                                   'fm2': fm2['Def' + stem], 'after': new, 'rule': 'range_position'})
            out['Def' + stem] = new
    if decisions.get('torque') == 'fm2':
        curve, out = source['nodes']['torque.full'], nodes['torque.full']['row']
        count = curve['NumTorqueValues']
        samples = [k for k in out if k[:1] == 'v' and k[1:].isdigit()]
        if count > len(samples):
            raise c.MappingError('FM2 torque curve has more samples than FM4 stores')
        for k in samples:  # inactive samples = 0, as native FM4 curves
            out[k] = curve[k] if int(k[1:]) < count else 0.0
        log['torque_samples'] = count
    if decisions.get('transmission') == 'fm2':
        gears = nodes['List_UpgradeDrivetrainTransmission']['row']
        for i in range(gears['NumGears'], 9):  # unused gear slots = -1 in FM4
            gears[f'GearRatio{i}'] = -1.0
    log['removed_roles'] = [r for r in ASPIRATION if r in nodes and r not in wanted]
    engine_id = nodes['engine']['row']['EngineID']
    for table in wanted:
        if table in nodes:
            continue
        fm2_row = source['nodes']['turbo' if table in TURBO else table]
        nodes[table], origin = new_part(table, fm2_row, engine_id, study, drive, fm4)
        log['added_roles'].append(table)
        log['installed'].append({'table': table, 'row': nodes[table]['row'], 'origin': origin,
                                 'fm2': {k: v for k, v in fm2_row.items() if k not in KEYS}})
    # The final graph must follow FM4's conventions: Data_Car and Data_Engine name the same
    # aspiration, and exactly that aspiration's stock parts remain.
    car, engine = nodes['car']['row'], nodes['engine']['row']
    left = {r for r in ASPIRATION if r in nodes and r not in log['removed_roles']}
    if car['AspirationTypeId'] != aspiration or engine['AspirationID_Stock'] != aspiration or left != set(wanted):
        raise c.MappingError(f'Aspiration graph not consistent: car {car["AspirationTypeId"]}, engine '
                             f'{engine["AspirationID_Stock"]}, parts {sorted(left)}, FM2 {aspiration}')
    if (engine['StockBoost-bar'] > 0) != (aspiration != 1):
        raise c.MappingError(f'StockBoost-bar {engine["StockBoost-bar"]} does not match AspirationTypeId {aspiration}')
    log['class'] = performance_index.apply(car, fm4, None)
    # As the FM3 validator (docs/fm3.md, Audi R10): unordered triplets inherited exactly from FM2
    # are kept with a warning, because the runtime normalises defaults to their limits; native FM4
    # also has 4 spring rows with Def > Max. New violations are still rejected.
    log['inherited_unordered'] = []
    for role, node in nodes.items():
        for stem in TRIPLETS.get(node['table'], ()):
            triplet = tuple(node['row'][p + stem] for p in ('Min', 'Def', 'Max'))
            if triplet[0] <= triplet[1] <= triplet[2]:
                continue
            if triplet == tuple(source['nodes'].get(role, {}).get(p + stem) for p in ('Min', 'Def', 'Max')):
                log['inherited_unordered'].append({'role': role, 'stem': stem, 'triplet': triplet})
                continue
            raise c.MappingError(f'{node["table"]} {stem}: Min/Def/Max not ordered {triplet}')
    return log


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--fm4', type=Path, default=c.FM4_DEFAULT)
    p.add_argument('--out', type=Path, default=OUT / 'study.json')
    a = p.parse_args()
    with closing(c.connect(FM2_DB)) as fm2, closing(c.connect(a.fm4)) as fm4:
        result = study(fm2, fm4)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(result, indent=1, default=list), encoding='utf-8')
    s = result['summary']
    print('pairs', dict(s['pairs']), 'excluded', len(s['excluded']), 'missing roles', s['roles_missing_in_fm4'])
    print('rules', Counter(e['status'] for e in result['columns']))
    for name, d in result['decisions'].items():
        t, v = d['training'] or {}, d['validation'] or {}
        print(f"{d['source']:5s} {'P' if d['physics'] else ' '} {name:42s} FM2 share train "
              f"{t.get('fm2_share', 0):.3f} ({t.get('columns', 0)}) val {v.get('fm2_share', 0):.3f}")


if __name__ == '__main__':
    main()
