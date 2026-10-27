"""Empirical FM3 -> FM4 calibration research, with Toyota held out."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from contextlib import closing
import hashlib
import json
import math
from pathlib import Path
import statistics

import converter as c


def stock(db, table, scope, owner):
    return c.one(c.rows(db, table, c.qi(scope)+"=? AND IsStock=1", (owner,)), table)


def calibration_record(db, car):
    """Read only the stock components relevant to the 36 investigated columns."""
    ordinal = car["Id"]
    body_id = stock(db,"List_UpgradeCarBody","Ordinal",ordinal)["CarBodyID"]
    engine_id = stock(db,"List_UpgradeEngine","Ordinal",ordinal)["EngineID"]
    spring = stock(db,"List_UpgradeSpringDamper","Ordinal",ordinal)
    nodes = {"car":car,
             "body":c.one(c.rows(db,"Data_CarBody","Id=?",(body_id,)),"body"),
             "engine":c.one(c.rows(db,"Data_Engine","EngineID=?",(engine_id,)),"engine"),
             "List_UpgradeCarBodyWeight":stock(db,"List_UpgradeCarBodyWeight","CarBodyId",body_id),
             "List_UpgradeCarBodyChassisStiffness":stock(db,"List_UpgradeCarBodyChassisStiffness","CarbodyId",body_id)}
    for table in ("List_UpgradeBrakes","List_UpgradeTireCompound"):
        nodes[table] = stock(db,table,"Ordinal",ordinal)
    for axle in ("front","rear"):
        nodes["spring."+axle] = c.one(c.rows(db,"List_SpringDamperPhysics","SpringDamperPhysicsID=?",
                                           (spring[axle.title()+"SpringDamperPhysicsID"],)),"spring."+axle)
        choice = stock(db,"List_UpgradeAntiSway"+axle.title(),"Ordinal",ordinal)
        nodes["antiroll."+axle] = c.one(c.rows(db,"List_AntiSwayPhysics","AntiSwayPhysicsID=?",
                                             (choice["AntiSwayPhysicsID"],)),"antiroll."+axle)
    return {"id":ordinal,"media_name":car["MediaName"],"year":car["Year"],"make_id":car["MakeID"],
            "engine_id":engine_id,"body_id":body_id,"nodes":nodes}


def collect(source_db, target_db, heldout_media=c.MEDIA):
    sources = {r["Id"]:r for r in c.rows(source_db,"Data_Car")}
    targets = {r["Id"]:dict(r) for r in target_db.execute("SELECT Id,MediaName,Year,MakeID FROM Data_Car")}
    heldout = c.one([r for r in sources.values() if r["MediaName"]==heldout_media],"heldout")
    heldout_engine = stock(source_db,"List_UpgradeEngine","Ordinal",heldout["Id"])["EngineID"]
    pairs, exclusions = [], []
    for identity in sorted(sources.keys() & targets.keys()):
        a,b = sources[identity],targets[identity]
        # Conservative matching: renamed or changed-year variants are not used.
        if a["MediaName"] != b["MediaName"] or (a["Year"],a["MakeID"]) != (b["Year"],b["MakeID"]):
            exclusions.append({"id":identity,"fm3":a["MediaName"],"fm4":b["MediaName"],"reason":"identity_or_year_mismatch"})
            continue
        # Exclude BEFORE reading any FM4 held-out calibration; siblings sharing
        # the source engine are excluded too, preventing shared-row leakage.
        engine = stock(source_db,"List_UpgradeEngine","Ordinal",identity)["EngineID"]
        if identity == heldout["Id"] or engine == heldout_engine:
            exclusions.append({"id":identity,"fm3":a["MediaName"],"reason":"heldout_car_or_shared_engine"})
            continue
        try:
            target_car = c.one(c.rows(target_db,"Data_Car","Id=?",(identity,)),"target car")
            pair = {"source":calibration_record(source_db,a),"target":calibration_record(target_db,target_car)}
        except c.MappingError as error:
            exclusions.append({"id":identity,"fm3":a["MediaName"],"reason":"stock_extraction_error","detail":str(error)})
            continue
        # Entire source engine groups go to one split, not individual rows.
        group = str(engine)
        bucket = int(hashlib.sha256(("fm3-fm4-calibration-v1:"+group).encode()).hexdigest()[:8],16) % 5
        pair["split"] = "validation" if bucket == 0 else "training"
        pairs.append(pair)
    return {"pairs":pairs,"exclusions":exclusions,"heldout_media":heldout_media,
            "heldout_source_id":heldout["Id"],"heldout_source_engine_id":heldout_engine,
            "counts":dict(Counter(p["split"] for p in pairs)),
            "common_ids":len(sources.keys() & targets.keys())}


def source_baseline(record, role, column):
    row = record["nodes"][role]
    if role == "List_UpgradeCarBodyChassisStiffness":
        column = column.replace("LatFriction","Friction").replace("LongFriction","Friction")
    return row[column]


def fields36():
    fields = [("List_UpgradeBrakes","ReleasePointABSRearFullSteer")]
    fields += [("List_UpgradeCarBodyChassisStiffness",side+direction+"FrictionScale") for side in ("Front","Rear") for direction in ("Lat","Long")]
    fields += [("List_UpgradeCarBodyWeight","CMHeight"),("List_UpgradeTireCompound","TireCompoundID")]
    fields += [("antiroll."+axle,prefix+"SwaybarStiffness") for axle in ("front","rear") for prefix in ("Def","Min","Max")]
    fields += [("car",x) for x in ("SteerMaxAngle","SteerMaxAngVelTurning","SteerMaxAngVelStraighten","SteerAngVelCountersteer")]
    fields += [("engine","GasTankSize")]
    fields += [("spring."+axle,prefix+base) for axle in ("front","rear")
               for base in ("SpringRate","DampenBumpRate","DampenReboundRate") for prefix in ("Def","Min","Max")]
    return fields


def equal(a,b):
    return math.isclose(a,b,rel_tol=1e-6,abs_tol=1e-6)


def exploratory_summary(data):
    output = []
    for role,col in fields36():
        train = [p for p in data["pairs"] if p["split"]=="training"]
        xy = [(source_baseline(p["source"],role,col),p["target"]["nodes"][role][col]) for p in train]
        ratios = [y/x for x,y in xy if x!=0]
        differences = [y-x for x,y in xy]
        output.append({"role":role,"column":col,"n":len(xy),
                       "unchanged":sum(equal(x,y) for x,y in xy),
                       "source_modes":Counter(x for x,y in xy).most_common(5),
                       "target_modes":Counter(y for x,y in xy).most_common(5),
                       "median_ratio":statistics.median(ratios) if ratios else None,
                       "median_delta":statistics.median(differences),
                       "pairs":xy})
    return output


def quantized_total(records, role_prefix, field):
    """Infer a common total from intervals implied by 4-decimal axle values.

    This is a hypothesis about data authoring/rounding, not a runtime formula.
    Use native FM4 weight split for discovering the relation, source split for
    later prediction. Keep both feasible interval and fallback residuals.
    """
    lows, highs, estimates = [], [], []
    for rec in records:
        n = rec["nodes"]
        front = n["List_UpgradeCarBodyWeight"]["CMBackFront"]
        for axle,fraction in (("front",front),("rear",1-front)):
            if not 0 < fraction < 1:
                continue
            v = n[role_prefix+"."+axle][field]
            lows.append((v-0.000050001)/fraction)
            highs.append((v+0.000050001)/fraction)
            estimates.append(v/fraction)
    low,high = max(lows),min(highs)
    feasible = low <= high
    return {"value":(low+high)/2 if feasible else statistics.median(estimates),
            "feasible_rounding_interval":[low,high] if feasible else None,
            "interval_consistent":feasible,"observations":len(estimates)}


def tier_key(record):
    n = record["nodes"]
    return format(n["spring.front"]["DefSpringRate"]+n["spring.rear"]["DefSpringRate"],".2f")


def fit_rules(data):
    """Use TRAINING only. All candidate choices/thresholds precede validation."""
    train = [p for p in data["pairs"] if p["split"]=="training"]
    model = {"version":1,"heldout_media":data["heldout_media"],"training_ids":[p["source"]["id"] for p in train],
             "validation_ids":[p["source"]["id"] for p in data["pairs"] if p["split"]=="validation"],
             "training_engine_ids":sorted({p["source"]["engine_id"] for p in train}),
             "validation_engine_ids":sorted({p["source"]["engine_id"] for p in data["pairs"] if p["split"]=="validation"}),
             "policy":{"strong_min_training":30,"strong_min_validation":10,"strong_train_match":0.99,"strong_validation_match":0.98,
                       "tier_min_training":5,"tier_train_concentration":0.80,"estimate_min_validation_covered":10,
                       "estimate_validation_tier_match":0.75,"estimate_max_relative_error_ratio_vs_baseline":0.70},
             "strong_rules":[],"tier_mappings":[],"target_tiers":{}}
    for role,column,kind in [
        ("List_UpgradeBrakes","ReleasePointABSRearFullSteer","constant"),
        ("car","SteerMaxAngle","scale"),
        ("car","SteerMaxAngVelTurning","constant"),
        ("car","SteerMaxAngVelStraighten","constant"),
        ("car","SteerAngVelCountersteer","constant"),
    ]:
        values = [p["target"]["nodes"][role][column] if kind=="constant" else
                  p["target"]["nodes"][role][column]/source_baseline(p["source"],role,column) for p in train]
        value = Counter(round(v,8) for v in values).most_common(1)[0][0]
        matches = sum(equal(v,value) for v in values)
        model["strong_rules"].append({"id":role+"."+column,"role":role,"column":column,"kind":kind,"value":value,
                                     "training_matches":matches,"training_n":len(values),
                                     "source_values_seen":sorted({source_baseline(p["source"],role,column) for p in train}),
                                     "training_eligible":matches/len(values)>=model["policy"]["strong_train_match"] and len(values)>=model["policy"]["strong_min_training"]})
    grouped = defaultdict(list)
    targets = defaultdict(list)
    for p in train:
        grouped[tier_key(p["source"])].append(tier_key(p["target"]))
        targets[tier_key(p["target"])].append(p["target"])
    for key,values in sorted(grouped.items(),key=lambda x:float(x[0])):
        counts = Counter(values)
        chosen,n = counts.most_common(1)[0]
        model["tier_mappings"].append({"source_total_key":key,"target_total_key":chosen,"support":len(values),"mode_count":n,
                                       "concentration":n/len(values),"distribution":dict(counts),
                                       "eligible":len(values)>=model["policy"]["tier_min_training"] and n/len(values)>=model["policy"]["tier_train_concentration"]})
    for key,records in targets.items():
        spring = quantized_total(records,"spring","DefSpringRate")
        bump = quantized_total(records,"spring","DefDampenBumpRate")
        rebound = quantized_total(records,"spring","DefDampenReboundRate")
        antiroll = {axle:statistics.median(r["nodes"]["antiroll."+axle]["DefSwaybarStiffness"] for r in records) for axle in ("front","rear")}
        spreads = {axle:max(abs(r["nodes"]["antiroll."+axle]["DefSwaybarStiffness"]-antiroll[axle]) for r in records) for axle in ("front","rear")}
        model["target_tiers"][key] = {"support":len(records),"spring_total":spring,"bump_total":bump,"rebound_total":rebound,
                                     "antiroll":antiroll,"antiroll_max_deviation":spreads}
    return model


def propose(record, model, mode="conservative", require_accepted=True):
    updates, notes = [], []
    for rule in model["strong_rules"]:
        if not rule.get("accepted" if require_accepted else "training_eligible"):
            continue
        old = source_baseline(record,rule["role"],rule["column"])
        if not any(equal(old,v) for v in rule["source_values_seen"]):
            notes.append({"rule":rule["id"],"status":"abstain_unseen_source_value","value":old})
            continue
        value = rule["value"] if rule["kind"]=="constant" else old*rule["value"]
        updates.append({"role":rule["role"],"column":rule["column"],"value":value,"rule":rule["id"],
                        "confidence":"validated_cross_car_pattern","input_value":old})
    if mode not in {"estimated","experimental"}:
        return updates,notes
    if mode == "estimated" and require_accepted and not model.get("estimated_profile_accepted"):
        return updates,[*notes,{"status":"estimated_profile_failed_validation_gate"}]
    if mode == "experimental" and not model.get("estimated_profile_accepted"):
        notes.append({"status":"EXPERIMENT_ONLY_validation_gate_failed","installable":False})
    key = tier_key(record)
    mapping = next((r for r in model["tier_mappings"] if r["source_total_key"]==key and r["eligible"]),None)
    if not mapping:
        return updates,[*notes,{"status":"abstain_ambiguous_or_unsupported_spring_tier","source_tier":key}]
    profile = model["target_tiers"][mapping["target_total_key"]]
    # Rounding feasibility is required, rather than silently fitting an average.
    if not all(profile[k]["interval_consistent"] for k in ("spring_total","bump_total","rebound_total")) or any(v>0.00011 for v in profile["antiroll_max_deviation"].values()):
        return updates,[*notes,{"status":"abstain_inconsistent_target_tier","target_tier":mapping["target_total_key"]}]
    front = record["nodes"]["List_UpgradeCarBodyWeight"]["CMBackFront"]
    if not 0 < front < 1:
        return updates,[*notes,{"status":"abstain_invalid_weight_distribution"}]
    pending = []
    for axle,fraction in (("front",front),("rear",1-front)):
        for role,field,total in [
            ("spring."+axle,"SpringRate",profile["spring_total"]["value"]*fraction),
            ("spring."+axle,"DampenBumpRate",profile["bump_total"]["value"]*fraction),
            ("spring."+axle,"DampenReboundRate",profile["rebound_total"]["value"]*fraction),
            ("antiroll."+axle,"SwaybarStiffness",profile["antiroll"][axle]),
        ]:
            row = record["nodes"][role]
            value = round(total,4)
            fixed = equal(row["Min"+field],row["Def"+field]) and equal(row["Max"+field],row["Def"+field])
            if not fixed and not row["Min"+field] <= value <= row["Max"+field]:
                return updates,[*notes,{"status":"abstain_prediction_outside_source_tune_range","role":role,"field":field}]
            for prefix in ("Def","Min","Max") if fixed else ("Def",):
                pending.append({"role":role,"column":prefix+field,"value":value,"rule":"suspension_tier_profile",
                                "confidence":"estimated_tier_not_universal","source_tier":key,
                                "target_tier":mapping["target_total_key"],"training_concentration":mapping["concentration"],
                                "input_value":row[prefix+field]})
    return updates+pending,notes


def field_metrics(pairs, model, mode, accepted=False):
    by_field = {}
    per_car = []
    for role,column in fields36():
        by_field[role+"."+column] = {"role":role,"column":column,"n":0,"baseline_matches":0,"predicted_matches":0,
                                   "baseline_absolute_error_sum":0.0,"predicted_absolute_error_sum":0.0,"regressions":0,"improvements":0}
    for pair in pairs:
        updates,notes = propose(pair["source"],model,mode,require_accepted=accepted)
        lookup = {(x["role"],x["column"]):x["value"] for x in updates}
        before,after = [],[]
        for role,column in fields36():
            original = source_baseline(pair["source"],role,column)
            predicted = lookup.get((role,column),original)
            actual = pair["target"]["nodes"][role][column]
            entry = by_field[role+"."+column]
            b,a = abs(original-actual),abs(predicted-actual)
            entry["n"]+=1
            entry["baseline_matches"]+=int(equal(original,actual))
            entry["predicted_matches"]+=int(equal(predicted,actual))
            entry["baseline_absolute_error_sum"]+=b
            entry["predicted_absolute_error_sum"]+=a
            entry["regressions"]+=int(a>b+1e-6)
            entry["improvements"]+=int(a+1e-6<b)
            if role.startswith(("spring.","antiroll.")):
                before.append(b/max(abs(actual),1e-6))
                after.append(a/max(abs(actual),1e-6))
        predicted_tier = next((x.get("target_tier") for x in updates if x["rule"]=="suspension_tier_profile"),None)
        per_car.append({"id":pair["source"]["id"],"media_name":pair["source"]["media_name"],
                        "engine_id":pair["source"]["engine_id"],"source_tier":tier_key(pair["source"]),
                        "actual_target_tier":tier_key(pair["target"]),"predicted_tier":predicted_tier,
                        "suspension_baseline_mean_relative_error":statistics.mean(before),
                        "suspension_predicted_mean_relative_error":statistics.mean(after),"notes":notes})
    for item in by_field.values():
        for kind in ("baseline","predicted"):
            item[kind+"_mae"] = item[kind+"_absolute_error_sum"]/max(item["n"],1)
    covered = [x for x in per_car if x["predicted_tier"] is not None]
    return {"fields":list(by_field.values()),"cars":per_car,"covered_suspension_cars":len(covered),
            "covered_suspension_tier_matches":sum(x["predicted_tier"]==x["actual_target_tier"] for x in covered),
            "covered_cars_improved":sum(x["suspension_predicted_mean_relative_error"]+1e-6<x["suspension_baseline_mean_relative_error"] for x in covered),
            "covered_cars_regressed":sum(x["suspension_predicted_mean_relative_error"]>x["suspension_baseline_mean_relative_error"]+1e-6 for x in covered),
            "covered_baseline_suspension_relative_error":statistics.mean(x["suspension_baseline_mean_relative_error"] for x in covered) if covered else None,
            "covered_predicted_suspension_relative_error":statistics.mean(x["suspension_predicted_mean_relative_error"] for x in covered) if covered else None}


def validate_rules(data, model):
    validation = [p for p in data["pairs"] if p["split"]=="validation"]
    train = [p for p in data["pairs"] if p["split"]=="training"]
    train_metrics = field_metrics(train,model,"estimated")
    metrics = field_metrics(validation,model,"estimated")
    for rule in model["strong_rules"]:
        stats = next(x for x in metrics["fields"] if x["role"]==rule["role"] and x["column"]==rule["column"])
        rule["validation_matches"] = stats["predicted_matches"]
        rule["validation_n"] = stats["n"]
        rule["accepted"] = rule["training_eligible"] and stats["n"]>=model["policy"]["strong_min_validation"] and stats["predicted_matches"]/stats["n"]>=model["policy"]["strong_validation_match"]
        rule["validation_exceptions"] = [
            {"id":p["source"]["id"],"media_name":p["source"]["media_name"],
             "source":source_baseline(p["source"],rule["role"],rule["column"]),"target":p["target"]["nodes"][rule["role"]][rule["column"]]}
            for p in validation if not equal(
                (rule["value"] if rule["kind"]=="constant" else source_baseline(p["source"],rule["role"],rule["column"])*rule["value"]),
                p["target"]["nodes"][rule["role"]][rule["column"]])]
    covered = metrics["covered_suspension_cars"]
    b,a = metrics["covered_baseline_suspension_relative_error"],metrics["covered_predicted_suspension_relative_error"]
    model["estimated_profile_accepted"] = bool(covered>=model["policy"]["estimate_min_validation_covered"] and
        metrics["covered_suspension_tier_matches"]/covered>=model["policy"]["estimate_validation_tier_match"] and
        a <= b*model["policy"]["estimate_max_relative_error_ratio_vs_baseline"])
    model["validation_summary"] = {k:v for k,v in metrics.items() if k not in ("fields","cars")}
    return {"training":train_metrics,"validation":metrics}


def apply_to_result(result, source_graph, model, mode):
    if mode not in {"conservative","estimated","experimental"}:
        raise c.MappingError("Unknown calibration mode")
    record = {"nodes":{r:n["row"] for r,n in source_graph["nodes"].items()}}
    # A replacement suspension profile must not inherit legacy proposals when
    # its own predictor abstains. Otherwise an abstention silently applies the
    # very rule the new profile is meant to replace.
    updates,notes = propose(record,model,"conservative" if "suspension_v2" in model else mode)
    if "remaining7" in model:
        from remaining import propose as propose_remaining
        remaining_updates, remaining_notes = propose_remaining(record, model["remaining7"], mode)
        updates.extend(remaining_updates)
        notes.extend(remaining_notes)
    if "benchmark_refinements" in model:
        from refinements import propose as propose_refinements
        extra, extra_notes = propose_refinements(record,model["benchmark_refinements"],mode)
        updates.extend(extra)
        notes.extend(extra_notes)
    for key in ("suspension_v2","drivetrain_v2"):
        if key in model:
            if key == "suspension_v2":
                from suspension_v2 import propose as propose_next
            else:
                from drivetrain_v2 import propose as propose_next
            extra, extra_notes = propose_next(record,model[key],mode)
            updates.extend(extra)
            notes.extend(extra_notes)
    seen = set()
    mapped = {}
    # Check the complete proposal before changing any candidate rows.
    for update in updates:
        role,col = update["role"],update["column"]
        key = (role,col)
        if key in seen:
            raise c.MappingError(f"Overlapping calibration proposals for {role}.{col}")
        seen.add(key)
        if role not in result["candidate"]["nodes"] or col not in result["candidate"]["nodes"][role]["row"]:
            raise c.MappingError(f"Calibration references missing column {role}.{col}")
        value = update["value"]
        if not isinstance(value,(int,float)) or not math.isfinite(value):
            raise c.MappingError(f"Nonfinite or nonnumeric calibration for {role}.{col}")
        mapped[key] = c.one([m for m in result["mapping"] if m["role"]==role and m["target_column"]==col],"calibration mapping")
        if not all(k in update for k in ("rule","confidence")):
            raise c.MappingError(f"Calibration proposal lacks provenance for {role}.{col}")
    # Metadata and audit serialization can fail too; resolve them before rows
    # or their mapping provenance are touched.
    required = ("version","heldout_media","estimated_profile_accepted")
    if any(k not in model for k in required):
        raise c.MappingError("Calibration model lacks required metadata")
    if not isinstance(result.get("assumptions"),list):
        raise c.MappingError("Calibration result lacks assumptions list")
    try:
        model_hash = hashlib.sha256(json.dumps(model,sort_keys=True,allow_nan=False).encode()).hexdigest()
    except (ValueError,TypeError) as exc:
        raise c.MappingError("Calibration model is not finite JSON data") from exc
    envelope = {"mode":mode,"rules_version":model["version"],"heldout_media":model["heldout_media"],
                "notes":notes,"estimated_profile_passed_validation":model["estimated_profile_accepted"],
                "rules_sha256":model_hash,"runtime_verified":False,"installable":False,
                "active_suspension_profile":"suspension_v2" if "suspension_v2" in model else "legacy_tier",
                "additional_profiles":[k for k in ("suspension_v2","drivetrain_v2") if k in model],
                "profile_gates":{
                    k:{name:v for name,v in model[k].items() if name in
                       ("accepted","component_accepted","experimental_accepted","conservative_accepted")}
                    for k in ("suspension_v2","drivetrain_v2") if k in model}}
    changes = []
    for update in updates:
        role,col = update["role"],update["column"]
        row = result["candidate"]["nodes"][role]["row"]
        before = row[col]
        row[col] = update["value"]
        changes.append({**update,"baseline_value":before,"changed":not equal(before,update["value"])})
        mapping = mapped[(role,col)]
        mapping["baseline_value"] = before
        mapping["target_value"] = update["value"]
        mapping["action"] = "cross_car_calibration"
        mapping["calibration_rule"] = update["rule"]
        mapping["confidence"] = update["confidence"]
    result["calibration"] = {**envelope,"changes":changes}
    result["assumptions"].append({"rule":"cross_car_calibration","mode":mode,
                                  "estimated_profile_passed_validation":model["estimated_profile_accepted"],
                                  "warning":"Empirical database patterns, not verified solver/unit conversions. Experimental mode may apply explicitly rejected estimates; see per-profile gates and notes."})
    return result


def ambiguity_analysis(data):
    output=[]
    train=[p for p in data["pairs"] if p["split"]=="training"]
    for role,col in fields36():
        groups=defaultdict(list)
        for p in train:
            groups[str(source_baseline(p["source"],role,col))].append(p["target"]["nodes"][role][col])
        ambiguous=[{"source_value":key,"n":len(values),"target_values":dict(Counter(str(v) for v in values))}
                   for key,values in groups.items() if len(set(values))>1]
        ambiguous.sort(key=lambda r:r["n"],reverse=True)
        output.append({"role":role,"column":col,"source_values_with_multiple_targets":len(ambiguous),
                       "examples":ambiguous[:5]})
    return output


def research_report(data, model, evaluation, ambiguity):
    train=evaluation["training"];val=evaluation["validation"]
    covered=val["covered_suspension_cars"];correct=val["covered_suspension_tier_matches"]
    lines=["# Aturan kalibrasi FM3 → FM4: pengujian lintas mobil","",
           "Studi database dasar Disc 1 lokal, konfigurasi stock. Toyota 2000GT dan engine stock-nya dikeluarkan sebelum pembacaan kalibrasi target. Tidak ada game atau instalasi dijalankan.","",
           f"Dari {data['common_ids']} ID bersama, {len(data['pairs'])} pasangan cocok persis pada MediaName, tahun, dan make. "
           f"{data['counts']['training']} mobil dipakai untuk menemukan aturan; {data['counts']['validation']} untuk validasi. "
           "Seluruh mobil dengan engine sumber sama berada pada split yang sama. Lima varian/penamaan yang berbeda dikeluarkan.",
           "",f"Kelompok engine: {len(model['training_engine_ids'])} training dan {len(model['validation_engine_ids'])} validation. "
           "Ini validasi antarkelompok engine; bukan jaminan semua chassis/platform terkait sudah independen.",
           "","## Aturan yang lolos ambang validasi","","| Parameter | Aturan nilai native | Training | Validation | Keputusan |",
           "|---|---|---:|---:|---|"]
    for r in model["strong_rules"]:
        formula=f"FM3 × {r['value']}" if r["kind"]=="scale" else str(r["value"])
        lines.append(f"| {r['id']} | {formula} | {r['training_matches']}/{r['training_n']} | {r['validation_matches']}/{r['validation_n']} | {'diterapkan' if r['accepted'] else 'ditolak'} |")
    lines += ["","Aturan hanya diterapkan pada nilai sumber yang pernah dilihat. Steering angle mempunyai pengecualian; skala 1,2 bukan hukum universal dan bukan konversi satuan. Nilai constant adalah perubahan kalibrasi data FM4.","",
              "## Hipotesis tingkat suspensi","","Jumlah spring depan+belakang FM3 berkelompok pada nilai diskret. Target FM4 juga berkelompok; pemetaan tingkat lama ke tingkat baru sering sama, tetapi tidak selalu. Pemilihan tingkat dipelajari dari modus training dengan minimal 5 mobil dan konsentrasi minimal 80%.",
              "","| Total spring FM3 | Kandidat total FM4 | Dukungan training | Konsentrasi | Layak dicoba |","|---:|---:|---:|---:|---|"]
    for r in model["tier_mappings"]:
        lines.append(f"| {r['source_total_key']} | {r['target_total_key']} | {r['mode_count']}/{r['support']} | {r['concentration']:.1%} | {'ya' if r['eligible'] else 'abstain'} |")
    lines += ["","Di dalam suatu tingkat FM4, spring dan damper dibagi menurut distribusi massa depan/belakang. Total damper dipulihkan dari irisan interval pembulatan 4 desimal pada mobil training. Anti-roll depan/belakang tetap pada nilai tingkat tersebut. Saat diterapkan, distribusi massa berasal dari FM3; batas tune yang terkunci mengikuti default baru, batas tune yang bisa diatur dipertahankan.",
              "",f"Pada validation, prediksi tingkat benar **{correct}/{covered} ({correct/covered:.2%})** untuk {covered} dari {len(val['cars'])} mobil yang tercakup. "
              f"Rata-rata error relatif pada 24 kolom suspensi/anti-roll untuk mobil tercakup turun dari {val['covered_baseline_suspension_relative_error']:.2%} menjadi {val['covered_predicted_suspension_relative_error']:.2%}. "
              "Angka ini error parameter database, bukan error handling.",
              f"Dari mobil tercakup, {val['covered_cars_improved']} membaik dan {val['covered_cars_regressed']} memburuk berdasarkan error relatif gabungan 24 kolom tersebut; hasil per mobil tetap disimpan.",
              "",f"**Keputusan profil otomatis: {'LOLOS' if model['estimated_profile_accepted'] else 'DITOLAK'}.** "
              "Syarat yang dibekukan sebelum validasi adalah minimal 10 mobil tercakup, akurasi tingkat minimal 75%, dan error relatif maksimal 70% dari baseline. "
              "Ambang tidak diturunkan setelah melihat hasil. Mode `estimated` mematuhi penolakan; mode `experimental` hanya menyediakan kandidat penelitian terpisah.",
              "","## Analisis semua 36 kolom","","| Peran / kolom | Sama sebelum, validation | Sama sesudah eksperimen, validation | MAE sebelum | MAE sesudah | Keputusan |",
              "|---|---:|---:|---:|---:|---|"]
    strong={(r["role"],r["column"]) for r in model["strong_rules"] if r["accepted"]}
    for r in val["fields"]:
        decision="pola kuat" if (r["role"],r["column"]) in strong else "eksperimen tingkat; tidak default" if r["role"].startswith(("spring.","antiroll.")) else "tetap sumber; perlu data tambahan"
        lines.append(f"| {r['role']}.{r['column']} | {r['baseline_matches']}/{r['n']} | {r['predicted_matches']}/{r['n']} | {r['baseline_mae']:.6g} | {r['predicted_mae']:.6g} | {decision} |")
    lines += ["","MAE memakai skala native masing-masing kolom; jangan dijumlahkan lintas unit. Untuk TireCompoundID, angka adalah kategori sehingga MAE bukan ukuran jarak fisik. Min/default/max adalah kolom berbeda tetapi bukan bukti independen.",
              "","## Mengapa tujuh kolom lain belum diberi aturan","","- `GasTankSize`: seluruh 236 sumber training bernilai 20, sedangkan FM4 mempunyai 73 nilai berbeda. Faktor universal tidak dapat menjelaskan data ini.",
              "- `TireCompoundID`: satu compound sumber dapat berubah menjadi beberapa compound FM4. Nama atau ID yang sama hanya cukup untuk lookup, bukan untuk memilih kalibrasi ban stock baru.",
              "- Empat friction scale chassis: nilai sumber yang sama sering mempunyai beberapa target; rear source 1 tidak berarti target rear tetap 1. Pembagian lateral/longitudinal tidak menentukan besarnya grip baru.",
              "- `CMHeight`: berubah pada seluruh mobil training. Tidak ada faktor skala tunggal yang dibuktikan; pemetaan satu kolom saja ambigu. Belum dilakukan fit multivariabel atau verifikasi sumbu/unit loader.",
              "","Bukti contoh konflik nilai sumber-ke-target ada di `ambiguity.json`. Menyalin jawaban Toyota FM4 atau menebak faktor universal akan menyembunyikan ketidakpastian ini.",
              "","## Reproduksi dan batas","","`rules_before_validation.json` merekam model/ambang sebelum evaluasi; `rules.json` menambahkan keputusan validasi tanpa mengubah parameter. `evaluation.json` berisi hasil per mobil dan per kolom, termasuk regresi. Semua file cohort dan database hasil tetap lokal.",
              "","Hasil berlaku pada populasi pasangan mobil dengan identitas persis sama di base FM3/FM4 yang dibaca. Tidak membuktikan generalisasi ke mobil FM3 yang hilang dari FM4, DLC/TU, upgrade non-stock, atau runtime. Kandidat Toyota dibandingkan sesudah model dibekukan.",""]
    return "\n".join(lines)


def heldout_report(root, data, model):
    conservative=json.loads((root/"toyota-conservative"/"comparison.json").read_text(encoding="utf-8"))
    experimental=json.loads((root/"toyota-experimental"/"comparison.json").read_text(encoding="utf-8"))
    baseline=json.loads((root/"toyota-conservative"/"baseline_comparison.json").read_text(encoding="utf-8"))
    lookups=[{(r.get("role"),r.get("column")):r for r in comparison["fields"]} for comparison in (baseline,conservative,experimental)]
    lines=["# Toyota 2000GT: hasil kalibrasi lintas mobil","",
           f"Aturan dibentuk dari {data['counts']['training']} mobil lain dan diuji pada {data['counts']['validation']} mobil lain. "
           "Toyota dikeluarkan dari keduanya; parameter aturan dibekukan sebelum dibandingkan dengan Toyota FM4 asli.","",
           "| Kandidat | Kolom fisika berbeda dari Toyota FM4 | Status |","|---|---:|---|",
           f"| Baseline pemetaan format | {baseline['differences_by_category'].get('physics',0)} | Kalibrasi FM3 |",
           f"| Aturan yang lolos validasi | {conservative['differences_by_category'].get('physics',0)} | Lima aturan steering/ABS |",
           f"| Tambahan profil suspensi eksperimental | {experimental['differences_by_category'].get('physics',0)} | Tidak lolos gerbang generalisasi |",
           "","**Hasil Toyota yang cocok tidak mengubah penolakan aturan suspensi untuk pemakaian umum.** "
           f"Pemilihan tingkat hanya benar {model['validation_summary']['covered_suspension_tier_matches']}/{model['validation_summary']['covered_suspension_cars']} pada mobil validasi yang tercakup. "
           "Profil konservatif tetap menjadi pilihan default bila file aturan diberikan.","",
           "## Perbandingan semua 36 kolom","","Nilai berikut native database. Hasil ini tidak menyatakan satuan, gaya, lap time atau handling telah sama.","",
           "| Peran / kolom | Baseline | Konservatif | Eksperimental | FM4 asli |","|---|---:|---:|---:|---:|"]
    for key in fields36():
        a,b,d=[m[key] for m in lookups]
        lines.append(f"| {key[0]}.{key[1]} | {a['candidate']} | {b['candidate']} | {d['candidate']} | {d['fm4_reference']} |")
    lines += ["","## Mengapa profil Toyota ini mendekati FM4","",
              "Total spring FM3 adalah 73,05. Pada training, 8 dari 10 mobil dengan tingkat tersebut berpindah ke total 50,3; dua lainnya memakai 41,8. Ini pemetaan probabilistik, bukan aturan pasti.",
              "","Dengan pilihan eksperimental 50,3 dan distribusi massa sumber 0,51/0,49, spring depan/belakang menjadi 25,653/24,647. "
              "Total bump/rebound dan anti-roll diambil dari pola tingkat 50,3 pada mobil training lain. Pembulatan per axle menghasilkan nilai yang sama dengan Toyota FM4 pada 24 kolom suspensi/anti-roll.",
              "","Tujuh kolom yang belum diselesaikan: CMHeight, TireCompoundID, GasTankSize, serta empat friction scale chassis. Nilai asli FM3 dipertahankan dan selisihnya tetap terlihat.",
              "","## Berkas hasil","",
              "- [Studi aturan dan validasi](REPORT.md)",
              "- [Aturan yang dibekukan](rules.json)",
              "- [Kandidat konservatif](toyota-conservative/candidate_stock.slt) dan [laporan](toyota-conservative/REPORT.md)",
              "- [Kandidat eksperimental](toyota-experimental/candidate_stock.slt) dan [laporan](toyota-experimental/REPORT.md)",
              "","Kedua kandidat tetap database penelitian dengan 46 baris/43 tabel. Belum merupakan DLC siap pasang; engine-braking shape, asset/collision, PI, metadata instalasi, dan runtime masih di luar validasi. Database sumber dibaca saja.",""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out",type=Path,required=True)
    parser.add_argument("--compare-heldout",action="store_true",help="Build conservative and explicitly experimental offline Toyota candidates after model freeze")
    args = parser.parse_args()
    args.out=args.out.resolve()
    if args.out.exists():
        parser.error("Use a new output directory")
    for source_path in (c.FM3_DEFAULT,c.FM4_DEFAULT):
        game_root=source_path.resolve().parent.parent.parent
        if args.out==game_root or game_root in args.out.parents:
            parser.error("Output must be outside the source game directories")
    before={"fm3":c.sha(c.FM3_DEFAULT),"fm4":c.sha(c.FM4_DEFAULT)}
    with closing(c.connect(c.FM3_DEFAULT)) as source, closing(c.connect(c.FM4_DEFAULT)) as target:
        data = collect(source,target)
    args.out.mkdir(parents=True)
    c.dump(args.out/"cohort.json",data)
    summary = exploratory_summary(data)
    c.dump(args.out/"exploration.json",summary)
    model = fit_rules(data)
    c.dump(args.out/"rules_before_validation.json",model)
    evaluation = validate_rules(data,model)
    c.dump(args.out/"rules.json",model)
    c.dump(args.out/"evaluation.json",evaluation)
    ambiguity=ambiguity_analysis(data)
    c.dump(args.out/"ambiguity.json",ambiguity)
    (args.out/"REPORT.md").write_text(research_report(data,model,evaluation,ambiguity),encoding="utf-8")
    predictions={}
    if args.compare_heldout:
        for name,mode in (("toyota-conservative","conservative"),("toyota-experimental","experimental")):
            predictions[mode]=c.run(c.FM3_DEFAULT,c.FM4_DEFAULT,args.out/name,
                                    calibration_rules=args.out/"rules.json",calibration_mode=mode)
        (args.out/"TOYOTA_COMPARISON.md").write_text(heldout_report(args.out,data,model),encoding="utf-8")
    after={"fm3":c.sha(c.FM3_DEFAULT),"fm4":c.sha(c.FM4_DEFAULT)}
    if before!=after:
        raise c.MappingError("Source database changed during calibration study")
    manifest={"source_hashes_before":before,"source_hashes_after":after,"sources_unchanged":True,
              "scope":"FM3 regular USA + FM4 Japan/Asia Disc1 base; no DLC/TU overlay",
              "calibration_code_sha256":c.sha(__file__),"converter_code_sha256":c.sha(c.__file__),
              "rules_before_validation_sha256":c.sha(args.out/"rules_before_validation.json"),
              "rules_after_validation_sha256":c.sha(args.out/"rules.json"),
              "runtime_tested":False,"outputs":{str(p.relative_to(args.out)):c.sha(p) for p in sorted(args.out.rglob("*")) if p.is_file()}}
    c.dump(args.out/"manifest.json",manifest)
    print(json.dumps({"output":str(args.out),"counts":data["counts"],"accepted_strong_rules":len([r for r in model["strong_rules"] if r["accepted"]]),
                      "estimated_profile_accepted":model["estimated_profile_accepted"],"validation":model["validation_summary"],
                      "heldout_results":{k:v["differences"] for k,v in predictions.items()},"sources_unchanged":True},indent=2))


if __name__=="__main__":
    main()
