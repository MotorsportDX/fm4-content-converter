"""Guarded drivetrain research; all source databases are opened read-only.

Fit uses training pairs only, including its group cross-validation. Validation
adds acceptance decisions without changing candidate parameters. Inference
uses only the source record and the frozen model, never an FM4 car lookup.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from contextlib import closing
import copy
import json
import math
from pathlib import Path
import re
import statistics

from . import calibration as cal
from . import converter as c

TRANS = "List_UpgradeDrivetrainTransmission"
INERTIA = (TRANS, "MomentInertia")
POLICY = {
    "cv_folds": 5,
    "minimum_scope_training": 12,
    "minimum_scope_validation": 4,
    "maximum_mae_ratio": 0.70,
    "maximum_regressions": 0,
    "minimum_scope_training_families": 5,
    "minimum_scope_validation_families": 3,
    "minimum_conservative_training": 30,
    "minimum_conservative_validation": 10,
    "minimum_conservative_match_fraction": 0.98,
    "pair_displacement_relative_tolerance": 0.02,
    "pair_mass_relative_tolerance": 0.05,
}


def augment(data, source_path=c.FM3_DEFAULT, target_path=c.FM4_DEFAULT):
    """Add full drivetrain/aero rows to already paired, Toyota-excluded data."""
    result = copy.deepcopy(data)
    with closing(c.connect(source_path)) as src, closing(c.connect(target_path)) as dst:
        for pair in result["pairs"]:
            for side, db in (("source", src), ("target", dst)):
                graph = c.extract_stock(db, pair[side]["media_name"])
                for role, node in graph["nodes"].items():
                    if role == "drivetrain" or role.startswith(("List_UpgradeDrivetrain", "aero.")):
                        pair[side]["nodes"][role] = node["row"]
    return result


def collect(source_path=c.FM3_DEFAULT, target_path=c.FM4_DEFAULT):
    with closing(c.connect(source_path)) as src, closing(c.connect(target_path)) as dst:
        data = cal.collect(src, dst)
    return augment(data, source_path, target_path)


def parity(pair):
    """Exclude known mismatched specifications from fitting, retain in evaluation."""
    s, t = pair["source"]["nodes"], pair["target"]["nodes"]
    reasons = []
    for role, fields in (("car", ("EngineConfigID", "CylinderID", "DriveTypeID")),
                         ("engine", ("ConfigID", "CylinderID", "Rotary", "Diesel"))):
        for field in fields:
            if s[role].get(field) != t[role].get(field):
                reasons.append(role+"."+field)
    for role, field, tolerance in (
        ("car", "Displacement", POLICY["pair_displacement_relative_tolerance"]),
        ("List_UpgradeCarBodyWeight", "Mass", POLICY["pair_mass_relative_tolerance"]),
    ):
        a, b = s[role][field], t[role][field]
        if abs(a-b)/max(abs(a), abs(b), 1e-12) > tolerance:
            reasons.append(role+"."+field)
    return reasons


def features(record):
    nodes = record["nodes"]
    car, transmission = nodes["car"], nodes[TRANS]
    result = {
        "old": transmission["MomentInertia"],
        "mass": nodes["List_UpgradeCarBodyWeight"]["Mass"],
        "engine_inertia": nodes["engine"]["MomentInertia"],
        "clutch_torque": nodes["List_UpgradeDrivetrainClutch"]["ClutchMaxTorque"],
        "drive": car["DriveTypeID"], "car_type": car["CarTypeID"],
        "year": car["Year"], "level": transmission["Level"],
        "gears": transmission["NumGears"],
        "shift_time": transmission["GearShiftTime"],
    }
    if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in result.values()):
        raise c.MappingError("Non-finite drivetrain feature")
    return result


def fold_groups(pairs):
    """Union engine IDs, identical physics and model families to reduce leakage."""
    parents = list(range(len(pairs)))

    def find(i):
        while parents[i] != i:
            parents[i] = parents[parents[i]]
            i = parents[i]
        return i

    def union(i, j):
        parents[find(j)] = find(i)

    by_id, by_payload, by_family = {}, {}, {}
    for i, pair in enumerate(pairs):
        source = pair["source"]
        engine = source["nodes"]["engine"]
        payload = {k:v for k,v in engine.items()
                   if k not in {"EngineID", "MediaName", "EngineName"}}
        key = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        for group, value in ((by_id, source["engine_id"]), (by_payload, key),
                             (by_family, family_key(source["media_name"]))):
            if value in group:
                union(i, group[value])
            else:
                group[value] = i
    components = defaultdict(list)
    for i in range(len(pairs)):
        components[find(i)].append(i)
    folds, counts = [None]*len(pairs), [0]*POLICY["cv_folds"]
    # Stable balancing does not use target values or target groups.
    for members in sorted(components.values(), key=lambda xs: (-len(xs), min(
            pairs[i]["source"]["engine_id"] for i in xs))):
        fold = min(range(len(counts)), key=lambda f: (counts[f], f))
        counts[fold] += len(members)
        for i in members:
            folds[i] = fold
    return folds, {"components":len(components), "fold_sizes":counts,
                   "largest_component":max(map(len, components.values()), default=0),
                   "rule":"Same source engine ID, identical source engine physics, or normalized source model family never cross folds. Names are grouping-only, not predictors."}


def family_key(name):
    return "_".join(token for token in name.split("_") if not re.fullmatch(r"\d+", token))


def specs():
    menu = [{"name":"identity", "kind":"identity", "scope":{}}]
    for scope_name, scope in (
        ("all", {}), ("road", {"car_type":1}), ("race", {"car_type":3}),
        ("race_2000plus", {"car_type":3, "level":3, "min_year":2000}),
        ("race_2005plus", {"car_type":3, "level":3, "min_year":2005}),
        ("race_2007plus", {"car_type":3, "level":3, "min_year":2007}),
        ("race_2008plus", {"car_type":3, "level":3, "min_year":2008}),
        ("race_2009plus", {"car_type":3, "level":3, "min_year":2009}),
        ("fwd", {"drive":1}), ("rwd", {"drive":2}), ("awd", {"drive":3}),
    ):
        menu.append({"name":scope_name+"_offset", "kind":"offset", "scope":scope})
    for names in (
        ["old"], ["old", "mass"], ["old", "engine_inertia", "clutch_torque"],
        ["old", "mass", "engine_inertia", "clutch_torque", "level", "drive", "gears"],
    ):
        menu.append({"name":"linear_"+"_".join(names), "kind":"linear",
                     "scope":{}, "features":names, "ridge":1.0})
    return menu


def in_scope(f, scope):
    return all(f["year"] >= value if key == "min_year" else f[key] == value
               for key, value in scope.items())


def solve(matrix, rhs):
    """Small pivoted linear system; predictors are standardized before this call."""
    a = [list(row)+[value] for row, value in zip(matrix, rhs)]
    for i in range(len(a)):
        pivot = max(range(i, len(a)), key=lambda j: abs(a[j][i]))
        a[i], a[pivot] = a[pivot], a[i]
        if abs(a[i][i]) < 1e-12:
            raise c.MappingError("Singular drivetrain regression")
        a[i] = [v/a[i][i] for v in a[i]]
        for j in range(len(a)):
            if j != i:
                factor = a[j][i]
                a[j] = [x-factor*y for x,y in zip(a[j], a[i])]
    return [row[-1] for row in a]


def fit_one(pairs, spec):
    selected = [p for p in pairs if in_scope(features(p["source"]), spec["scope"])]
    model = copy.deepcopy(spec)
    model.update(n=len(selected), disabled=len(selected) < 5)
    if spec["kind"] == "identity":
        model["disabled"] = False
        return model
    if model["disabled"]:
        return model
    xs = [features(p["source"]) for p in selected]
    ys = [p["target"]["nodes"][TRANS]["MomentInertia"]-x["old"]
          for p,x in zip(selected, xs)]
    # Domain is part of the frozen source-side rule.
    model["domain"] = {key: [min(x[key] for x in xs), max(x[key] for x in xs)]
                       for key in ("old", "year")}
    if spec["kind"] == "offset":
        model["offset"] = round(statistics.median(ys), 4)
    elif spec["kind"] == "linear":
        names = spec["features"]
        means = [statistics.mean(x[k] for x in xs) for k in names]
        scales = [statistics.pstdev(x[k] for x in xs) or 1 for k in names]
        design = [[1]+[(x[k]-m)/s for k,m,s in zip(names, means, scales)] for x in xs]
        size = len(names)+1
        gram = [[sum(row[i]*row[j] for row in design)+(spec["ridge"] if i == j and i else 0)
                 for j in range(size)] for i in range(size)]
        beta = solve(gram, [sum(row[i]*y for row,y in zip(design, ys)) for i in range(size)])
        model["intercept"] = beta[0]-sum(b*m/s for b,m,s in zip(beta[1:], means, scales))
        model["coefficients"] = {k:b/s for k,b,s in zip(names, beta[1:], scales)}
    return model


def predict(record, model):
    f = features(record)
    if model["kind"] == "identity":
        return f["old"], "identity"
    if model["disabled"]:
        return f["old"], "insufficient_training_scope"
    if not in_scope(f, model["scope"]):
        return f["old"], "outside_source_scope"
    for key, (low, high) in model["domain"].items():
        if f[key] < low or f[key] > high:
            return f["old"], "outside_training_domain"
    delta = (model["offset"] if model["kind"] == "offset" else
             model["intercept"]+sum(f[k]*v for k,v in model["coefficients"].items()))
    value = round(f["old"]+delta, 4)
    if value <= 0:
        return f["old"], "invalid_inertia"
    return value, "predicted"


def score(rows):
    n = len(rows)
    changed = [r for r in rows if not cal.equal(r["baseline"], r["predicted"])]
    subset = [r for r in rows if r["prediction_status"] == "predicted"]
    def mean(values):
        values = list(values)
        return statistics.mean(values) if values else 0.0
    base = mean(r["baseline_error"] for r in rows)
    after = mean(r["predicted_error"] for r in rows)
    scope_base = mean(r["baseline_error"] for r in subset)
    scope_after = mean(r["predicted_error"] for r in subset)
    return {
        "n":n, "changed":len(changed), "scope_predicted":len(subset),
        "baseline_mae":base, "predicted_mae":after,
        "mae_ratio":after/base if base else (0 if after == 0 else None),
        "scope_baseline_mae":scope_base, "scope_predicted_mae":scope_after,
        "scope_mae_ratio":scope_after/scope_base if scope_base else (0 if scope_after == 0 else None),
        "scope_families":len({family_key(r["media_name"]) for r in subset}),
        "baseline_matches":sum(cal.equal(r["baseline"],r["native"]) for r in rows),
        "predicted_matches":sum(cal.equal(r["predicted"],r["native"]) for r in rows),
        "scope_match_fraction":mean(cal.equal(r["predicted"],r["native"]) for r in subset),
        "improved":sum(r["result"] == "improved" for r in rows),
        "regressed":sum(r["result"] == "regressed" for r in rows),
        "unchanged":sum(r["result"] == "unchanged" for r in rows),
    }


def evaluate(pairs, model, folds=None):
    rows = []
    for i, pair in enumerate(pairs):
        s = pair["source"]
        baseline = s["nodes"][TRANS]["MomentInertia"]
        predicted, why = predict(s, model[i] if isinstance(model, list) else model)
        actual = pair["target"]["nodes"][TRANS]["MomentInertia"]
        before, after = abs(baseline-actual), abs(predicted-actual)
        row = {"media_name":s["media_name"], "source_engine_id":s["engine_id"],
               "baseline":baseline, "predicted":predicted, "native":actual,
               "baseline_error":before, "predicted_error":after,
               "result":"improved" if after < before-1e-6 else
                        "regressed" if after > before+1e-6 else "unchanged",
               "prediction_status":why, "specification_mismatches":parity(pair)}
        if folds is not None:
            row["fold"] = folds[i]
        rows.append(row)
    return {"summary":score(rows), "cars":rows}


def gate(summary, minimum, policy=POLICY, minimum_families=1):
    return (summary["scope_predicted"] >= minimum and summary["changed"] >= minimum and
            summary["scope_families"] >= minimum_families and
            summary["scope_mae_ratio"] is not None and summary["scope_mae_ratio"] <= policy["maximum_mae_ratio"] and
            summary["regressed"] <= policy["maximum_regressions"] and
            summary["predicted_matches"] >= summary["baseline_matches"])


def fit(data):
    """Select by source-group CV among a fixed, transparent menu; no validation reads."""
    original = [p for p in data["pairs"] if p["split"] == "training"]
    pairs = [p for p in original if not parity(p)]
    excluded = [{"media_name":p["source"]["media_name"], "reasons":parity(p)}
                for p in original if parity(p)]
    folds, grouping = fold_groups(pairs)
    trials = []
    for spec in specs():
        models = {fold:fit_one([p for i,p in enumerate(pairs) if folds[i] != fold], spec)
                  for fold in range(POLICY["cv_folds"])}
        result = evaluate(pairs, [models[f] for f in folds], folds)
        result.update(name=spec["name"], spec=spec)
        trials.append(result)
    ranking = lambda item: (
        item["summary"]["predicted_mae"], item["summary"]["regressed"],
        len(item["spec"].get("features", [])), item["name"])
    unrestricted = min(trials, key=ranking)
    eligible = [trial for trial in trials if gate(
        trial["summary"], POLICY["minimum_scope_training"], POLICY,
        POLICY["minimum_scope_training_families"])]
    selected = min(eligible, key=ranking) if eligible else trials[0]
    frozen = fit_one(pairs, selected["spec"])
    eligible_scope = sum(in_scope(features(p["source"]), frozen["scope"]) for p in pairs)
    eligible_cv = gate(selected["summary"], POLICY["minimum_scope_training"], POLICY,
                       POLICY["minimum_scope_training_families"])
    return {
        "version":2, "field":{"role":TRANS, "column":"MomentInertia"},
        "policy":copy.deepcopy(POLICY), "candidate_menu":specs(),
        "training_pairs":len(original), "eligible_training_pairs":len(pairs),
        "training_exclusions":excluded, "grouping":grouping,
        "selected":frozen, "selected_scope_training":eligible_scope,
        "selected_scope_training_families":len({
            family_key(p["source"]["media_name"]) for p in pairs
            if in_scope(features(p["source"]), frozen["scope"])}),
        "cv":trials, "selected_cv":selected["summary"], "cv_gate_passed":eligible_cv,
        "unrestricted_best_cv":unrestricted["name"],
        "selection_policy":"Minimum training group-CV MAE among candidates meeting all CV safety gates; otherwise identity.",
        "experimental_accepted":False, "conservative_accepted":False,
        "validated":False,
        "provenance":"Fit uses only training targets; reused validation is evaluated after freezing.",
        "development_note":"A prior minimum-MAE-only selection was audited and rejected for regressions. The final selector requires the same CV gates; validation is reused, not an independent discovery cohort.",
        "precision":"MomentInertia is rounded to the four decimal places present in the source databases; comparison tolerance remains 1e-6.",
    }


def validate(data, model):
    """Return a new model with decisions; keep selected model/menu/thresholds frozen."""
    result = copy.deepcopy(model)
    pairs = [p for p in data["pairs"] if p["split"] == "validation"]
    evidence = evaluate(pairs, result["selected"])
    policy = result["policy"]
    validation_gate = gate(evidence["summary"], policy["minimum_scope_validation"], policy,
                           policy["minimum_scope_validation_families"])
    result["experimental_accepted"] = bool(result["cv_gate_passed"] and validation_gate)
    tr, va = result["selected_cv"], evidence["summary"]
    result["conservative_accepted"] = bool(
        result["experimental_accepted"] and
        tr["scope_predicted"] >= policy["minimum_conservative_training"] and
        va["scope_predicted"] >= policy["minimum_conservative_validation"] and
        min(tr["scope_match_fraction"], va["scope_match_fraction"]) >=
        policy["minimum_conservative_match_fraction"])
    result["validated"] = True
    result["validation"] = evidence
    result["validation_gate_passed"] = validation_gate
    result["validation_reused"] = True
    result["validation_mismatch_policy"] = "All validation cars retained and flagged, including changed-specification pairs."
    return result


def propose(record, model, mode="conservative"):
    """Return calibration-compatible updates and notes; no target information."""
    notes = []
    acceptance = ("experimental_accepted" if mode in {"experimental", "estimated"}
                  else "conservative_accepted")
    if not model.get("validated") or not model.get(acceptance):
        return [], [{"drivetrain":"abstained", "reason":"frozen_rule_gate_not_passed",
                     "required_gate":acceptance}]
    if TRANS not in record["nodes"]:
        return [], [{"drivetrain":"abstained", "reason":"missing_stock_transmission"}]
    value, why = predict(record, model["selected"])
    if why != "predicted":
        return [], [{"drivetrain":"abstained", "reason":why}]
    baseline = record["nodes"][TRANS]["MomentInertia"]
    if cal.equal(value, baseline):
        return [], [{"drivetrain":"unchanged", "reason":"prediction_equals_source"}]
    notes.append({"drivetrain":"applied", "rule":model["selected"]["name"],
                  "confidence":"experimental_estimate" if acceptance == "experimental_accepted"
                  else "cross_car_supported",
                  "source_value":baseline, "predicted_value":value})
    return [{"role":TRANS, "column":"MomentInertia", "value":value,
             "rule":"drivetrain_v2_"+model["selected"]["name"],
             "confidence":notes[-1]["confidence"], "input_value":baseline}], notes


def diagnose(data):
    """Describe final-drive/aero ambiguity without turning retunes into a guessed rule."""
    pairs = [p for p in data["pairs"] if p["split"] == "training"]
    fields = [(TRANS, "FinalDriveRatio"), ("car", "BodyAeroLongitudinalDrag"),
              ("aero.front", "Downforce0"), ("aero.front", "Downforce1"),
              ("aero.rear", "Downforce0"), ("aero.rear", "Downforce1")]
    output = []
    for role, column in fields:
        grouped, examples = defaultdict(list), []
        counts = {}
        for car_type in sorted({p["source"]["nodes"]["car"]["CarTypeID"] for p in pairs}):
            subset = [p for p in pairs if p["source"]["nodes"]["car"]["CarTypeID"] == car_type]
            counts[str(car_type)] = {"n":len(subset), "different":sum(not cal.equal(
                p["source"]["nodes"][role][column], p["target"]["nodes"][role][column])
                for p in subset)}
        for pair in pairs:
            a, b = pair["source"]["nodes"][role][column], pair["target"]["nodes"][role][column]
            grouped[a].append((b, pair["source"]["media_name"]))
        for a, values in sorted(grouped.items()):
            if len({v[0] for v in values}) > 1:
                examples.append({"source":a, "distinct_targets":len({v[0] for v in values}),
                                 "targets":[{"value":b, "media_name":name} for b,name in values]})
        output.append({"role":role, "column":column, "by_source_car_type":counts,
                       "ambiguous_source_values":examples,
                       "decision":"preserve_source_pending_separate_physical_specification_or_aero_model"})
    return {"training_only":True, "fields":output}


def report(model, diagnostic):
    cv, val = model["selected_cv"], model["validation"]["summary"]
    lines = ["# Drivetrain v2 research", "",
             "Model selected using training-only group cross-validation. Source engine IDs, identical engine payloads, and normalized model families share folds. Names are used only for grouping, never inference.",
             "Validation uses the earlier 73-car split again; it is not a new independent test set.",
             "Cars with clear engine/drive specification mismatches or >5% mass changes are excluded only from fitting; validation retains and flags them.", "",
             f"- Training: {model['training_pairs']}; fitting eligible: {model['eligible_training_pairs']}.",
             f"- Selected candidate: `{model['selected']['name']}`.",
             f"- Source scope training support: {model['selected_scope_training']} cars / {model['selected_scope_training_families']} model families.",
             f"- Groups: {model['grouping']['components']}; largest group: {model['grouping']['largest_component']}.",
             f"- Experimental accepted: **{model['experimental_accepted']}**; conservative accepted: **{model['conservative_accepted']}**.", "",
             "| Evaluation | Cars | MAE before | MAE after | Exact before | Exact after | Improved | Regressed | Changed |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for title, s in (("Training group CV",cv), ("Reused validation",val)):
        lines.append(f"| {title} | {s['n']} | {s['baseline_mae']:.8f} | {s['predicted_mae']:.8f} | "
                     f"{s['baseline_matches']} | {s['predicted_matches']} | {s['improved']} | "
                     f"{s['regressed']} | {s['changed']} |")
    lines += ["", "The inference gate requires at least 12 CV predictions from five families and four validation predictions from three families, >=30% MAE reduction within the predicted scope, no worse individual error, and no reduction in exact matches. A conservative rule additionally requires 30/10 covered cars and >=98% exact matches.",
              f"Validation covers only **{val['scope_predicted']} cars / {val['scope_families']} families**. Covered-scope MAE is {val['scope_baseline_mae']:.8f} before and {val['scope_predicted_mae']:.8f} after the raw estimate.",
              "Development audit: an earlier selector chose minimum CV MAE without filtering unsafe candidates. Its global regression lowered average error but damaged many already-correct values. The final selector ranks only candidates passing the unchanged CV gates. This is further reuse of validation, not an independent confirmation.",
              "The candidate scopes/thresholds and coefficients were frozen before validation. The prediction domain rejects unseen inertia/year ranges.",
              "A rejected estimate is never applied, including in experimental mode. No gearbox ratio or aero field is changed by this module.", "",
              "## Candidate menu (training CV)", "",
              "| Candidate | MAE | Improved | Regressed | Exact | Changed |",
              "|---|---:|---:|---:|---:|---:|"]
    for trial in model["cv"]:
        s = trial["summary"]
        lines.append(f"| {trial['name']} | {s['predicted_mae']:.8f} | {s['improved']} | {s['regressed']} | {s['predicted_matches']} | {s['changed']} |")
    lines += ["", "## Final drive and aero diagnosis", "",
              "| Field | Type 1 different / n | Type 2 different / n | Type 3 different / n |",
              "|---|---:|---:|---:|"]
    for item in diagnostic["fields"]:
        cells = [f"{item['by_source_car_type'][str(i)]['different']} / {item['by_source_car_type'][str(i)]['n']}"
                 for i in (1,2,3)]
        lines.append(f"| {item['role']}.{item['column']} | "+" | ".join(cells)+" |")
    lines += ["", "Same source final-drive and downforce values map to multiple FM4 values. That disproves a lookup using those values alone, but does not prove no richer relationship exists. Race changes dominate; target retuning/variant differences cannot safely be interpreted as a universal unit conversion.",
              "All inertia counts concern a single stock transmission field, separately from the full car benchmark. Numerical agreement does not establish identical handling.", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohort", type=Path,
                        default=Path("outputs/fm-car-converter/remaining7-v2/cohort.json"))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--augmented", action="store_true")
    args = parser.parse_args()
    args.out = args.out.resolve()
    for source_path in (c.FM3_DEFAULT, c.FM4_DEFAULT):
        game_root = source_path.resolve().parent.parent.parent
        if args.out == game_root or game_root in args.out.parents:
            parser.error("Output must be outside source game directories")
    args.out.mkdir(parents=True, exist_ok=False)
    before = {str(p):c.sha(p) for p in (c.FM3_DEFAULT, c.FM4_DEFAULT)}
    data = json.loads(args.cohort.read_text(encoding="utf-8"))
    if not args.augmented:
        data = augment(data)
    c.dump(args.out/"cohort.json", data)
    frozen = fit(data)
    c.dump(args.out/"rules_before_validation.json", frozen)
    rules = validate(data, frozen)
    diagnostic = diagnose(data)
    c.dump(args.out/"rules.json", rules)
    c.dump(args.out/"diagnosis.json", diagnostic)
    (args.out/"REPORT.md").write_text(report(rules, diagnostic), encoding="utf-8")
    after = {str(p):c.sha(p) for p in (c.FM3_DEFAULT, c.FM4_DEFAULT)}
    c.dump(args.out/"manifest.json", {"source_hashes_before":before, "source_hashes_after":after,
                                     "sources_unchanged":before == after,
                                     "files":{p.name:c.sha(p) for p in args.out.iterdir() if p.is_file()}})
    if before != after:
        raise c.MappingError("Source hash changed")
    print(json.dumps({"selected":rules["selected"]["name"], "cv":rules["selected_cv"],
                      "validation":rules["validation"]["summary"],
                      "experimental":rules["experimental_accepted"],
                      "conservative":rules["conservative_accepted"]}, indent=2))


if __name__ == "__main__":
    main()
