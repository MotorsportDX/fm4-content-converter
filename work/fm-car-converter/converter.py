"""Offline stock-car FM3 -> FM4 database experiment. Never installs content.

The converter preserves source calibration. FM4's matching car is read only by
the comparator, after conversion. FM4 schema, registries, and explicitly scoped
default cohorts are allowed target inputs. Python standard library only.
"""
from __future__ import annotations

import argparse
import copy
from collections import Counter, defaultdict
from contextlib import closing
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3


FM3_DEFAULT = Path(r"D:\Data\FM3\USA\Forza Motorsport 3 (USA) (Disc 1) (Play Disc)\Media\DB\gamedb.slt")
FM4_DEFAULT = Path(r"D:\Data\forza-motorsport-4\Forza Motorsport 4 (Japan, Asia) (Disc 1) (Play Disc)\Media\DB\gamedb.slt")
MEDIA = "TOY_2000GT_69"
ID_BASE = 1_500_000_000  # Offline namespace, NOT a verified engine-safe ordinal.


class MappingError(ValueError):
    pass


def qi(name):
    return '"' + name.replace('"', '""') + '"'


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def dump(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def connect(path):
    db = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro&immutable=1", uri=True)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA query_only=ON")
    return db


def rows(db, table, where="", args=()):
    return [dict(r) for r in db.execute("SELECT * FROM " + qi(table) + (" WHERE " + where if where else ""), args)]


def schema(db):
    return {r["name"]: {"sql": r["sql"], "columns": [dict(c) for c in db.execute("PRAGMA table_info(" + qi(r["name"]) + ")")]}
            for r in db.execute("SELECT name,sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")}


def pk(info):
    keys = [c["name"] for c in info["columns"] if c["pk"]]
    if len(keys) != 1:
        raise MappingError(f"Expected one declared primary key, got {keys}")
    return keys[0]


def one(values, label):
    if len(values) != 1:
        raise MappingError(f"{label}: expected exactly one row, got {len(values)}")
    return values[0]


def extract_stock(db, media):
    """Follow actual columns and IsStock, never derive a key by multiplication."""
    sc = schema(db)
    graph = {"media_name": media, "nodes": {}, "edges": [], "empty_stock_tables": [], "scope": "stock physics + stock wheel; no purchasable upgrades or assets"}

    def add(role, table, row):
        graph["nodes"][role] = {"table": table, "pk": pk(sc[table]), "row": row}

    def link(origin, column, target):
        graph["edges"].append({"from": origin, "column": column, "to": target})

    car = one(rows(db, "Data_Car", "MediaName=?", (media,)), media)
    add("car", "Data_Car", car)
    for table, column, role, base in [
        ("List_UpgradeCarBody", "CarBodyID", "body", "Data_CarBody"),
        ("List_UpgradeEngine", "EngineID", "engine", "Data_Engine"),
        ("List_UpgradeDrivetrain", "DrivetrainID", "drivetrain", "Data_Drivetrain"),
    ]:
        choice = one(rows(db, table, "Ordinal=? AND IsStock=1", (car["Id"],)), table)
        add(table, table, choice)
        add(role, base, one(rows(db, base, qi(pk(sc[base])) + "=?", (choice[column],)), base))
        link(table, "Ordinal", "car")
        link(table, column, role)

    scopes = {"ordinal": ("car", car["Id"]), "carbodyid": ("body", graph["nodes"]["body"]["row"]["Id"]),
              "engineid": ("engine", graph["nodes"]["engine"]["row"]["EngineID"]),
              "drivetrainid": ("drivetrain", graph["nodes"]["drivetrain"]["row"]["DrivetrainID"])}
    for table, info in sc.items():
        if not table.startswith("List_Upgrade") or table in graph["nodes"]:
            continue
        columns = [c["name"] for c in info["columns"]]
        scope = next((n for n in columns if n.lower() in scopes), None)
        if not scope or "IsStock" not in columns:
            continue
        parent, value = scopes[scope.lower()]
        selected = rows(db, table, qi(scope) + "=? AND IsStock=1", (value,))
        if not selected:
            graph["empty_stock_tables"].append(table)
            continue
        if table == "List_UpgradeMotor":
            raise MappingError("Electric motors are outside this combustion-engine prototype")
        add(table, table, one(selected, table))
        link(table, scope, parent)

    for origin, column, role, table in [
        ("List_UpgradeSpringDamper", "FrontSpringDamperPhysicsID", "spring.front", "List_SpringDamperPhysics"),
        ("List_UpgradeSpringDamper", "RearSpringDamperPhysicsID", "spring.rear", "List_SpringDamperPhysics"),
        ("List_UpgradeAntiSwayFront", "AntiSwayPhysicsID", "antiroll.front", "List_AntiSwayPhysics"),
        ("List_UpgradeAntiSwayRear", "AntiSwayPhysicsID", "antiroll.rear", "List_AntiSwayPhysics"),
        ("List_UpgradeCarBodyFrontBumper", "AeroPhysicsID", "aero.front", "List_AeroPhysics"),
        ("List_UpgradeRearWing", "AeroPhysicsID", "aero.rear", "List_AeroPhysics"),
        ("List_UpgradeEngineCamshaft", "TorqueCurveFullThrottleID", "torque.full", "List_TorqueCurve"),
        ("List_UpgradeEngineCamshaft", "TorqueCurveZeroThrottleID", "torque.zero", "List_TorqueCurve"),
        ("car", "StockWheelID", "wheel", "List_Wheels"),
    ]:
        if origin not in graph["nodes"] or column not in graph["nodes"][origin]["row"]:
            continue
        value = graph["nodes"][origin]["row"][column]
        add(role, table, one(rows(db, table, qi(pk(sc[table])) + "=?", (value,)), role))
        link(origin, column, role)
        dep = graph["nodes"][role]["row"]
        for scope, (parent, expected) in scopes.items():
            for name in dep:
                if name.lower() == scope:
                    if dep[name] != expected:
                        raise MappingError(f"{role}.{name}: dependency belongs to another vehicle")
                    link(role, name, parent)
    modifiers = rows(db, "TireMod_FrictionScale", "Ordinal=?", (car["Id"],))
    if modifiers:
        add("tire.modifier", "TireMod_FrictionScale", one(modifiers, "tire modifier"))
        link("tire.modifier", "Ordinal", "car")
    return graph


# Only reviewed reference relations are interpreted. Similar names do NOT imply
# identical domains: Powertrains.DrivetrainId, for example, is a drive type enum.
REGISTRY_COLUMNS = {
    "makeid": "List_CarMake", "cartypeid": "List_CarType", "familymodelid": "List_FamilyModel",
    "familybodyid": "List_FamilyBody", "familyspecialid": "List_FamilySpecial",
    "engineplacementid": "List_EnginePlacement", "materialtypeid": "List_MaterialType",
    "powertrainid": "Powertrains", "drivetypeid": "List_DriveType", "regionid": "List_Region",
    "countryid": "List_Country", "engineconfigid": "List_EngineConfig", "configid": "List_EngineConfig",
    "cylinderid": "List_Cylinders", "aspirationtypeid": "List_Aspiration", "aspirationid_stock": "List_Aspiration",
    "variabletimingid": "List_VariableTiming", "suspensionphysicstypeid": "List_SuspensionPhysicsType",
    "frontbraketypeid": "List_BrakeType", "rearbraketypeid": "List_BrakeType",
    "damagemoddefid": "List_DamageModDef", "suspensiondamagemoddefid": "List_DamageModDef",
    "tiresdamagemoddefid": "List_DamageModDef", "tirecompoundid": "List_TireCompound",
}
LABELS = {
    "Powertrains": ("DrivetrainId", "EnginePlacementId"), "List_DamageModDef": ("DamageModName",),
    "List_SuspensionPhysicsType": ("Name",), "List_CarMake": ("ManufacturerCode",),
    "List_BrakeType": ("BrakeType",), "List_EngineConfig": ("EngineConfig",),
    "List_Aspiration": ("Aspiration",),
}


def registry_label(row, table, primary):
    columns = LABELS.get(table)
    if columns is None:
        if "DisplayName" in row:
            columns = ("DisplayName",)
        else:
            columns = tuple(k for k in row if k != primary)
    return tuple((c, row[c]) for c in columns)


def registry_pk(info, table):
    # The schema omits this PK; every lookup still enforces a unique row.
    if table == "List_SuspensionPhysicsType":
        return "SuspensionPhysicsTypeID"
    return pk(info)


def category(table, column):
    if table == "Data_Engine" and column in {"EngineGraphingMaxTorque","EngineGraphingMaxPower"}:
        return "stored_performance_metadata"
    if table == "Data_Car":
        if column.startswith("Sim") or column.endswith("Rating") or column in {"PerformanceIndex", "ClassID"}:
            return "stored_performance_metadata"
        if column.startswith(("Steer", "Assists", "FixListing", "BodyAero", "TireAero", "Game")):
            return "physics"
        if column in {"CurbWeight", "WeightDistribution", "NumGears", "Displacement", "FrontStockRideHeight", "RearStockRideHeight", "AutoSteerOverrideID"} or "Tire" in column or "WheelDiameter" in column:
            return "physics"
        return "catalog_or_integration"
    if column in {"Level", "IsStock", "ManufacturerID", "ManufacturerId", "PartManufacturerID", "Price", "PartsStringID", "PartsStringId", "Sequence", "DisplayName", "MediaName", "IconPath", "EngineName"}:
        return "part_metadata"
    return "physics"


def convert(source_db, target_db, source, id_base=ID_BASE):
    """Build candidate WITHOUT reading the native target car's calibration."""
    sc, tc = schema(source_db), schema(target_db)
    candidate = {"media_name": source["media_name"], "nodes": {}, "edges": [], "scope": source["scope"]}
    mapping, drops, assumptions, external = [], [], [], []
    allocation = {}
    next_id = defaultdict(lambda: id_base)
    occupied = {}
    for node in source["nodes"].values():
        table = node["table"]
        if table not in tc:
            raise MappingError(f"Unsupported source table {table}")
        primary = pk(tc[table])
        if table not in occupied:
            occupied[table] = {r[0] for r in target_db.execute("SELECT " + qi(primary) + " FROM " + qi(table))}
    for role, node in sorted(source["nodes"].items()):
        if role == "torque.zero":
            continue
        table = node["table"]
        identity = (table, node["row"][node["pk"]])
        if identity not in allocation:
            value = next_id[table]
            while value in occupied[table]:
                value += 1
            if value < 1 or value > 2_147_483_647:
                raise MappingError("Experimental ID namespace exceeds signed 32-bit range")
            allocation[identity] = value
            occupied[table].add(value)
            next_id[table] = value + 1

    source_edges = {(e["from"], e["column"]): e["to"] for e in source["edges"]}
    global_cache = {}

    def resolve_registry(table, value):
        key = (table, value)
        if key not in global_cache:
            sp, tp = registry_pk(sc[table],table), registry_pk(tc[table],table)
            original = one(rows(source_db, table, qi(sp) + "=?", (value,)), str(key))
            label = registry_label(original, table, sp)
            matches = [r for r in rows(target_db, table) if registry_label(r, table, tp) == label]
            exact = [r for r in matches if r[tp] == value]
            chosen = one(exact or matches, f"semantic registry match {key}")
            global_cache[key] = chosen[tp]
            external.append({"table": table, "pk": tp, "source_id": value, "target_id": chosen[tp],
                             "identity": list(label), "row": chosen, "policy": "native_fm4_registry_by_semantic_identity"})
        return global_cache[key]

    def cohort_default(table, column, owner_column, excluded):
        counts = Counter(r[0] for r in target_db.execute(
            "SELECT " + qi(column) + " FROM " + qi(table) + " WHERE " + qi(owner_column) + "<>? AND " + qi(column) + " IS NOT NULL", (excluded,)))
        if not counts:
            raise MappingError(f"No independent cohort for {table}.{column}")
        ranking = counts.most_common()
        if len(ranking) > 1 and ranking[0][1] == ranking[1][1]:
            raise MappingError(f"Ambiguous default for {table}.{column}")
        value = ranking[0][0]
        assumptions.append({"table": table, "column": column, "value": value, "rule": "mode_of_other_owners",
                            "excluded_owner": excluded, "owner_column": owner_column,
                            "distribution": [{"value": v, "count": n} for v, n in ranking], "runtime_verified": False})
        return value

    car = source["nodes"]["car"]["row"]
    full = source["nodes"]["torque.full"]["row"]
    zero = source["nodes"]["torque.zero"]["row"]
    count = full["NumTorqueValues"]
    if not isinstance(count, int) or not 1 <= count <= 151:
        raise MappingError("Unsupported FM3 torque sample count")
    if zero["NumTorqueValues"] != count:
        raise MappingError("Zero/full-throttle sample domains differ")
    if source["nodes"]["List_UpgradeEngineCamshaft"]["row"]["NumRPMEntriesArray"] != count:
        raise MappingError("Camshaft and torque sample counts differ")
    for i in range(count):
        if f"v{i}" not in full or not isinstance(full[f"v{i}"], (int, float)) or not math.isfinite(full[f"v{i}"]):
            raise MappingError(f"Invalid active torque sample v{i}")

    stretch = cohort_default("List_SpringDamperPhysics", "MaxStretchDeltaFromRideHeight", "Ordinal", car["Id"])
    cvt = cohort_default("List_UpgradeDrivetrainTransmission", "CVTShiftTime", "DrivetrainID", source["nodes"]["drivetrain"]["row"]["DrivetrainID"])
    auto_candidates = rows(target_db, "AutoSteerOverrides", "STMSlipMin=? AND STMSlipMax=?",
                           (car["AssistsSTMSlipDefMin"], car["AssistsSTMSlipDefMax"]))
    if not auto_candidates:
        raise MappingError("No AutoSteerOverrides matching the FM3 STM thresholds")
    auto_payloads = {json.dumps({k:v for k,v in r.items() if k != "Id"}, sort_keys=True) for r in auto_candidates}
    if len(auto_payloads) != 1:
        raise MappingError("Ambiguous AutoSteerOverrides semantics")
    auto = min(auto_candidates, key=lambda r:r["Id"])
    external.append({"table":"AutoSteerOverrides", "pk":"Id", "target_id":auto["Id"], "row":auto,
                     "policy":"match STM thresholds; equivalent rows choose lowest ID"})
    assumptions.extend([
        {"rule":"zero_throttle_scale_from_fm3_curve", "value":zero["TorqueScale"], "runtime_verified":False,
         "limitation":"FM3 zero-throttle sample SHAPE is retained in source IR only; FM4 reconstruction is unknown."},
        {"rule":"split_chassis_friction_to_lat_and_long", "runtime_verified":False,
         "limitation":"FM3 axle scalar copied to both FM4 directions; this is a baseline hypothesis."},
        {"rule":"same_semantic_tire_compound_uses_native_fm4_curves", "runtime_verified":False,
         "limitation":"Compound assignment remains FM3's choice; matching FM4 car can select a different compound."},
    ])

    for role, node in source["nodes"].items():
        if role == "torque.zero":
            drops.append({"role":role, "table":node["table"], "reason":"Scalar folded into full curve; original samples retained in source_ir.json, not in target schema."})
            continue
        table, old = node["table"], node["row"]
        primary = pk(tc[table])
        out = {}
        target_columns = {c["name"] for c in tc[table]["columns"]}
        for col in tc[table]["columns"]:
            name = col["name"]
            origin = name if name in old else None
            action, confidence = "copy_native_value", "structural_only"
            if (role, name) in source_edges:
                parent = source["nodes"][source_edges[(role, name)]]
                identity = (parent["table"], parent["row"][parent["pk"]])
                value = allocation[identity]
                action, confidence = "remap_reference", "verified_relation"
                candidate["edges"].append({"from":role,"column":name,"to":source_edges[(role,name)]})
            elif name == primary:
                value = allocation[(table, old[node["pk"]])]
                action, confidence = "allocate_primary_key", "offline_namespace"
            elif name.lower() in REGISTRY_COLUMNS:
                value = resolve_registry(REGISTRY_COLUMNS[name.lower()], old[name])
                action, confidence = "native_fm4_registry", "semantic_identity"
            elif table == "Data_Car" and name in {"IsCarExperienceUnlocked","HasCarExperience","HasRaceLivery","IsDrivable"}:
                value = int(name == "IsDrivable")
                action, confidence = "prototype_capability_flag", "explicit_policy"
            elif table == "Data_Car" and name == "AutoSteerOverrideID":
                value = auto["Id"]
                origin = "AssistsSTMSlipDefMin + AssistsSTMSlipDefMax"
                action, confidence = "stm_threshold_lookup", "partial_semantics"
            elif table == "Data_Car" and name in {"FrontStockRideHeight","RearStockRideHeight"}:
                axle = "front" if name.startswith("Front") else "rear"
                value = source["nodes"]["spring."+axle]["row"]["DefRideHeight"]
                origin = "spring." + axle + ".DefRideHeight"
                action, confidence = "derive_stock_ride_height", "candidate_rule"
            elif table == "List_SpringDamperPhysics" and name == "MaxStretchDeltaFromRideHeight":
                value = stretch
                action, confidence = "other_car_cohort_default", "provisional"
            elif table == "List_UpgradeDrivetrainTransmission" and name == "CVTShiftTime":
                value = cvt
                action, confidence = "other_drivetrain_cohort_default", "provisional"
            elif table == "List_UpgradeCarBodyChassisStiffness" and name in {"FrontLatFrictionScale","FrontLongFrictionScale","RearLatFrictionScale","RearLongFrictionScale"}:
                origin = ("Front" if name.startswith("Front") else "Rear") + "FrictionScale"
                value = old[origin]
                action, confidence = "split_axle_friction", "provisional"
            elif table == "List_TorqueCurve" and name == "ZeroThrottleTorqueScale":
                value = zero["TorqueScale"]
                origin = "torque.zero.TorqueScale"
                action, confidence = "fold_zero_throttle_scale", "candidate_rule"
            elif table == "List_TorqueCurve" and re.fullmatch(r"v\d+",name) and name not in old:
                if int(name[1:]) < count:
                    raise MappingError("Refusing to invent active torque samples")
                value = 0.0
                action, confidence = "pad_inactive_torque_sample", "outside_active_count"
            elif name in old:
                value = old[name]
            else:
                raise MappingError(f"Unmapped target column {table}.{name}")
            if isinstance(value, float) and not math.isfinite(value):
                raise MappingError(f"Nonfinite value {role}.{name}")
            out[name] = value
            source_value = old.get(origin)
            if origin == "torque.zero.TorqueScale":
                source_value = zero["TorqueScale"]
            elif origin == "AssistsSTMSlipDefMin + AssistsSTMSlipDefMax":
                source_value = {c:car[c] for c in ("AssistsSTMSlipDefMin","AssistsSTMSlipDefMax")}
            elif origin and origin.startswith("spring."):
                source_role, source_col = origin.rsplit(".",1)
                source_value = source["nodes"][source_role]["row"][source_col]
            mapping.append({"role":role,"table":table,"target_column":name,"source_expression":origin,
                            "source_value":source_value,"target_value":value,"action":action,"confidence":confidence,
                            "category":category(table,name)})
        for name in sorted(old.keys() - target_columns):
            reason = {
                "AssistsSTMSlipDefMin":"Moved to AutoSteerOverrides lookup by both STM thresholds.",
                "AssistsSTMSlipDefMax":"Moved to AutoSteerOverrides lookup by both STM thresholds.",
                "GasBurnRateFullThrottle":"Removed from FM4 engine schema; fuel consumption equivalence not established.",
                "GasBurnRateZeroThrottle":"Removed from FM4 engine schema; fuel consumption equivalence not established.",
                "FrontFrictionScale":"Provisionally expanded into FrontLatFrictionScale and FrontLongFrictionScale.",
                "RearFrictionScale":"Provisionally expanded into RearLatFrictionScale and RearLongFrictionScale.",
                "TorqueCurveZeroThrottleID":"FM3 zero curve scale folded into FM4 full curve; source shape not representable here.",
                "EngineID":"Curve ownership retained through camshaft dependency; target curve table has no EngineID.",
            }.get(name)
            if reason is None:
                raise MappingError(f"Unreviewed removed source field {table}.{name}")
            drops.append({"role":role,"table":table,"column":name,"source_value":old[name],
                          "reason":reason + " Raw value retained in source IR."})
        candidate["nodes"][role] = {"table":table,"pk":primary,"row":out}

    tire_deps = native_tire_dependencies(target_db,candidate)
    unreviewed = [m for m in mapping if m["action"] == "copy_native_value" and
                  (m["target_column"].lower().endswith("id") or m["target_column"].lower() == "ordinal")]
    return {"candidate":candidate,"mapping":mapping,"dropped_source_fields":drops,"assumptions":assumptions,
            "external_dependencies":external,"native_tire_dependencies":tire_deps,
            "unreviewed_reference_fields":unreviewed,
            "id_map":[{"table":t,"source_id":s,"target_id":v} for (t,s),v in sorted(allocation.items())]}


def native_tire_dependencies(target_db, candidate):
    """Enumerate selected native curves after any compound reassignment."""
    tc = schema(target_db)
    tire_deps = []
    visited = set()
    def visit(table, value):
        key = (table,value)
        if key in visited:
            return
        visited.add(key)
        primary = pk(tc[table])
        row = one(rows(target_db,table,qi(primary)+"=?",(value,)),str(key))
        tire_deps.append({"table":table,"pk":primary,"id":value,"row":row})
        for col,val in row.items():
            if table == "List_TireCompound" and col.startswith("FrictionMultiCurve"):
                visit("List_TireFrictionMultiCurve",val)
            elif table == "List_TireCompound" and col.startswith("AffectCurve"):
                visit("List_TireAffectCurve",val)
            elif table == "List_TireFrictionMultiCurve" and col.startswith("TireFrictionCurve"):
                visit("List_TireFrictionCurve",val)
    visit("List_TireCompound",candidate["nodes"]["List_UpgradeTireCompound"]["row"]["TireCompoundID"])
    return tire_deps


def refresh_tire_dependencies(target_db, result):
    deps = native_tire_dependencies(target_db,result["candidate"])
    result["native_tire_dependencies"] = deps
    selected = deps[0]
    for external in result["external_dependencies"]:
        if external["table"] == "List_TireCompound" and external["target_id"] != selected["id"]:
            external["baseline_target_id"] = external["target_id"]
            external["target_id"] = selected["id"]
            external["row"] = selected["row"]
            external["identity"] = list(registry_label(selected["row"],selected["table"],selected["pk"]))
            external["policy"] = "experimental_cross_car_compound_choice"


def write_patch(path, target_db, candidate):
    """Schema-only FM4 SQLite + candidate rows, created exclusively (no overwrite)."""
    path = Path(path)
    if path.exists():
        raise MappingError(f"Output already exists: {path}")
    sc = schema(target_db)
    seen = {}
    with closing(sqlite3.connect(path)) as out:
        for table in sorted({n["table"] for n in candidate["nodes"].values()}):
            out.execute(sc[table]["sql"])
        for node in candidate["nodes"].values():
            table,row = node["table"],node["row"]
            key = (table,row[node["pk"]])
            if key in seen:
                if row != seen[key]:
                    raise MappingError("Shared dependency converted inconsistently")
                continue
            seen[key] = row
            out.execute("INSERT INTO " + qi(table) + " (" + ",".join(map(qi,row)) + ") VALUES (" + ",".join("?" for _ in row) + ")",tuple(row.values()))
        out.commit()
        integrity = out.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise MappingError(integrity)
    return {"path":str(path.resolve()),"tables":len({t for t,_ in seen}),"rows":len(seen),"integrity_check":integrity,"sha256":sha(path)}


def validate(candidate, target_db, patch_path, source=None):
    issues, checks, warnings = [], [], []
    tc = schema(target_db)
    tire_dependencies = native_tire_dependencies(target_db,candidate)
    with closing(connect(patch_path)) as saved:
        for role,node in candidate["nodes"].items():
            table,row = node["table"],node["row"]
            expected_columns = [c["name"] for c in tc[table]["columns"]]
            if list(row) != expected_columns:
                issues.append(f"Column mismatch {role}")
            exists = target_db.execute("SELECT 1 FROM "+qi(table)+" WHERE "+qi(node["pk"])+"=?",(row[node["pk"]],)).fetchone()
            if exists:
                issues.append(f"ID collision {role}")
            actual = one(rows(saved,table,qi(node["pk"])+"=?",(row[node["pk"]],)),role)
            if actual != row:
                issues.append(f"Serialized values changed {role}")
            checks.append({"role":role,"schema_and_roundtrip_checked":True})
        for edge in candidate["edges"]:
            origin = candidate["nodes"][edge["from"]]
            target = candidate["nodes"][edge["to"]]
            if origin["row"][edge["column"]] != target["row"][target["pk"]]:
                issues.append(f"Broken dependency {edge}")
        for role in ("spring.front","spring.rear","antiroll.front","antiroll.rear"):
            row = candidate["nodes"][role]["row"]
            bases=("SwaybarStiffness",) if role.startswith("antiroll.") else ("RideHeight","SpringRate","DampenBumpRate","DampenReboundRate")
            for base in bases:
                if not row["Min"+base] <= row["Def"+base] <= row["Max"+base]:
                    original = source["nodes"].get(role,{}).get("row",{}) if source else {}
                    keys = ["Min"+base,"Def"+base,"Max"+base]
                    inherited = (row["Min"+base] <= row["Max"+base] and
                                 all(k in original and row[k] == original[k] for k in keys))
                    if inherited:
                        warnings.append({"role":role,"field":base,
                                         "reason":"inherited_source_stock_default_outside_adjustable_bounds",
                                         "values":{k:row[k] for k in keys},
                                         "action":"preserved_without_clamping","runtime_verified":False})
                    else:
                        issues.append(f"Invalid tuning range {role}.{base}")
    car = candidate["nodes"]["car"]["row"]
    mass = candidate["nodes"]["List_UpgradeCarBodyWeight"]["row"]["Mass"]
    if not math.isclose(car["CurbWeight"] * 100,mass,rel_tol=1e-7,abs_tol=1e-5):
        issues.append("Stock catalog mass and body mass disagree; nonzero stock modifiers need analysis")
    return {"passed":not issues,"issues":issues,"nodes_checked":len(checks),"internal_edges_checked":len(candidate["edges"]),
            "native_tire_dependencies_checked":len(tire_dependencies),
            "warnings":warnings,"stock_tuning_review_required":bool(warnings),
            "checks":checks,"scope":"declared core dependencies and schema; NOT full loader/assets/foreign-key coverage","runtime_tested":False}


def compare(candidate, reference, target_db):
    """Compare physical roles, avoiding false differences from fresh IDs."""
    output = []
    ce = {(e["from"],e["column"]):e["to"] for e in candidate["edges"]}
    re_edges = {(e["from"],e["column"]):e["to"] for e in reference["edges"]}
    tc = schema(target_db)
    for role in sorted(candidate["nodes"].keys() | reference["nodes"].keys()):
        a,b = candidate["nodes"].get(role),reference["nodes"].get(role)
        if a is None or b is None:
            output.append({"role":role,"status":"missing_role","candidate_present":a is not None,"reference_present":b is not None,"category":"structure"})
            continue
        for col,av in a["row"].items():
            bv = b["row"].get(col)
            item = {"role":role,"table":a["table"],"column":col,"candidate":av,"fm4_reference":bv,"category":category(a["table"],col)}
            if col == a["pk"] or (ce.get((role,col)) is not None and ce.get((role,col)) == re_edges.get((role,col))):
                item.update(status="identity_remap",category="identity")
            elif a["table"] == "List_TorqueCurve" and re.fullmatch(r"v\d+",col) and int(col[1:]) >= max(a["row"]["NumTorqueValues"],b["row"]["NumTorqueValues"]):
                item.update(status="inactive_padding_equal" if av == bv else "inactive_padding_difference",category="inactive_padding")
            elif av == bv:
                item["status"] = "exact"
            elif isinstance(av,(int,float)) and isinstance(bv,(int,float)) and (isinstance(av,float) or isinstance(bv,float)) and math.isclose(av,bv,rel_tol=1e-6,abs_tol=1e-6):
                item["status"] = "within_numeric_tolerance"
            elif col == "AutoSteerOverrideID":
                aa = one(rows(target_db,"AutoSteerOverrides","Id=?",(av,)),"auto candidate")
                bb = one(rows(target_db,"AutoSteerOverrides","Id=?",(bv,)),"auto reference")
                item["status"] = "equivalent_registry_payload" if {k:v for k,v in aa.items() if k!="Id"} == {k:v for k,v in bb.items() if k!="Id"} else "different"
            else:
                item["status"] = "different"
            if isinstance(av,(int,float)) and isinstance(bv,(int,float)) and item["status"] not in {"identity_remap","equivalent_registry_payload"}:
                item["delta_candidate_minus_reference"] = av-bv
            output.append(item)
    stats = Counter(x["status"] for x in output)
    differences = [x for x in output if x["status"] in {"different","missing_role","inactive_padding_difference"}]
    return {"tolerance":{"absolute":1e-6,"relative":1e-6,"note":"numerical rounding tolerance, not a handling tolerance"},
            "counts":dict(stats),"differences_by_category":dict(Counter(x["category"] for x in differences)),
            "differences":differences,"fields":output,"runtime_equivalence_claimed":False}


def report_text(result, comparison, validation, patch, compatibility=None):
    diff = comparison["differences"]
    lines = [f"# {result['candidate']['media_name']}: prototype konversi FM3 ke FM4", "",
        "Prototype offline konfigurasi stock. Hasil menggunakan schema FM4, nilai FM3 sebagai baseline, dan registry/kurva ban native FM4. Bila profil kalibrasi dipakai, perubahan dicatat di calibration_changes.json. Mobil FM4 asli hanya digunakan oleh comparator sesudah konversi. Tidak ada game, SQL instalasi, atau modifikasi database sumber dijalankan.", "",
        "## Hasil", "", f"- {patch['rows']} baris pada {patch['tables']} tabel ditulis ke `candidate_stock.slt`.",
        f"- Validasi struktur: {'lulus' if validation['passed'] else 'gagal'}; {validation['internal_edges_checked']} hubungan internal diperiksa; {len(validation.get('warnings',[]))} peringatan tuning bawaan sumber.",
        f"- Perbandingan: `{json.dumps(comparison['counts'])}`.",
        f"- Selisih menurut kategori: `{json.dumps(comparison['differences_by_category'])}`.",
        "- ID baru dan padding kurva yang tidak aktif dilaporkan terpisah. Kedekatan angka bukan persentase kesamaan handling.","",
        "## Selisih yang masih membutuhkan keputusan", "", "| Peran / tabel | Kolom | Hasil converter | FM4 asli | Kategori |", "|---|---|---:|---:|---|"]
    if "calibration" in result:
        info=result["calibration"]
        lines[3:3]=[f"**Profil kalibrasi: {info['mode']}**. Suspensi aktif: `{info.get('active_suspension_profile','legacy_tier')}`. "
                    f"Gerbang profil tambahan: `{info.get('profile_gates',{})}`. "
                    "Mode experimental adalah kandidat penelitian meskipun gerbang validasi gagal; hasil cocok pada satu mobil tidak mengesahkan pemakaian universal.",""]
    if comparison.get("reference_available") is False:
        lines[3:3] = [
            "**Tidak ada mobil pembanding native FM4.** Konversi dan validasi terhadap sumber FM3 tetap dijalankan. "
            "Perbandingan native tidak tersedia; daftar selisih kosong bukan berarti cocok dengan FM4.", ""]
    if compatibility:
        lines[3:3]=[f"**Audit pasangan:** spesifikasi memenuhi kriteria pembanding: `{compatibility['pairing']['eligible']}`; "
                    f"perlu review: `{compatibility['requires_manual_review']}`. "
                    "Audit dilakukan setelah kandidat dibuat; rincian spesifikasi, domain kurva, dan stock role ada di `compatibility.json`. "
                    "Indeks torque pada domain berbeda bukan perbandingan fisika pada RPM identik.",""]
    if "code_semantics" in result:
        info=result["code_semantics"]
        lines[3:3]=["**Adapter koordinat dari kode aktif.** "
                    f"CMHeight target ditulis `{info['target_raw_cmheight']}` agar input Y komponen massa utama "
                    f"mempertahankan `{info['source_main_mass_block_center_y']}` pada jalur kode yang ditelusuri. "
                    "Tinggi referensi Data_Car memakai MaxRideHeight sumber. MaxStretchDeltaFromRideHeight "
                    "dipertahankan setelah lolos audit bahwa cap tidak memotong batas extension FM3 "
                    "di seluruh rentang spring part stock terpilih. "
                    "Ini tidak menyalin tuning native FM4 dan belum membuktikan handling runtime. "
                    "Lihat `code_semantics.json` dan `effective_comparison.json`.",""]
    for item in diff:
        if item["status"] == "missing_role":
            lines.append(f"| {item['role']} | baris | {item['candidate_present']} | {item['reference_present']} | structure |")
        else:
            fmt = lambda v: str(v).replace("|","\\|")
            lines.append(f"| {item['role']} | {item['column']} | {fmt(item['candidate'])} | {fmt(item['fm4_reference'])} | {item['category']} |")
    lines += ["", "## Aturan khusus", "",
        "- Semua stock dipilih melalui `IsStock=1`; level 1 yang stock tetap disertakan.",
        "- ID entity dan part dialokasikan ulang, semua hubungan internal terdaftar ikut dipetakan. Rentang ID ini hanya untuk eksperimen offline; batas loader belum diverifikasi.",
        "- FM3 full-throttle curve dipertahankan; `ZeroThrottleTorqueScale` diambil dari scale kurva zero-throttle sumber. Shape kurva zero-throttle lama tidak dapat diwakili langsung oleh schema target dan tetap disimpan di source IR. Kesetaraan engine braking belum terbukti.",
        "- Friction scale chassis FM3 per axle disalin ke lateral dan longitudinal FM4 sebagai hipotesis awal.",
        ("- Stock ride height memakai MaxRideHeight sumber; cap extension dari cohort FM4 diverifikasi tidak aktif "
         "di rentang spring part stock. CVT shift time tetap default cohort. Rincian ada di code_semantics.json dan assumptions.json."
         if "code_semantics" in result else
         "- Mode legacy: stock ride height memakai DefRideHeight sumber sebagai asumsi. Max stretch dan CVT shift time "
         "memakai nilai modus pada pemilik lain di FM4; distribusi dan pengecualian pemilik tercatat di assumptions.json."),
        "- Compound dipetakan melalui identitas nama, kemudian menggunakan seluruh keluarga kurva FM4. Tidak ada tabel ban global disalin ke patch.",
        "- STM threshold dipetakan ke AutoSteerOverrides. Jika beberapa ID punya payload identik, pilih ID terkecil; comparator membedakan ekuivalensi isi dari kesamaan ID.",
        "- Tidak ada scaling satuan otomatis. Semua nilai tanpa unit yang telah dibuktikan tetap native dan memerlukan pemeriksaan loader/runtime.","",
        "## Batas prototype", "",
        "`candidate_stock.slt` adalah database riset terpisah, bukan DLC siap pasang. MediaName dan resource strings sumber dipertahankan. Flag instalasi/content, katalog, PI/rating hasil simulasi lama, manufacturer/part metadata, asset lookup, collision/model, title update, paket DLC, dan seluruh pilihan upgrade belum diadaptasi atau divalidasi untuk game. Schema SQLite tidak mendeklarasikan seluruh foreign key; validasi hanya mencakup edge yang tercantum.",
        "", "Selisih antara data mobil FM3 dan FM4 tidak dihapus dengan menyalin jawaban dari mobil FM4 pembanding. Perubahan ban, pusat massa, spring/damping, steering, tank size, dan grip chassis harus menjadi keputusan kalibrasi tersendiri. GasTankSize dicatat native; selisihnya tidak digunakan untuk menebak faktor konversi unit.",
        "", "## Berkas", "", "- `mapping.json`: aturan per kolom, nilai, confidence, kolom sumber yang tidak ada di target.",
        "- `source_ir.json`, `candidate_ir.json`, `reference_fm4_ir.json`: konfigurasi berdasarkan peran komponen.",
        "- `comparison.json`: semua kolom, selisih, toleransi numerik dan pengecualian identitas/padding.",
        "- `external_dependencies.json`: registry FM4 yang dipakai dan seluruh dependency ban.",
        "- `assumptions.json`, `id_map.json`, `validation.json`, `manifest.json`: asumsi, pemetaan ID, validasi, hash sumber/output.", ""]
    return "\n".join(lines)


def mapping_text(result, source):
    lines = [f"# Mapping database FM3 ke FM4: {source['media_name']} stock", "",
             "Mapping ini berasal dari prototype yang berjalan pada database lokal. Status structural_only berarti nilai dapat ditulis ke schema FM4; makna unit dan kesetaraan runtime belum dibuktikan.", "",
             "## Pemetaan per komponen", "", "| Peran | Tabel FM4 | Kolom target |", "|---|---|---:|"]
    for role,node in sorted(result["candidate"]["nodes"].items()):
        lines.append(f"| {role} | {node['table']} | {len(node['row'])} |")
    lines += ["", "## Transformasi selain penyalinan nilai dan pemetaan ID", "",
              "| Peran | Kolom target | Sumber / aturan | Status |", "|---|---|---|---|"]
    for m in result["mapping"]:
        if m["action"] in {"copy_native_value","remap_reference","allocate_primary_key","native_fm4_registry","pad_inactive_torque_sample"}:
            continue
        lines.append(f"| {m['role']} | {m['target_column']} | {m['source_expression'] or m['action']} | {m['confidence']} |")
    lines += ["", "Tambahan v151–v185 diisi nol hanya di luar NumTorqueValues. Tidak ada sampel aktif atau unit yang diciptakan.", "",
              "## Field sumber yang dihapus dari schema target", "", "| Peran | Kolom | Perlakuan |", "|---|---|---|"]
    for item in result["dropped_source_fields"]:
        lines.append(f"| {item['role']} | {item.get('column','seluruh row')} | {item['reason']} |")
    lines += ["", "## Cakupan yang belum terhubung", "",
              "Kolom berikut dipertahankan sebagai nilai mentah. Tidak dihitung sebagai foreign key yang telah divalidasi; beberapa merupakan enum/sentinel dan bukan referensi row. Pemakaiannya harus diperiksa sebelum instalasi.", "",
              "| Peran | Kolom | Nilai |", "|---|---|---|"]
    for item in result["unreviewed_reference_fields"]:
        lines.append(f"| {item['role']} | {item['target_column']} | {item['target_value']} |")
    lines += ["", "Tabel upgrade yang tidak memiliki pilihan stock untuk source ini:", "",
              ", ".join("`"+t+"`" for t in source["empty_stock_tables"]), "",
              "Upgrade non-stock, engine/drivetrain swaps, CarPartPositions, camera/UI/localisasi, geometry/collision, instalasi/content flags dan registrasi DLC berada di luar output prototype ini.", ""]
    return "\n".join(lines)


def run(source_path, target_path, out_dir, media=MEDIA, id_base=ID_BASE, calibration_rules=None, calibration_mode="conservative", code_semantics=False):
    source_path,target_path,out_dir = map(lambda p:Path(p).resolve(),(source_path,target_path,out_dir))
    # Create-only run directories prevent accidental clobbering or writing into
    # either game root, including through a path alias/junction.
    for dbpath in (source_path,target_path):
        game_root = dbpath.parent.parent.parent
        if out_dir == game_root or game_root in out_dir.parents:
            raise MappingError("Output must be outside both source game directories")
    if out_dir.exists():
        raise MappingError(f"Choose a new output directory: {out_dir}")
    before = {"fm3":sha(source_path),"fm4":sha(target_path)}
    with closing(connect(source_path)) as source_db, closing(connect(target_path)) as target_db:
        source = extract_stock(source_db,media)
        result = convert(source_db,target_db,source,id_base)
        baseline_candidate=copy.deepcopy(result["candidate"])
        rules=None
        if calibration_rules is not None:
            from calibration import apply_to_result
            rules=json.loads(Path(calibration_rules).read_text(encoding="utf-8"))
            apply_to_result(result,source,rules,calibration_mode)
            refresh_tire_dependencies(target_db,result)
        if code_semantics:
            from code_semantics import apply as apply_code_semantics
            apply_code_semantics(result,source)
        out_dir.mkdir(parents=True)
        patch = write_patch(out_dir/"candidate_stock.slt",target_db,result["candidate"])
        validation = validate(result["candidate"],target_db,out_dir/"candidate_stock.slt",source=source)
        if not validation["passed"]:
            dump(out_dir/"validation.json",validation)
            raise MappingError(f"Candidate validation failed: {validation['issues']}")
        # A new FM3-only car has no native FM4 answer. Comparison is optional;
        # absence must not turn an otherwise valid conversion into an error.
        matches = rows(target_db, "Data_Car", "MediaName=?", (media,))
        reference = extract_stock(target_db,media) if matches else None
        if reference is not None:
            comparison = compare(result["candidate"],reference,target_db)
            from compatibility import audit
            compatibility = audit(source,reference)
        else:
            comparison = {"reference_available":False, "status":"not_available",
                          "reason":"No matching MediaName in the target database",
                          "counts":{}, "differences_by_category":{}, "differences":[]}
            compatibility = {"status":"not_available", "pairing":{"eligible":False},
                             "reason":comparison["reason"], "requires_manual_review":True}
        dump(out_dir/"compatibility.json",compatibility)
        if code_semantics:
            from code_semantics import compare_centers
            from effective_physics import compare_effective
            from suspension_semantics import compare_geometry
            dump(out_dir/"code_semantics.json",result["code_semantics"])
            dump(out_dir/"effective_comparison.json",{
                "centers":compare_centers(source,result["candidate"],reference),
                "suspension_vs_source":compare_effective(source,result["candidate"]),
                "suspension_vs_native_fm4":compare_effective(reference,result["candidate"]) if reference else None,
                "suspension_geometry_vs_source":compare_geometry(source,result["candidate"]),
                "scope":"Normalized coefficients and traced center input; not forces, full solver or runtime handling"})
        if rules is not None:
            dump(out_dir/"calibration_rules.json",rules)
            dump(out_dir/"calibration_changes.json",result["calibration"])
            dump(out_dir/"baseline_comparison.json",
                 compare(baseline_candidate,reference,target_db) if reference else comparison)
        dump(out_dir/"source_ir.json",source)
        dump(out_dir/"candidate_ir.json",result["candidate"])
        if reference is not None:
            dump(out_dir/"reference_fm4_ir.json",reference)
        dump(out_dir/"mapping.json",{"columns":result["mapping"],"dropped_source_fields":result["dropped_source_fields"],
                                      "unreviewed_reference_fields":result["unreviewed_reference_fields"]})
        (out_dir/"MAPPING.md").write_text(mapping_text(result,source),encoding="utf-8")
        dump(out_dir/"id_map.json",result["id_map"])
        dump(out_dir/"assumptions.json",result["assumptions"])
        dump(out_dir/"external_dependencies.json",{"registries":result["external_dependencies"],"native_tires":result["native_tire_dependencies"]})
        dump(out_dir/"comparison.json",comparison)
        dump(out_dir/"validation.json",validation)
        (out_dir/"REPORT.md").write_text(report_text(result,comparison,validation,patch,compatibility),encoding="utf-8")
    after = {"fm3":sha(source_path),"fm4":sha(target_path)}
    if before != after:
        raise MappingError("Input hashes changed during run")
    manifest = {"source":str(source_path),"target_schema_and_reference":str(target_path),"media_name":media,
                "source_hashes_before":before,"source_hashes_after":after,"sources_unchanged":True,
                "source_scope":"Disc1 base databases only; no TU/DLC overlays applied", "converter_sha256":sha(__file__),
                "patch":patch,"installable":False,"runtime_tested":False,
                "compatibility_code_sha256":sha(Path(__file__).with_name("compatibility.py")),
                "requires_manual_review":compatibility["requires_manual_review"],
                "outputs":{p.name:sha(p) for p in sorted(out_dir.iterdir()) if p.is_file()}}
    if calibration_rules is not None:
        manifest["calibration"]={"rules_path":str(Path(calibration_rules).resolve()),"rules_file_sha256":sha(calibration_rules),
                                 "mode":calibration_mode,"calibration_code_sha256":sha(Path(__file__).with_name("calibration.py"))}
        if "remaining7" in rules:
            manifest["calibration"]["remaining_code_sha256"]=sha(Path(__file__).with_name("remaining.py"))
        if "benchmark_refinements" in rules:
            manifest["calibration"]["refinements_code_sha256"]=sha(Path(__file__).with_name("refinements.py"))
        for key in ("suspension_v2","drivetrain_v2"):
            if key in rules:
                manifest["calibration"][key+"_code_sha256"]=sha(Path(__file__).with_name(key+".py"))
    if code_semantics:
        manifest["code_semantics"]={"enabled":True,"code_sha256":{
            name:sha(Path(__file__).with_name(name)) for name in ("code_semantics.py","effective_physics.py","suspension_semantics.py")}}
    dump(out_dir/"manifest.json",manifest)
    return {"output":str(out_dir),"patch":patch,"comparison":comparison["counts"],"differences":comparison["differences_by_category"],
            "validation_passed":True,"sources_unchanged":True,"requires_manual_review":compatibility["requires_manual_review"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fm3",type=Path,default=FM3_DEFAULT)
    parser.add_argument("--fm4",type=Path,default=FM4_DEFAULT)
    parser.add_argument("--media-name",default=MEDIA)
    parser.add_argument("--id-base",type=int,default=ID_BASE)
    parser.add_argument("--out",type=Path,required=True,help="New output directory, outside source game folders")
    parser.add_argument("--calibration-rules",type=Path,help="Frozen cross-car rules.json; matching target car not read by calibration")
    parser.add_argument("--calibration-mode",choices=("conservative","estimated","experimental"),default="conservative",
                        help="experimental enables offline research estimates, including rejected suspension selection")
    parser.add_argument("--code-semantics",action="store_true",
                        help="Opt-in stock CM/ride-reference adapter and extension-cap audit from paired code; rejects unsupported inputs")
    args = parser.parse_args()
    try:
        print(json.dumps(run(args.fm3,args.fm4,args.out,args.media_name,args.id_base,args.calibration_rules,args.calibration_mode,args.code_semantics),indent=2))
    except (MappingError,sqlite3.Error,OSError) as exc:
        parser.exit(1,f"Conversion stopped: {exc}\n")


if __name__ == "__main__":
    main()
