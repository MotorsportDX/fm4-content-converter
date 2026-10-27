"""Second suspension study: train-only model selection and explicit abstention.

Fixed stock suspension is the only supported inference regime. Race, adjustable,
unknown tiers and source anomalies retain FM3 values. This is database research,
not proof of physical equivalence or a unit conversion.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import copy
import hashlib
import json
import math
from pathlib import Path
import statistics

from . import calibration as cal
from . import converter as c
from . import compatibility
from . import remaining

WEIGHT = "List_UpgradeCarBodyWeight"
FIELDS = [(role, prefix + field)
          for role in ("spring.front", "spring.rear", "antiroll.front", "antiroll.rear")
          for field in (("SwaybarStiffness",) if role.startswith("antiroll")
                        else ("SpringRate", "DampenBumpRate", "DampenReboundRate"))
          for prefix in ("Def", "Min", "Max")]
BASE_FIELDS = [(role, field) for role, col in FIELDS
               if col.startswith("Def") for field in (col[3:],)]


def regime(record):
    n = record["nodes"]
    for role, field in BASE_FIELDS:
        lo, value, hi = (n[role][p + field] for p in ("Min", "Def", "Max"))
        if not all(math.isfinite(x) for x in (lo, value, hi)):
            return "nonfinite"
        if lo > hi or value < lo or value > hi:
            return "source_tuning_anomaly"
    if n["car"]["CarTypeID"] == 3:
        return "race"
    if any(not cal.equal(n[role]["Min" + f], n[role]["Def" + f]) or
           not cal.equal(n[role]["Max" + f], n[role]["Def" + f])
           for role, f in BASE_FIELDS):
        return "adjustable"
    return "fixed"


def spec_flags(pair):
    """Training selection only; these target checks are never inference inputs."""
    a, b = pair["source"]["nodes"], pair["target"]["nodes"]
    audit = compatibility.pair_eligibility(pair["source"], pair["target"])
    flags = [reason["code"] if "code" in reason else str(reason)
             for reason in audit["exclusion_reasons"]]
    flags.extend("missing:" + str(reason) for reason in audit["missing_required_fields"])
    for role, field, threshold in ((WEIGHT, "Mass", .05),):
        if abs(a[role][field] - b[role][field]) > max(abs(a[role][field]), 1) * threshold:
            flags.append(role + "." + field)
    return flags


def features(record):
    n = record["nodes"]
    car, weight, chassis = n["car"], n[WEIGHT], n["List_UpgradeCarBodyChassisStiffness"]
    return {"old_tier": float(cal.tier_key(record)), "year": car["Year"],
            "era": car["Year"] // 10, "car_type": car["CarTypeID"],
            "drive": car["DriveTypeID"], "engine_location": car["EnginePlacementID"],
            "body_type": car["FamilyBodyID"], "compound": n["List_UpgradeTireCompound"]["TireCompoundID"],
            "front_grip": chassis["FrontFrictionScale"], "rear_grip": chassis["RearFrictionScale"],
            "mass": weight["Mass"], "weight_front": weight["CMBackFront"],
            "tire_width": car["FrontTireWidthMM"], "power_mass": car["SimPeakPower"] / weight["Mass"]}


def protocol():
    # Menu/thresholds are written before validation. Do not tune against Toyota.
    specs = []
    for purity in (.80, .90):
        for extra in (None, "drive", "compound", "era", "front_grip", "engine_location"):
            specs.append({"name": "lookup_" + (extra or "tier") + f"_p{purity}",
                          "kind": "lookup", "features": ["old_tier"] + ([extra] if extra else []),
                          "min_leaf": 5, "purity": purity})
        for depth in (2, 3, 4):
            for leaf in (5, 10):
                specs.append({"name": f"tree_d{depth}_n{leaf}_p{purity}", "kind": "tree",
                              "features": ["old_tier", "front_grip", "rear_grip", "year", "car_type",
                                           "drive", "engine_location", "compound", "mass", "weight_front",
                                           "tire_width", "power_mass"],
                              "depth": depth, "min_leaf": leaf, "purity": purity})
    # Added after the first training-CV menu failed, before any validation
    # prediction was evaluated. Gates stay unchanged; study1 is preserved.
    for purity in (.95, 1.0):
        for leaf in (5, 10, 15):
            for extra in (None, "drive", "compound", "era", "front_grip", "engine_location"):
                specs.append({"name": "lookup_" + (extra or "tier") + f"_n{leaf}_p{purity}",
                              "kind": "lookup", "features": ["old_tier"] + ([extra] if extra else []),
                              "min_leaf": leaf, "purity": purity})
            for depth in (2, 3, 4):
                specs.append({"name": f"tree_d{depth}_n{leaf}_p{purity}", "kind": "tree",
                              "features": ["old_tier", "front_grip", "rear_grip", "year", "car_type",
                                           "drive", "engine_location", "compound", "mass", "weight_front",
                                           "tire_width", "power_mass"],
                              "depth": depth, "min_leaf": leaf, "purity": purity})
    component_specs = [
        {"name": "component_" + (extra or "tier") + f"_n{leaf}_step{step}",
         "features": ["old_tier"] + ([extra] if extra else []),
         "min_leaf": leaf, "step": step}
        for extra in (None, "drive", "compound", "era", "front_grip", "engine_location")
        for leaf in (5, 10, 15) for step in (.5, 1.0)]
    return {"version": "suspension-v2.2", "cv_folds": 5,
            "fold_salt": "suspension-v2-engine-cv:",
            "min_profile_cars": 3,
            "min_cv_covered": 30, "min_validation_covered": 10,
            "tier_accuracy_min": .75, "error_ratio_max": .70,
            "regressed_car_fraction_max": .05,
            "selection": "eligible CV: maximum exact fields minus twice regressed fields; then coverage, then menu order",
            "component_selection": "eligible CV: maximize net reduction in relative error over all training cars; then coverage",
            "component_gate": "Separate partial-parameter estimate; no tier predicted. Same coverage/error/regression gates; never passes the rejected tier gate.",
            "source_regime": "fixed only; all 8 Min=Def=Max triplets, CarTypeID != 3",
            "spec_training_exclusion": "config/cylinder/rotary/diesel mismatch, displacement >1%, mass >5%",
            "candidates": specs, "component_candidates": component_specs}


def fold(record, policy):
    return int(hashlib.sha256((policy["fold_salt"] + str(record["engine_id"])).encode()).hexdigest()[:8], 16) % policy["cv_folds"]


def _key(f, names):
    return "|".join(format(f[name], ".8g") for name in names)


def _fit_one(pairs, spec, policy):
    eligible = [p for p in pairs if not spec_flags(p) and regime(p["source"]) == "fixed"
                and regime(p["target"]) == "fixed"]
    model = {"spec": copy.deepcopy(spec), "n": len(eligible),
             "source_tiers": sorted({cal.tier_key(p["source"]) for p in eligible}),
             "profiles": {}, "excluded": [
                 {"id": p["source"]["id"], "spec_flags": spec_flags(p),
                  "source_regime": regime(p["source"]), "target_regime": regime(p["target"])}
                 for p in pairs if p not in eligible]}
    target_groups = defaultdict(list)
    for p in eligible:
        target_groups[cal.tier_key(p["target"])].append(p["target"])
    for key, recs in target_groups.items():
        if len(recs) < policy["min_profile_cars"]:
            continue
        totals = {field: cal.quantized_total(recs, "spring", "Def" + field)
                  for field in ("SpringRate", "DampenBumpRate", "DampenReboundRate")}
        bars = {axle: statistics.median(r["nodes"]["antiroll." + axle]["DefSwaybarStiffness"]
                                       for r in recs) for axle in ("front", "rear")}
        consistent = all(t["interval_consistent"] for t in totals.values()) and all(
            cal.equal(r["nodes"]["antiroll." + axle]["DefSwaybarStiffness"], bars[axle])
            for r in recs for axle in bars)
        model["profiles"][key] = {"support": len(recs), "totals": totals,
                                  "antiroll": bars, "consistent": consistent}
    if not eligible:
        return model
    xs = [features(p["source"]) for p in eligible]
    ys = [float(cal.tier_key(p["target"])) for p in eligible]
    model["domain"] = {name: {"min": min(f[name] for f in xs), "max": max(f[name] for f in xs),
                               "seen": sorted({f[name] for f in xs})}
                       for name in spec["features"]}
    if spec["kind"] == "tree":
        model["tree"] = remaining.tree_fit(xs, ys, spec, "compound")
    else:
        groups = defaultdict(list)
        for x, y in zip(xs, ys):
            groups[_key(x, spec["features"])].append(y)
        model["lookup"] = {}
        for key, values in groups.items():
            counts = Counter(values)
            chosen = sorted(counts, key=lambda v: (-counts[v], v))[0]
            model["lookup"][key] = {"value": chosen, "n": len(values), "distribution": dict(counts)}
    return model


def _predict(record, fitted):
    state = regime(record)
    if state != "fixed":
        return None, "abstain_" + state
    if cal.tier_key(record) not in fitted["source_tiers"]:
        return None, "abstain_unknown_source_tier"
    f, spec = features(record), fitted["spec"]
    for key, domain in fitted.get("domain", {}).items():
        if f[key] < domain["min"] or f[key] > domain["max"]:
            return None, "abstain_out_of_training_domain"
        if key in ("drive", "compound", "engine_location", "car_type") and f[key] not in domain["seen"]:
            return None, "abstain_unknown_category"
    if spec["kind"] == "lookup":
        leaf = fitted.get("lookup", {}).get(_key(f, spec["features"]))
    else:
        leaf = fitted.get("tree")
        while leaf and "feature" in leaf:
            value = f[leaf["feature"]]
            left = value == leaf["threshold"] if leaf["categorical"] else value <= leaf["threshold"]
            leaf = leaf["left"] if left else leaf["right"]
    if not leaf:
        return None, "abstain_unseen_group"
    counts = list(leaf["distribution"].values())
    purity = max(counts) / leaf["n"]
    if leaf["n"] < spec["min_leaf"] or purity < spec["purity"]:
        return None, "abstain_ambiguous_tier"
    key = format(leaf["value"], ".2f")
    profile = fitted["profiles"].get(key)
    if not profile or not profile["consistent"]:
        return None, "abstain_unsupported_profile"
    return {"tier": key, "profile": profile, "purity": purity, "support": leaf["n"]}, None


def _updates(record, fitted):
    prediction, reason = _predict(record, fitted)
    if prediction is None:
        return [], [{"rule": "suspension_v2", "status": reason}]
    front = record["nodes"][WEIGHT]["CMBackFront"]
    if not 0 < front < 1:
        return [], [{"rule": "suspension_v2", "status": "abstain_invalid_weight_distribution"}]
    changes = []
    for role, field in BASE_FIELDS:
        axle = role.split(".")[1]
        profile = prediction["profile"]
        value = (profile["antiroll"][axle] if field == "SwaybarStiffness"
                 else profile["totals"][field]["value"] * (front if axle == "front" else 1 - front))
        value = round(value, 4)
        for prefix in ("Def", "Min", "Max"):
            col = prefix + field
            changes.append({"role": role, "column": col, "value": value,
                            "input_value": record["nodes"][role][col], "rule": "suspension_v2",
                            "confidence": "experimental_fixed_profile",
                            "target_tier": prediction["tier"], "source_tier": cal.tier_key(record),
                            "training_support": prediction["support"], "training_purity": prediction["purity"]})
    return changes, []


def _fit_components(pairs, spec):
    groups = defaultdict(list)
    excluded = []
    for pair in pairs:
        if spec_flags(pair) or regime(pair["source"]) != "fixed" or regime(pair["target"]) != "fixed":
            excluded.append({"id": pair["source"]["id"], "spec_flags": spec_flags(pair),
                             "source_regime": regime(pair["source"]), "target_regime": regime(pair["target"])})
            continue
        groups[_key(features(pair["source"]), spec["features"])].append(pair)
    fitted = {"spec": copy.deepcopy(spec), "groups": {}, "excluded": excluded}
    for key, pairs in groups.items():
        if len(pairs) < spec["min_leaf"]:
            continue
        rules = []
        for role, field in BASE_FIELDS:
            col = "Def" + field
            if any(p["source"]["nodes"][role][col] <= 0 for p in pairs):
                continue
            ratios = [p["target"]["nodes"][role][col] / p["source"]["nodes"][role][col] for p in pairs]
            low, high = min(ratios), max(ratios)
            # Move only in the direction shared by every fitting observation.
            # Closest ratio to identity is conservative relative to TRAINING
            # bounds only, not a guaranteed bound for an unseen car.
            ratio = high if high < 1 else low if low > 1 else 1
            ratio = 1 + spec["step"] * (ratio - 1)
            if abs(ratio - 1) <= 1e-6:
                continue
            rules.append({"role": role, "field": field, "ratio": ratio,
                          "training_ratio_min": low, "training_ratio_max": high,
                          "source_value_min": min(p["source"]["nodes"][role][col] for p in pairs),
                          "source_value_max": max(p["source"]["nodes"][role][col] for p in pairs)})
        fitted["groups"][key] = {"support": len(pairs), "rules": rules}
    return fitted


def _component_updates(record, fitted):
    state = regime(record)
    if state != "fixed":
        return [], [{"rule": "suspension_component_v2", "status": "abstain_" + state}]
    group = fitted["groups"].get(_key(features(record), fitted["spec"]["features"]))
    if not group or not group["rules"]:
        return [], [{"rule": "suspension_component_v2", "status": "abstain_unsupported_or_mixed_direction_group"}]
    updates = []
    for rule in group["rules"]:
        role, field = rule["role"], rule["field"]
        old = record["nodes"][role]["Def" + field]
        if not rule["source_value_min"] <= old <= rule["source_value_max"]:
            continue
        value = round(old * rule["ratio"], 4)
        if cal.equal(old, value):
            continue
        for prefix in ("Def", "Min", "Max"):
            col = prefix + field
            updates.append({"role": role, "column": col, "value": value,
                            "input_value": record["nodes"][role][col],
                            "rule": "suspension_component_v2",
                            "confidence": "experimental_partial_estimate_not_tier_conversion",
                            "training_support": group["support"],
                            "ratio": rule["ratio"],
                            "training_ratio_interval": [rule["training_ratio_min"], rule["training_ratio_max"]]})
    return updates, ([] if updates else [{"rule": "suspension_component_v2",
                                         "status": "abstain_component_source_out_of_domain"}])


def metrics(pairs, fitted, component=False):
    records = []
    for pair in pairs:
        updates, notes = (_component_updates if component else _updates)(pair["source"], fitted)
        values = {(u["role"], u["column"]): u["value"] for u in updates}
        b, a = [], []
        exact_before = exact_after = regressions = improvements = 0
        for role, col in FIELDS:
            source, target = pair["source"]["nodes"][role][col], pair["target"]["nodes"][role][col]
            predicted = values.get((role, col), source)
            before, after = abs(source - target), abs(predicted - target)
            exact_before += cal.equal(source, target)
            exact_after += cal.equal(predicted, target)
            regressions += after > before + 1e-6
            improvements += after + 1e-6 < before
            b.append(before / max(abs(target), 1e-6))
            a.append(after / max(abs(target), 1e-6))
        records.append({"id": pair["source"]["id"], "media_name": pair["source"]["media_name"],
                        "engine_id": pair["source"]["engine_id"], "covered": bool(updates),
                        "source_regime": regime(pair["source"]), "spec_flags": spec_flags(pair),
                        "target_tier": cal.tier_key(pair["target"]),
                        "predicted_tier": updates[0].get("target_tier") if updates else None,
                        "baseline_relative_error": statistics.mean(b),
                        "predicted_relative_error": statistics.mean(a),
                        "baseline_exact": exact_before, "predicted_exact": exact_after,
                        "field_regressions": regressions, "field_improvements": improvements,
                        "notes": notes})
    return summarize(records)


def summarize(records):
    covered = [r for r in records if r["covered"]]
    b = statistics.mean(r["baseline_relative_error"] for r in covered) if covered else 0
    a = statistics.mean(r["predicted_relative_error"] for r in covered) if covered else 0
    result = {"n": len(records), "covered": len(covered),
              "tier_matches": sum(r["target_tier"] == r["predicted_tier"] for r in covered),
              "baseline_exact": sum(r["baseline_exact"] for r in records),
              "predicted_exact": sum(r["predicted_exact"] for r in records),
              "field_regressions": sum(r["field_regressions"] for r in records),
              "field_improvements": sum(r["field_improvements"] for r in records),
              "regressed_cars": sum(r["field_regressions"] > 0 for r in covered),
              "covered_baseline_relative_error": b, "covered_predicted_relative_error": a,
              "error_ratio": a / b if b else (0 if a == 0 else None), "cars": records}
    result["tier_accuracy"] = result["tier_matches"] / len(covered) if covered else None
    result["regressed_car_fraction"] = result["regressed_cars"] / len(covered) if covered else None
    return result


def passes(stats, policy, phase, component=False):
    return bool(stats["covered"] >= policy["min_" + phase + "_covered"]
                and (component or stats["tier_accuracy"] >= policy["tier_accuracy_min"])
                and stats["error_ratio"] is not None and stats["error_ratio"] <= policy["error_ratio_max"]
                and stats["regressed_car_fraction"] <= policy["regressed_car_fraction_max"])


def fit(data):
    train = [p for p in data["pairs"] if p["split"] == "training"]
    policy = protocol()
    model = {"version": policy["version"], "policy": policy,
             "training_ids": [p["source"]["id"] for p in train],
             "training_engine_ids": sorted({p["source"]["engine_id"] for p in train}),
             "cv_groups": {str(p["source"]["engine_id"]): fold(p["source"], policy) for p in train},
             "provenance": "Original training only; adaptive follow-up to old benchmark; 73 validation reused.",
             "replace_legacy_suspension": True, "candidates": [], "accepted": False,
             "experimental_eligible": False}
    winner, winner_score = None, None
    for spec in policy["candidates"]:
        records = []
        for held in range(policy["cv_folds"]):
            fitting = [p for p in train if fold(p["source"], policy) != held]
            evaluation = [p for p in train if fold(p["source"], policy) == held]
            candidate = _fit_one(fitting, spec, policy)
            records.extend(metrics(evaluation, candidate)["cars"])
        stats = summarize(records)
        eligible = passes(stats, policy, "cv")
        entry = {"spec": spec, "cv": stats, "eligible": eligible}
        model["candidates"].append(entry)
        score = (stats["predicted_exact"] - stats["baseline_exact"] - 2 * stats["field_regressions"],
                 stats["covered"])
        if eligible and (winner_score is None or score > winner_score):
            winner, winner_score = spec, score
    if winner is not None:
        model["selected"] = _fit_one(train, winner, policy)
        model["selected_cv"] = next(e["cv"] for e in model["candidates"] if e["spec"] == winner)
        model["experimental_eligible"] = True
    else:
        model["selected"] = None
        model["selection_note"] = "All candidates failed frozen training-CV gates; legacy suspension suppressed."
    component_winner = component_score = None
    model["component_candidates"] = []
    for spec in policy["component_candidates"]:
        records = []
        for held in range(policy["cv_folds"]):
            fitting = [p for p in train if fold(p["source"], policy) != held]
            evaluation = [p for p in train if fold(p["source"], policy) == held]
            candidate = _fit_components(fitting, spec)
            records.extend(metrics(evaluation, candidate, component=True)["cars"])
        stats = summarize(records)
        eligible = passes(stats, policy, "cv", component=True)
        model["component_candidates"].append({"spec": spec, "cv": stats, "eligible": eligible})
        score = (sum(r["baseline_relative_error"] - r["predicted_relative_error"] for r in records),
                 stats["covered"])
        if eligible and (component_score is None or score > component_score):
            component_winner, component_score = spec, score
    model["component_selected"] = _fit_components(train, component_winner) if component_winner else None
    model["component_accepted"] = False
    if component_winner:
        model["component_selected_cv"] = next(e["cv"] for e in model["component_candidates"]
                                               if e["spec"] == component_winner)
    return model


def validate(data, model):
    validation = [p for p in data["pairs"] if p["split"] == "validation"]
    # This adds decisions/evaluation; it cannot select or refit a model.
    if model["selected"] is None:
        model["validation"] = {"n": len(validation), "covered": 0,
                               "reason": "No training-CV candidate eligible"}
        model["accepted"] = False
    else:
        model["validation"] = metrics(validation, model["selected"])
        model["accepted"] = passes(model["validation"], model["policy"], "validation")
    if model["component_selected"] is None:
        model["component_validation"] = {"n": len(validation), "covered": 0,
                                         "reason": "No component estimate passed training-CV gates"}
    else:
        model["component_validation"] = metrics(validation, model["component_selected"], component=True)
        model["component_accepted"] = passes(model["component_validation"], model["policy"],
                                              "validation", component=True)
    return model


def propose(record, model, mode):
    if mode not in ("conservative", "estimated", "experimental"):
        raise c.MappingError("Unknown suspension mode")
    # An estimated model is never promoted to conservative exact calibration.
    if mode == "conservative":
        return [], []
    try:
        inputs = features(record)
        if any(not isinstance(v, (int, float)) or not math.isfinite(v) for v in inputs.values()):
            raise ValueError("Nonfinite input")
        if record["nodes"][WEIGHT]["Mass"] <= 0:
            raise ValueError("Nonpositive mass")
        state = regime(record)
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        return [], [{"rule": "suspension_v2", "status": "abstain_malformed_or_missing_source_data"}]
    if state != "fixed":
        return [], [{"rule": "suspension_v2", "status": "abstain_" + state}]
    if model["selected"] is None:
        component = model.get("component_selected")
        if component is None:
            return [], [{"rule": "suspension_v2", "status": "abstain_no_candidate_passed_training_cv"}]
        if mode == "estimated" and not model.get("component_accepted"):
            return [], [{"rule": "suspension_component_v2", "status": "abstain_failed_validation_gate"}]
        updates, notes = _component_updates(record, component)
        if not model.get("component_accepted"):
            notes.append({"rule": "suspension_component_v2", "status": "EXPERIMENT_ONLY_validation_gate_failed",
                          "installable": False})
        return updates, notes
    if mode == "estimated" and not model.get("accepted"):
        return [], [{"rule": "suspension_v2", "status": "abstain_failed_validation_gate"}]
    changes, notes = _updates(record, model["selected"])
    if not model.get("accepted"):
        notes.append({"rule": "suspension_v2", "status": "EXPERIMENT_ONLY_validation_gate_failed",
                      "installable": False})
    return changes, notes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohort", type=Path, default=Path("outputs/fm-car-converter/calibration-v2/cohort.json"))
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    if out.exists():
        parser.error("Use a new output directory")
    for path in (c.FM3_DEFAULT, c.FM4_DEFAULT):
        root = path.resolve().parent.parent.parent
        if out == root or root in out.parents:
            parser.error("Output must be outside game directories")
    out.mkdir(parents=True)
    c.dump(out / "protocol.json", protocol())
    data = json.loads(args.cohort.read_text(encoding="utf-8"))
    model = fit(data)
    c.dump(out / "rules_before_validation.json", model)
    validate(data, model)
    c.dump(out / "rules.json", model)
    lines = ["# Studi suspensi kedua", "",
             "236 training asli; cross-validation lima fold dikelompokkan menurut source engine. "
             "Toyota dikeluarkan. Pemilihan kandidat tidak memakai 73 validation; validation tersebut "
             "sudah digunakan dalam studi sebelumnya. Menu dan gerbang dibekukan sebelum evaluasi.",
             "", "Suspensi race, adjustable, source anomaly dan tier tidak dikenal dipertahankan. "
             "Pasangan training yang berbeda spesifikasi mesin/massa dikeluarkan dari fitting dan "
             "tetap ditampilkan pada evaluasi. Profil dipelajari hanya dari target fixed training.",
             "", "| Kandidat | CV tercakup | Tier benar | Kolom memburuk | Mobil memburuk | Lolos CV |",
             "|---|---:|---:|---:|---:|---|"]
    for item in model["candidates"]:
        s = item["cv"]
        lines.append(f"| {item['spec']['name']} | {s['covered']} | {s['tier_matches']} | "
                     f"{s['field_regressions']} | {s['regressed_cars']} | {item['eligible']} |")
    lines += ["", "## Alternatif perubahan sebagian komponen", "",
              "Setelah semua kandidat tier gagal pada CV training, diuji metode terpisah: "
              "kelompok source tier + kategori sumber; suatu komponen hanya digeser jika seluruh "
              "rasio target/source training berada pada sisi yang sama terhadap 1. Rasio terdekat "
              "ke 1 membatasi perubahan; batas ini hanya berlaku pada observasi training. "
              "Menu alternatif dibekukan sebelum validation. Ini tidak memilih tier FM4 dan "
              "tidak meloloskan gerbang tier yang gagal.", "",
              "| Kandidat komponen | CV tercakup | Error/baseline | Mobil memburuk | Lolos CV |",
              "|---|---:|---:|---:|---|"]
    for item in model["component_candidates"]:
        s = item["cv"]
        lines.append(f"| {item['spec']['name']} | {s['covered']} | {s['error_ratio']:.4f} | "
                     f"{s['regressed_cars']} | {item['eligible']} |")
    lines += ["", "Gerbang: minimal 30 mobil CV/10 validation tercakup; akurasi tier >=75%; "
              "error relatif <=70% baseline; mobil dengan kolom memburuk <=5% dari cakupan. "
              "Dua gerbang akurasi/error lama dipertahankan, dengan pembatasan regresi tambahan.",
              "", f"Kandidat terpilih: `{model['selected']['spec']['name'] if model['selected'] else None}`.",
              f"Lolos validation: `{model['accepted']}`. Conservative tetap tidak menerapkan prediksi suspensi.",
              f"Estimasi sebagian komponen: `{model['component_selected']['spec']['name'] if model['component_selected'] else None}`; "
              f"lolos validation: `{model['component_accepted']}`.",
              "",
              "Gerbang estimasi sebagian komponen memakai syarat cakupan/error/regresi yang sama; "
              "tidak mempunyai prediksi tier sehingga akurasi tier tidak berlaku dan tidak diklaim. "
              "Tidak satu pun mode ini mengubah ride height, camber, toe atau batas adjustable.",
              "", "Model ini menggantikan aturan suspensi lama, bukan menambahkannya. "
              "Abstain berarti mempertahankan sumber; tidak kembali ke aturan lama yang ditolak.",
              "", "Rincian seluruh mobil dan sumber regresi tersedia dalam rules.json. "
              "Semua 73 validation tetap dilaporkan, termasuk spec mismatch. Pemisahan engine "
              "tidak menjamin platform/chassis atau trim terkait independen. Rasio empiris terdekat "
              "ke 1 bukan batas fisik yang dijamin untuk mobil baru. Batas 4 desimal hanya hipotesis "
              "pembulatan data. Tidak ada database game yang ditulis; pengujian runtime belum dilakukan.", ""]
    if model["component_selected"]:
        stats = model["component_validation"]
        lines += ["## Validation estimasi komponen", "",
                  f"- Cakupan: {stats['covered']}/{stats['n']}; {stats['field_improvements']} kolom membaik, "
                  f"{stats['field_regressions']} kolom memburuk dari baseline.",
                  f"- {stats['regressed_cars']}/{stats['covered']} mobil memiliki sedikitnya satu kolom "
                  f"memburuk ({stats['regressed_car_fraction']:.2%}); batas tetap 5%.",
                  f"- Error relatif rerata: {stats['covered_baseline_relative_error']:.6f} → "
                  f"{stats['covered_predicted_relative_error']:.6f}; rasio {stats['error_ratio']:.6f}.",
                  "- Komponen yang tidak memperoleh bukti satu arah tetap memakai nilai sumber.", ""]
    (out / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    c.dump(out / "manifest.json", {"cohort_sha256": c.sha(args.cohort), "code_sha256": c.sha(__file__),
                                  "outputs": {p.name: c.sha(p) for p in out.iterdir() if p.is_file()}})
    print(json.dumps({"selected": model["selected"]["spec"] if model["selected"] else None,
                      "validation": {k: v for k, v in model["validation"].items() if k != "cars"},
                      "accepted": model["accepted"],
                      "component_selected": model["component_selected"]["spec"] if model["component_selected"] else None,
                      "component_validation": {k: v for k, v in model["component_validation"].items() if k != "cars"},
                      "component_accepted": model["component_accepted"]}, indent=2))


if __name__ == "__main__":
    main()
