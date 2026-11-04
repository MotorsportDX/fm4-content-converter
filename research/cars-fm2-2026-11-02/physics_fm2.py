"""Fisika stock FM2 -> FM4: extractor, studi pasangan mobil yang sama, dan aturan (REPORT bagian 10).

`extract(db, car_id)` membaca konfigurasi stock FM2 (IsStock=1, relasi Ordinal/EngineID) dan
menyusunnya dalam role, tabel, dan nama kolom FM4 seperti `converter.extract_stock`. Kolom FM4
yang tidak punya sumber FM2 tidak diisi; di paket uji kolom itu tetap milik donor.

`study` mengikuti metode `value_scales` jalur FM3: pasangan FM2∩FM4 dengan Id, MediaName, tahun,
dan merek sama; split training/validation dikelompokkan per mesin FM2 (1/5 validation);
kandidat dipilih dengan CV 5 fold per mesin pada training lalu dibekukan sebelum validation.
"""
from collections import Counter, defaultdict
from contextlib import closing
import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fm4_converter.fm3 import converter as c, value_scales as vs
from fm4_converter.paths import PROJECT_ROOT

FM2_DB = Path(r'D:\Data\FM2\USA\Forza Motorsport 2 (USA)\Media\DB\gamedb.slt')
OUT = PROJECT_ROOT / 'outputs/car-fm2-research-2026-11-02/physics'
SALT = 'fm2-fm4-calibration-v1'

# Tabel part FM2 -> role FM4 (= nama tabel FM4 di converter.extract_stock), kolom bernama sama.
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
# Satu baris FM2 dipecah menjadi dua role FM4 per gandar: {role: {kolom FM4: kolom FM2}}.
SPLIT = [
    ('List_UpgradeTireWidth', {'List_UpgradeCarBodyTireWidthFront': {'FrontTireWidth': 'FrontTireWidth'},
                               'List_UpgradeCarBodyTireWidthRear': {'RearTireWidth': 'RearTireWidth'}}),
    ('List_UpgradeRimSize', {'List_UpgradeRimSizeFront': {'FrontWheelDiameter': 'FrontWheelDiameter'},
                             'List_UpgradeRimSizeRear': {'RearWheelDiameter': 'RearWheelDiameter'}}),
]
COMMON_PART = ('MassDiff', 'DragScale', 'WindInstabilityScale', 'Price', 'ManufacturerID', 'Level')
# Kolom FM4 yang di FM2 berada di tabel atau nama lain: role -> {kolom FM4: (role FM2, kolom FM2)}.
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
# Kunci baris dan referensi ke baris lain: tidak dibandingkan (nilainya nomor baris, bukan fisika).
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
    """AutoSteerOverrides FM4 dengan ambang STM FM2 yang sama (seperti converter FM3)."""
    found = rows(fm4, 'AutoSteerOverrides', 'STMSlipMin=? AND STMSlipMax=?',
                 (car['AssistsSTMSlipDefMin'], car['AssistsSTMSlipDefMax']))
    payloads = {json.dumps({k: v for k, v in r.items() if k != 'Id'}, sort_keys=True) for r in found}
    return min(r['Id'] for r in found) if len(payloads) == 1 else None


def extract(db, car_id, fm4=None):
    """Konfigurasi stock FM2 dalam role/tabel/kolom FM4. Nilai mentah FM2, tanpa aturan.
    Dengan `fm4`, `AutoSteerOverrideID` dicari dari ambang STM FM2."""
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
    # FM4 menyimpan skala kurva zero-throttle di kurva full-throttle (seperti jalur FM3).
    nodes['torque.full']['ZeroThrottleTorqueScale'] = source['torque.zero']['TorqueScale']
    if fm4 is not None:
        steer = auto_steer(fm4, car)
        if steer is not None:
            nodes['car']['AutoSteerOverrideID'] = steer
    return {'car_id': car_id, 'media_name': car['MediaName'], 'engine_id': engine['EngineID'],
            'nodes': nodes, 'torque_zero': source['torque.zero']}


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
    """Kurva full-throttle efektif (rpm, Nm x GameTorqueScale); sampel i pada i * MaxRPM / (N - 1)."""
    curve, cam = nodes['torque.full'], nodes['List_UpgradeEngineCamshaft']
    n, top = curve['NumTorqueValues'], cam['TorqueCurveMaxRPM']
    scale = curve['TorqueScale'] * nodes['car']['GameTorqueScale']
    return [(i * top / (n - 1), scale * curve[f'v{i}']) for i in range(n)]


def curve_error(candidate, reference):
    """Rata-rata |selisih torsi| pada grid rpm referensi, dibagi torsi puncak referensi."""
    def at(curve, rpm):
        if rpm >= curve[-1][0]:
            return curve[-1][1]
        for (r0, t0), (r1, t1) in zip(curve, curve[1:]):
            if r0 <= rpm <= r1:
                return t0 + (t1 - t0) * (rpm - r0) / (r1 - r0)
    peak = max(t for _, t in reference)
    return sum(abs(at(candidate, r) - t) for r, t in reference) / len(reference) / peak


def flat(nodes):
    """fm4_nodes -> {role: row}, bentuk yang sama dengan extract()['nodes']."""
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
    """Donor seperti di paket uji: mobil FM4 semerek dan berpenggerak sama, massa dan tenaga terdekat."""
    nodes = source['nodes']
    mass, power = nodes['List_UpgradeCarBodyWeight']['Mass'], nodes['engine']['EngineGraphingMaxPower']
    pool = [d for d in index if d['id'] != exclude_id and d['drive'] == nodes['drivetrain']['DrivetypeID']]
    pool = [d for d in pool if d['make'] == nodes['car']['MakeID']] or pool
    return min(pool, key=lambda d: (abs(math.log(d['mass'] / mass)) + abs(math.log(d['power'] / power)), d['id']))


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
    obs, curves, missing = [], [], Counter()
    for pair in found:
        source = extract(fm2, pair['id'], fm4)
        native = fm4_nodes(fm4, pair['media'])
        target = flat(native)
        chosen = donor(index, source, pair['id'])
        pair['donor'] = chosen['media']
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
        reference = torque_curve(target)
        curves.append({'media': pair['media'], 'split': pair['split'], 'engine': pair['engine'],
                       'fm2': curve_error(torque_curve(source['nodes']), reference),
                       'donor': curve_error(torque_curve(chosen['nodes']), reference),
                       'samples': (source['nodes']['torque.full']['NumTorqueValues'],
                                   target['torque.full']['NumTorqueValues'])})
    return {'pairs': found, 'excluded': excluded, 'observations': obs, 'curves': curves,
            'roles_missing_in_fm4': dict(missing), 'conventions': drive_conventions(index)}


TIRES = {'FrontTireWidthMM', 'FrontTireAspect', 'FrontWheelDiameterIN', 'RearTireWidthMM', 'RearTireAspect',
         'RearWheelDiameterIN'}


def group(role, column):
    """Kolom yang harus berasal dari sumber yang sama: triplet tuning, kedua gandar, gigi, kurva
    torsi beserta GameTorqueScale, aero bodi beserta GameDragScale, massa. Metadata performa
    tersimpan (rating, Sim*, grafik mesin) tidak mengubah fisika dan diputuskan per kolom."""
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


# Part yang kolomnya bekerja bersama (skala boost, LSD tiap gandar); kolom part lain diputuskan sendiri.
COUPLED = {'turbo', 'List_UpgradeEngineCSC', 'List_UpgradeEngineDSC', 'List_UpgradeDrivetrainDifferential'}


def drive_conventions(index):
    """Kolom diferensial yang di FM4 bernilai tunggal pada ≥ 99% mobil sejenis penggerak
    (mis. LSD tengah 0 pada semua mobil RWD)."""
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


def errors(items, predict, continuous):
    """Galat ternormalisasi: MAE / rata-rata |FM4| (kontinu) atau 1 - kecocokan (kategori)."""
    if continuous:
        scale = sum(abs(r['y']) for r in items) / len(items) or 1.0
        return sum(abs(predict(r) - r['y']) for r in items) / len(items) / scale
    return sum(not vs.same(predict(r), r['y']) for r in items) / len(items)


def convention(conventions, drive, table, column):
    if table == 'List_UpgradeDrivetrainDifferential':
        return conventions.get(f'{drive}:{column}')


def decide(observations, curves, rules, conventions):
    """Per grup: nilai FM2 (identity atau aturan yang diterima) melawan donor. Dipilih pada training
    dan dikonfirmasi pada validation; FM2 dipakai hanya bila tidak lebih buruk di keduanya."""
    accepted = {(r['table'], r['column']): r for r in rules}

    def fm2_value(r):
        fixed = convention(conventions, r['drive'], r['table'], r['column'])
        if fixed:
            return fixed['value']
        rule = accepted.get((r['table'], r['column']))
        return vs.predict(rule, r['x']) if rule and vs.in_domain(rule, r['x']) else r['x']

    columns = defaultdict(list)
    for r in observations:
        if r['d'] is not None:
            columns[group(r['role'], r['column']), r['role'], r['column']].append(r)
    groups = defaultdict(dict)
    for (name, role, column), items in sorted(columns.items()):
        # Seperti value_scales: integer dengan ≤ 50 nilai adalah kategori.
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
    # Skor grup: rata-rata bagian galat FM2, fm2 / (fm2 + donor), atas kolom yang galatnya tidak
    # keduanya nol. Bebas skala, sehingga kolom bernilai hampir nol tidak mendominasi; 0,5 = seri.
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
    decisions = decide(data['observations'], data['curves'], result['rules'], data['conventions'])
    summary = {'pairs': Counter(p['split'] for p in data['pairs']), 'excluded': data['excluded'],
               'donors': {p['media']: p['donor'] for p in data['pairs']},
               'roles_missing_in_fm4': data['roles_missing_in_fm4'], 'curves': data['curves']}
    return {**result, 'conventions': data['conventions'], 'decisions': decisions, 'summary': summary}


# Kolom Data_Car yang tetap milik paket atau donor: identitas, keluarga, model dan warna kaliper
# donor, mask livery, harga. ClassID ditulis ulang dari PerformanceIndex.
PACKAGE_OWNED = {'Year', 'MakeID', 'IsPurchased', 'IsUnicorn', 'AIPlayerID', 'FamilyModelID', 'FamilyBodyID',
                 'CaliperAngleFront', 'CaliperAngleRear', 'CaliperRGBFront', 'CaliperRGBRear', 'HasLivery',
                 'WingMask', 'MaterialTypeID', 'BaseRarity', 'BaseCost', 'ClassID'}
TURBO = ('List_UpgradeEngineTurboSingle', 'List_UpgradeEngineTurboTwin')
ASPIRATION = TURBO + ('List_UpgradeEngineCSC', 'List_UpgradeEngineDSC', 'List_UpgradeEngineIntercooler')
TRIPLETS = {'List_SpringDamperPhysics': ('SpringRate', 'DampenBumpRate', 'DampenReboundRate', 'RideHeight'),
            'List_AntiSwayPhysics': ('SwaybarStiffness',)}


def apply(nodes, source, study, fm4):
    """Tulis fisika FM2 ke graf stock donor yang sudah dikloning (`package_fm2_test.clone_stock`).

    Grup yang di studi lebih dekat ke FM4 asli lewat FM2 memakai nilai FM2 (aturan yang diterima
    bila ada); grup lain tetap donor. Part aspirasi donor yang tidak dimiliki mobil FM2 dibuang.
    `nodes` diubah di tempat; hasilnya log perubahan dan daftar role yang dibuang."""
    from fm4_converter.fm3 import performance_index
    rules = {(r['table'], r['column']): r for r in study['rules']}
    decisions = {name: d['source'] for name, d in study['decisions'].items()}
    log = {'changed': [], 'kept_donor': [], 'abstained': [], 'unknown_enum': [], 'removed_roles': []}
    roles = {('turbo' if r in TURBO else r): r for r in nodes}
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
            fixed = convention(study['conventions'], source['nodes']['drivetrain']['DrivetypeID'], table, column)
            if fixed:
                new, entry['rule'] = fixed['value'], 'drive_convention'
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
    # Triplet stock yang tidak bisa disetel di FM2 (Min = Def = Max) tetap begitu, seperti 384/503
    # suspensi stock FM4; aturan terpisah untuk Max tidak boleh membuka rentang setelan.
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
    if decisions.get('torque') == 'fm2':
        curve, out = source['nodes']['torque.full'], nodes['torque.full']['row']
        count = curve['NumTorqueValues']
        samples = [k for k in out if k[:1] == 'v' and k[1:].isdigit()]
        if count > len(samples):
            raise c.MappingError('FM2 torque curve has more samples than FM4 stores')
        for k in samples:  # sampel tak aktif = 0, seperti kurva FM4 asli
            out[k] = curve[k] if int(k[1:]) < count else 0.0
        log['torque_samples'] = count
    if decisions.get('transmission') == 'fm2':
        gears = nodes['List_UpgradeDrivetrainTransmission']['row']
        for i in range(gears['NumGears'], 9):  # slot gigi tak terpakai = -1 di FM4
            gears[f'GearRatio{i}'] = -1.0
    for role in ASPIRATION:
        if role in nodes and ('turbo' if role in TURBO else role) not in source['nodes']:
            log['removed_roles'].append(role)
    for role in ('turbo', 'List_UpgradeEngineCSC', 'List_UpgradeEngineDSC', 'List_UpgradeEngineIntercooler'):
        if role in source['nodes'] and role not in roles:
            raise c.MappingError(f'FM2 car has {role} but the donor does not')
    car = nodes['car']['row']
    log['class'] = performance_index.apply(car, fm4, None)
    for node in nodes.values():
        for stem in TRIPLETS.get(node['table'], ()):
            low, mid, high = (node['row'][p + stem] for p in ('Min', 'Def', 'Max'))
            if not low <= mid <= high:
                raise c.MappingError(f'{node["table"]} {stem}: Min/Def/Max not ordered ({low}, {mid}, {high})')
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
