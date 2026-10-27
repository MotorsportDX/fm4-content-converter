"""Research the seven residual fields. Fit uses NumPy; inference is stdlib only.

Every fitted rule remains experimental. Numeric closeness is not handling
validation. Toyota's target rows are never used in fitting or model selection.
"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import closing
import copy
import hashlib
import json
import math
from pathlib import Path
import statistics

import calibration as cal
import converter as c

CHASSIS = "List_UpgradeCarBodyChassisStiffness"
WEIGHT = "List_UpgradeCarBodyWeight"
TIRE = "List_UpgradeTireCompound"
FIELDS = [(CHASSIS, a+d+"FrictionScale") for a in ("Front", "Rear") for d in ("Lat", "Long")]
FIELDS += [(WEIGHT, "CMHeight"), (TIRE, "TireCompoundID"), ("engine", "GasTankSize")]
TASKS = ("grip", "cg", "compound", "tank")


def features(record):
    n = record["nodes"]
    car, body, weight, chassis = n["car"], n["body"], n[WEIGHT], n[CHASSIS]
    return {
        "front": chassis["FrontFrictionScale"], "rear": chassis["RearFrictionScale"],
        "old_cg": weight["CMHeight"], "old_tank": n["engine"]["GasTankSize"],
        "compound": n[TIRE]["TireCompoundID"], "year": car["Year"],
        "car_type": car["CarTypeID"], "body_type": car["FamilyBodyID"],
        "engine_location": car["EnginePlacementID"], "drive": car["DriveTypeID"],
        "mass": weight["Mass"], "weight_front": weight["CMBackFront"],
        "block_height": weight["BlockDimY"], "block_width": weight["BlockDimX"],
        "block_length": weight["BlockDimZ"],
        "bbox_height": body["PristineBoundingBoxMaxY"]-body["PristineBoundingBoxMinY"],
        "wheelbase": body["ModelWheelbase"],
        "ride": (body["ModelFrontStockRideHeight"]+body["ModelRearStockRideHeight"])/2,
        "wheel_radius": car["FrontWheelDiameterIN"]*.0254/2+
                        car["FrontTireWidthMM"]*car["FrontTireAspect"]/100000,
        "tire_width": car["FrontTireWidthMM"], "displacement": car["Displacement"],
        "power_mass": car["SimPeakPower"]/weight["Mass"],
    }


def actual(pair, task):
    n = pair["target"]["nodes"]
    return {"grip": n[CHASSIS]["FrontLatFrictionScale"], "cg": n[WEIGHT]["CMHeight"],
            "compound": n[TIRE]["TireCompoundID"], "tank": n["engine"]["GasTankSize"]}[task]


def baseline(f, task):
    return f[{"grip":"front", "cg":"old_cg", "compound":"compound", "tank":"old_tank"}[task]]


def candidate_specs(task):
    """Fixed candidate menu. No target identity, make or model IDs are features."""
    specs = [{"name":"identity", "kind":"identity", "features":[]}]
    if task == "compound":
        fs = ["compound", "year", "car_type", "body_type", "drive", "tire_width", "power_mass"]
        for depth in (2, 3, 4):
            for leaf in (5, 10):
                specs.append({"name":f"tree_d{depth}_leaf{leaf}", "kind":"tree",
                              "features":fs, "depth":depth, "min_leaf":leaf})
        return specs
    specs.append({"name":"median", "kind":"median", "features":[]})
    sets = {
        "grip": [["front", "rear"], ["front", "rear", "year"]],
        "cg": [["old_cg"], ["block_height"], ["bbox_height"],
               ["old_cg", "ride", "bbox_height"],
               ["block_height", "wheel_radius", "ride"],
               ["old_cg", "block_height", "bbox_height", "ride", "wheel_radius",
                "mass", "weight_front", "wheelbase"]],
        "tank": [["mass"], ["mass", "displacement", "wheelbase", "year", "power_mass"]],
    }[task]
    for fs in sets:
        for alpha in (0.0, 1.0):
            specs.append({"name":"linear_"+"_".join(fs)+f"_ridge{alpha}", "kind":"linear",
                          "features":fs, "ridge":alpha})
            if task == "grip":
                specs.append({**specs[-1], "name":specs[-1]["name"]+"_grid005", "grid":.005})
    if task in ("grip", "tank"):
        fs = (["front", "rear", "year", "car_type", "body_type", "mass"] if task == "grip"
              else ["mass", "displacement", "year", "car_type", "body_type", "wheelbase"])
        for depth in (2, 3, 4):
            for leaf in (5, 10):
                specs.append({"name":f"tree_d{depth}_leaf{leaf}", "kind":"tree",
                              "features":fs, "depth":depth, "min_leaf":leaf})
    return specs


def tree_fit(xs, ys, spec, task, depth=0):
    # Grip leaves use the most common discrete calibration; capacity uses median.
    discrete = task in ("compound", "grip")
    counts = Counter(ys)
    mode = sorted(counts, key=lambda y: (-counts[y], y))[0]
    value = mode if discrete else statistics.median(ys)
    node = {"value":value, "n":len(ys), "distribution":dict(sorted(counts.items()))}
    if depth >= spec["depth"] or len(ys) < 2*spec["min_leaf"] or len(counts) == 1:
        return node
    def loss(vals):
        if discrete:
            cc = Counter(vals)
            return len(vals)-sum(v*v for v in cc.values())/len(vals)
        mid = statistics.median(vals)
        return sum(abs(v-mid) for v in vals)
    best_loss, best = loss(ys), None
    for key in spec["features"]:
        values = sorted({f[key] for f in xs})
        categorical = key in {"compound", "car_type", "body_type", "drive", "engine_location"}
        candidates = values if categorical else [(a+b)/2 for a,b in zip(values, values[1:])]
        for threshold in candidates:
            mask = [(f[key] == threshold if categorical else f[key] <= threshold) for f in xs]
            a = [i for i,m in enumerate(mask) if m]
            b = [i for i,m in enumerate(mask) if not m]
            if min(len(a), len(b)) < spec["min_leaf"]:
                continue
            score = loss([ys[i] for i in a])+loss([ys[i] for i in b])
            if score < best_loss-1e-12:
                best_loss, best = score, (key, threshold, categorical, a, b)
    if best is not None:
        key, threshold, cat, a, b = best
        node.update(feature=key, threshold=threshold, categorical=cat,
                    left=tree_fit([xs[i] for i in a], [ys[i] for i in a], spec, task, depth+1),
                    right=tree_fit([xs[i] for i in b], [ys[i] for i in b], spec, task, depth+1))
    return node


def fit_one(pairs, task, spec):
    xs = [features(p["source"]) for p in pairs]
    ys = [actual(p, task) for p in pairs]
    model = {**spec, "task":task, "n":len(pairs)}
    model["domain"] = {k:{"min":min(f[k] for f in xs), "max":max(f[k] for f in xs),
                          "seen":sorted({f[k] for f in xs})}
                       for k in spec["features"]}
    if spec["kind"] == "median":
        model["value"] = statistics.median(ys)
    elif spec["kind"] == "tree":
        model["tree"] = tree_fit(xs, ys, spec, task)
    elif spec["kind"] == "linear":
        import numpy as np
        raw = np.array([[f[k] for k in spec["features"]] for f in xs], dtype=float)
        mean, scale = raw.mean(axis=0), raw.std(axis=0)
        scale[scale < 1e-12] = 1
        x = np.column_stack((np.ones(len(xs)), (raw-mean)/scale))
        penalty = np.eye(x.shape[1])*spec["ridge"]
        penalty[0, 0] = 0
        # Augmentation handles rank deficiency without inverting X.T @ X.
        beta = np.linalg.lstsq(np.vstack((x, np.sqrt(penalty))),
                               np.concatenate((ys, np.zeros(x.shape[1]))), rcond=None)[0]
        model["intercept"] = float(beta[0]-sum(beta[1:]*mean/scale))
        model["coefficients"] = {k:float(v) for k,v in zip(spec["features"], beta[1:]/scale)}
    residuals = sorted(abs(predict_one(model, f)[0]-y) for f,y in zip(xs, ys))
    model["training_abs_error_p90"] = residuals[math.ceil(.9*len(residuals))-1]
    return model


def predict_one(model, f, check_domain=False):
    if any(not isinstance(v, (int,float)) or not math.isfinite(v) for v in f.values()):
        raise c.MappingError("Non-finite residual-model feature")
    if check_domain:
        for k,domain in model["domain"].items():
            cat = k in {"compound", "car_type", "body_type", "drive", "engine_location"}
            if f[k] < domain["min"] or f[k] > domain["max"] or (cat and f[k] not in domain["seen"]):
                return baseline(f, model["task"]), {"abstained":"outside_training_domain", "feature":k}
    kind = model["kind"]
    detail = {}
    if kind == "identity":
        value = baseline(f, model["task"])
    elif kind == "median":
        value = model["value"]
    elif kind == "linear":
        value = model["intercept"]+sum(f[k]*v for k,v in model["coefficients"].items())
    elif kind == "tree":
        node = model["tree"]
        path = []
        while "feature" in node:
            key = node["feature"]
            left = f[key] == node["threshold"] if node["categorical"] else f[key] <= node["threshold"]
            path.append({"feature":key, "threshold":node["threshold"], "categorical":node["categorical"], "left":left})
            node = node["left"] if left else node["right"]
        value = node["value"]
        detail = {"leaf_n":node["n"], "leaf_distribution":node["distribution"], "path":path}
    else:
        raise c.MappingError("Unknown residual predictor")
    if "grid" in model:
        value = round(value/model["grid"])*model["grid"]
    if model["task"] != "compound":
        value = round(value, 4)
    if not math.isfinite(value) or value <= 0:
        return baseline(f, model["task"]), {"abstained":"nonpositive_prediction"}
    return value, detail


def fold(pair):
    # Group engines, matching the outer split's protection against shared rows.
    key = "remaining7-internal-v1:"+str(pair["source"]["engine_id"])
    return int(hashlib.sha256(key.encode()).hexdigest()[:8], 16) % 5


def select_models(data):
    train = [p for p in data["pairs"] if p["split"] == "training"]
    result = {"version":"remaining7-v1", "experimental_only":True,
              "selection":"five-fold source-engine-group CV on 236 training pairs only",
              "validation_reused":True,
              "policy":{"auto_apply":False, "numeric_cv_and_validation_mae_ratio":.8,
                        "compound_cv_and_validation_accuracy_gain":.03,
                        "tank_apply":False,
                        "reason":"Tank needs independent specification; fitted capacity is diagnostic only."},
              "relations":{"front_long_equals_front_lat":True, "rear_long_equals_rear_lat":True,
                           "rear_formula":"0.5 * predicted_front + 0.25 * source_rear + 0.25"},
              "models":{}, "selection_results":{}}
    for task in TASKS:
        results = []
        for spec in candidate_specs(task):
            errors, rows = [], []
            for i in range(5):
                fit_pairs = [p for p in train if fold(p) != i]
                test_pairs = [p for p in train if fold(p) == i]
                model = fit_one(fit_pairs, task, spec)
                for p in test_pairs:
                    pred, detail = predict_one(model, features(p["source"]), check_domain=True)
                    target = actual(p, task)
                    error = int(pred != target) if task == "compound" else abs(pred-target)
                    errors.append(error)
                    rows.append({"id":p["source"]["id"], "fold":i, "predicted":pred,
                                 "actual":target, "error":error, "detail":detail})
            results.append({"spec":spec, "cv_error":statistics.mean(errors), "predictions":rows})
        # Deterministic ties favor the earlier, simpler candidate.
        winner = min(results, key=lambda r:r["cv_error"])
        model = fit_one(train, task, winner["spec"])
        model["cv_error"] = winner["cv_error"]
        model["baseline_cv_error"] = results[0]["cv_error"]
        cv_errors = sorted(r["error"] for r in winner["predictions"])
        model["cv_abs_error_p90"] = cv_errors[math.ceil(.9*len(cv_errors))-1]
        result["models"][task] = model
        result["selection_results"][task] = results
    return result


def predictions(record, model):
    f = features(record)
    return {task:predict_one(model["models"][task], f, check_domain=True) for task in TASKS}


def ambiguity_evidence(data):
    """Training examples make the limits of one-column conversion inspectable."""
    train = [p for p in data["pairs"] if p["split"] == "training"]
    groups = {}
    for task in TASKS:
        grouped = {}
        for p in train:
            key = baseline(features(p["source"]), task)
            grouped.setdefault(key, []).append({
                "media_name":p["source"]["media_name"], "year":p["source"]["year"],
                "source":key, "target":actual(p,task)})
        groups[task] = {
            "source_distinct":len(grouped),
            "target_distinct":len({actual(p,task) for p in train}),
            "ambiguous_source_values":sum(len({r["target"] for r in rs})>1 for rs in grouped.values()),
            "groups":[{"source":v,"targets":sorted({r["target"] for r in rs}),"cars":rs}
                      for v,rs in sorted(grouped.items())]}
    return groups


def evaluate(pairs, model):
    output = {}
    for task in TASKS:
        per_car = []
        for p in pairs:
            f = features(p["source"])
            pred, detail = predict_one(model["models"][task], f, check_domain=True)
            target, before = actual(p, task), baseline(f, task)
            error = lambda x: int(x != target) if task == "compound" else abs(x-target)
            per_car.append({"id":p["source"]["id"], "media_name":p["source"]["media_name"],
                            "source":before, "actual":target, "predicted":pred,
                            "baseline_error":error(before), "predicted_error":error(pred), "detail":detail})
        output[task] = {
            "n":len(per_car), "baseline_error":statistics.mean(r["baseline_error"] for r in per_car),
            "predicted_error":statistics.mean(r["predicted_error"] for r in per_car),
            "baseline_matches":sum(cal.equal(r["source"], r["actual"]) for r in per_car),
            "predicted_matches":sum(cal.equal(r["predicted"], r["actual"]) for r in per_car),
            "improved":sum(r["predicted_error"] < r["baseline_error"]-1e-6 for r in per_car),
            "regressed":sum(r["predicted_error"] > r["baseline_error"]+1e-6 for r in per_car),
            "abstained":sum("abstained" in r["detail"] for r in per_car),
            "cars":per_car,
        }
    relation_errors = []
    for p in pairs:
        a, b = p["source"]["nodes"][CHASSIS], p["target"]["nodes"][CHASSIS]
        if (not cal.equal(b["FrontLatFrictionScale"], b["FrontLongFrictionScale"]) or
            not cal.equal(b["RearLatFrictionScale"], b["RearLongFrictionScale"]) or
            not cal.equal(b["RearLatFrictionScale"], .5*b["FrontLatFrictionScale"]+.25*a["RearFrictionScale"]+.25)):
            relation_errors.append(p["source"]["media_name"])
    output["relations"] = {"n":len(pairs), "exceptions":relation_errors,
                           "warning":"Uses native target front to test structure, not end-to-end prediction."}
    # End-to-end metrics for all four chassis fields, including front prediction.
    output["chassis_fields"] = []
    for role, column in FIELDS[:4]:
        errors, matches = [], 0
        for p in pairs:
            f = features(p["source"])
            front, detail = predict_one(model["models"]["grip"], f, check_domain=True)
            value = front if column.startswith("Front") else round(.5*front+.25*f["rear"]+.25, 4)
            if "abstained" in detail:
                value = cal.source_baseline(p["source"], role, column)
            actual_value = p["target"]["nodes"][role][column]
            errors.append(abs(value-actual_value))
            matches += cal.equal(value, actual_value)
        output["chassis_fields"].append({"column":column, "mae":statistics.mean(errors), "matches":matches, "n":len(pairs)})
    return output


def validate_models(data, model):
    validation = evaluate([p for p in data["pairs"] if p["split"] == "validation"], model)
    for task, fitted in model["models"].items():
        stats = validation[task]
        if task == "compound":
            gain = model["policy"]["compound_cv_and_validation_accuracy_gain"]
            favorable = (fitted["cv_error"] <= fitted["baseline_cv_error"]-gain and
                         stats["predicted_error"] <= stats["baseline_error"]-gain)
        else:
            ratio = model["policy"]["numeric_cv_and_validation_mae_ratio"]
            favorable = (fitted["cv_error"] <= fitted["baseline_cv_error"]*ratio and
                         stats["predicted_error"] <= stats["baseline_error"]*ratio)
        fitted["validation_favorable"] = favorable
        fitted["apply_experimental"] = favorable and task != "tank"
    # Structural exceptions block the joint four-column rule.
    if validation["relations"]["exceptions"]:
        model["models"]["grip"]["apply_experimental"] = False
    return validation


def propose(record, model, mode):
    if mode != "experimental":
        return [], [{"rule":"remaining7", "reason":"experimental_only"}]
    values = predictions(record, model)
    updates, notes = [], []
    for task in TASKS:
        value, detail = values[task]
        fitted = model["models"][task]
        if task == "tank" or not fitted.get("apply_experimental") or "abstained" in detail:
            notes.append({"rule":"remaining7_"+task, "reason":detail.get("abstained",
                          "independent_specification_required" if task == "tank" else "validation_gate_failed"),
                          "diagnostic_prediction":value, "detail":detail})
            continue
        if task == "grip":
            rear = round(.5*value+.25*record["nodes"][CHASSIS]["RearFrictionScale"]+.25, 4)
            entries = [(r,k,value if k.startswith("Front") else rear) for r,k in FIELDS[:4]]
        else:
            r,k = {"cg":(WEIGHT,"CMHeight"), "compound":(TIRE,"TireCompoundID")}[task]
            entries = [(r,k,value)]
        for role, column, v in entries:
            updates.append({"role":role, "column":column, "value":v, "rule":"remaining7_"+task,
                            "confidence":"experimental_estimate", "model":fitted["name"],
                            "cv_abs_error_p90":fitted["cv_abs_error_p90"], "detail":detail})
    return updates, notes


def report(model, evaluation, evidence):
    lines = [
        "# Analisis tujuh kolom tersisa — FM3 ke FM4", "",
        "Toyota dikeluarkan sebelum membaca kalibrasi target. Pemilihan model memakai lima fold engine "
        "di 236 pasangan training. Menu model dan kebijakan dibekukan sebelum evaluasi 73 pasangan validation. "
        "Validation ini pernah digunakan pada studi sebelumnya, jadi bukan test set baru yang sepenuhnya independen. "
        "Varian dengan chassis serupa masih mungkin berkorelasi meskipun engine dipisahkan.", "",
        "Semua model baru tetap eksperimental. Ambang untuk kandidat numerik adalah MAE CV dan validation "
        "maksimal 80% baseline; compound harus meningkatkan akurasi setidaknya 3 poin persentase pada keduanya. "
        "Tangki hanya diprediksi untuk diagnosis dan tidak diterapkan. Tidak ada uji game/handling.", "",
        "## Pola struktur chassis", "",
        "`FrontLong = FrontLat`, `RearLong = RearLat`, "
        "`RearLat = 0.5 × FrontLat + 0.25 × RearFrictionScale_FM3 + 0.25`.", "",
        f"Pola tersebut cocok pada training {evaluation['training']['relations']['n']-len(evaluation['training']['relations']['exceptions'])}"
        f"/{evaluation['training']['relations']['n']} dan validation "
        f"{evaluation['validation']['relations']['n']-len(evaluation['validation']['relations']['exceptions'])}"
        f"/{evaluation['validation']['relations']['n']}. Pemeriksaan ini memakai FrontLat target untuk "
        "menguji hubungan antar kolom; bukan bukti bahwa nilai FrontLat dapat diprediksi sempurna. "
        "Empat kolom grip kini menyisakan satu nilai bebas, yaitu FrontLat FM4.", "",
        "## Model yang dipilih sebelum validation", "",
        "| Grup | Model | CV error baseline → model | Validation error baseline → model | Exact validation | Membaik / memburuk | Dipakai di eksperimen |",
        "|---|---|---:|---:|---:|---:|---|",
    ]
    for task in TASKS:
        m, v = model["models"][task], evaluation["validation"][task]
        lines.append(f"| {task} | `{m['name']}` | {m['baseline_cv_error']:.6g} → {m['cv_error']:.6g} | "
                     f"{v['baseline_error']:.6g} → {v['predicted_error']:.6g} | "
                     f"{v['predicted_matches']}/{v['n']} | {v['improved']} / {v['regressed']} | "
                     f"{m['apply_experimental']} |")
    lines += ["", "## Rumus estimasi terpilih", "",
              "Koefisien di bawah dibulatkan untuk dibaca; inference memakai presisi penuh dalam JSON. "
              "Rumus grip dibulatkan ke grid 0,005; hasil CG dibulatkan empat desimal. "
              "Ini model empiris dari training, bukan rumus resmi engine.", ""]
    for task in ("grip","cg"):
        m = model["models"][task]
        if m["kind"] == "linear":
            equation = f"{m['intercept']:.10g}" + "".join(
                f" {v:+.10g} × {k}" for k,v in m["coefficients"].items())
            lines.append(f"- `{task} = {equation}`")
    lines += ["", "`ride` adalah rata-rata ModelFrontStockRideHeight dan ModelRearStockRideHeight FM3; "
              "`bbox_height` adalah PristineBoundingBoxMaxY − MinY; `old_cg` adalah CMHeight FM3. "
              "`front` dan `rear` adalah skala grip chassis FM3, `year` adalah tahun model.", "",
              "## Contoh mobil lain dan ambiguitas", "",
              "| Grup | Sumber berbeda | Target berbeda | Nilai sumber yang punya >1 target |",
              "|---|---:|---:|---:|"]
    for task in TASKS:
        e = evidence[task]
        lines.append(f"| {task} | {e['source_distinct']} | {e['target_distinct']} | {e['ambiguous_source_values']} |")
    lines += ["", "Contoh training dengan grip depan FM3 sama seperti Toyota:", "",
              "| Mobil | Tahun | Grip depan FM3 | Grip depan FM4 |", "|---|---:|---:|---:|"]
    group = next(g for g in evidence["grip"]["groups"] if g["source"] == .95)
    for r in group["cars"]:
        lines.append(f"| {r['media_name']} | {r['year']} | {r['source']} | {r['target']} |")
    lines += ["", "Contoh compound 5 pada mobil sebelum 1980 (seluruh contoh training yang memenuhi kondisi):", "",
              "| Mobil | Tahun | Compound FM3 | Compound FM4 |", "|---|---:|---:|---:|"]
    group = next(g for g in evidence["compound"]["groups"] if g["source"] == 5)
    for r in group["cars"]:
        if r["year"] < 1980:
            lines.append(f"| {r['media_name']} | {r['year']} | {r['source']} | {r['target']} |")
    lines += ["", "Semua kandidat compound yang memakai pohon keputusan kalah pada CV. "
              "Model terbaik tetap identity; ini alasan konversi 5 → 2 tidak diotomatisasi.", "",
              "Regresi grip pada validation (perubahan membuat error lebih besar):", ""]
    for r in evaluation["validation"]["grip"]["cars"]:
        if r["predicted_error"] > r["baseline_error"]+1e-6:
            lines.append(f"- `{r['media_name']}`: baseline {r['source']} → estimasi {r['predicted']}; FM4 {r['actual']}.")
    lines += ["", "## Akurasi empat kolom chassis secara menyeluruh", "",
              "| Kolom | Exact validation | MAE validation |", "|---|---:|---:|"]
    for row in evaluation["validation"]["chassis_fields"]:
        lines.append(f"| {row['column']} | {row['matches']}/{row['n']} | {row['mae']:.8g} |")
    lines += ["", "Error numerik adalah MAE dalam skala kolom database. Error compound adalah proporsi "
              "klasifikasi salah; selisih angka ID tidak diperlakukan sebagai jarak fisik. "
              "CV menerapkan penjagaan domain yang sama dengan inference. Identitas, merek dan nama model "
              "tidak dijadikan fitur. `power_mass` memakai SimPeakPower FM3 sehingga bukan daya FM4 terukur.", "",
              "## Batas interpretasi", "",
              "- CG: korelasi geometri adalah estimasi, bukan penemuan konversi satuan atau algoritme solver. "
              "Error p90 CV merupakan ringkasan sampel, bukan interval jaminan untuk mobil tertentu.",
              "- Compound: kelas dipilih sebagai kategori, bukan rata-rata ID. Daun pohon dan jumlah "
              "pendukung dicatat; daun kecil tetap lemah untuk mobil langka.",
              "- Tangki: semua 236 training memiliki GasTankSize FM3 = 20, sementara nilai FM4 bervariasi. "
              "Prediksi dari ukuran/jenis mobil tidak cukup untuk mengklaim kapasitas spesifik. Diperlukan "
              "spesifikasi independen dengan provenance, lalu pengecekan makna satuan pada FM4.",
              "- Empat kolom grip yang sama pola strukturalnya bukan empat bukti generalisasi independen.",
              "- Profil suspensi dari studi sebelumnya tetap ditolak untuk pemakaian otomatis; "
              "penambahan eksperimen ini tidak mengubah keputusannya.", "",
              "Parameter lengkap, semua kandidat CV, prediksi per mobil, regresi, dan abstention disimpan "
              "pada JSON. `rules_before_validation.json` dibekukan sebelum evaluasi; hanya flag hasil gerbang "
              "yang ditambahkan sesudahnya.", ""]
    return "\n".join(lines)


def heldout_report(out, model):
    before = json.loads((out/"toyota-previous-experimental"/"candidate_ir.json").read_text())
    after = json.loads((out/"toyota-residual-experimental"/"candidate_ir.json").read_text())
    native = json.loads((out/"toyota-residual-experimental"/"reference_fm4_ir.json").read_text())
    source = json.loads((out/"toyota-residual-experimental"/"source_ir.json").read_text())
    rec = {"nodes":{r:n["row"] for r,n in source["nodes"].items()}}
    pred = predictions(rec, model)
    lines = ["# Toyota 2000GT — perbandingan tujuh kolom", "",
             "Toyota tidak masuk fitting atau pemilihan model. Nilai target sudah diketahui dari studi "
             "sebelumnya, sehingga hasil ini merupakan pemeriksaan target yang dikecualikan dari fitting, "
             "bukan benchmark yang sepenuhnya buta.", "",
             "| Kolom | Sebelumnya | Eksperimen baru | FM4 asli | Error absolut baru |",
             "|---|---:|---:|---:|---:|"]
    for role, col in FIELDS:
        a,b,t = [g["nodes"][role]["row"][col] for g in (before,after,native)]
        err = str(int(b != t))+" (kategori)" if role == TIRE else f"{abs(b-t):.6g}"
        lines.append(f"| {role}.{col} | {a} | {b} | {t} | {err} |")
    lines += ["", "## Prediksi dan dukungan", ""]
    for task in TASKS:
        v, detail = pred[task]
        m = model["models"][task]
        lines += [f"- **{task}**: prediksi {v}; diterapkan `{m['apply_experimental']}`; "
                  f"p90 error CV {m['cv_abs_error_p90']:.6g}. Detail: `{json.dumps(detail,sort_keys=True)}`."]
    lines += ["", "Prediksi tangki hanya diagnosis; kandidat mempertahankan nilai FM3 dan menandai "
              "kebutuhan spesifikasi. Default conservative tetap memakai lima aturan lama. "
              "Eksperimen penuh juga memakai profil suspensi yang gagal gerbang generalisasi sebelumnya. "
              "Kedekatan database tidak membuktikan handling atau kesiapan DLC.", ""]
    for name in ("toyota-conservative","toyota-previous-experimental","toyota-residual-experimental"):
        comp = json.loads((out/name/"comparison.json").read_text())
        lines += [f"`{name}`: `{json.dumps(comp['differences_by_category'],sort_keys=True)}`", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--previous-rules", type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    if out.exists():
        parser.error("Use a new output directory")
    for path in (c.FM3_DEFAULT, c.FM4_DEFAULT):
        root = path.resolve().parent.parent.parent
        if out == root or root in out.parents:
            parser.error("Output must be outside game directories")
    hashes = {str(p):c.sha(p) for p in (c.FM3_DEFAULT, c.FM4_DEFAULT)}
    with closing(c.connect(c.FM3_DEFAULT)) as src, closing(c.connect(c.FM4_DEFAULT)) as dst:
        data = cal.collect(src, dst)
    out.mkdir(parents=True)
    c.dump(out/"cohort.json", data)
    # Save the finite candidate menu and gate before running CV or validation.
    c.dump(out/"protocol.json", {"candidates":{t:candidate_specs(t) for t in TASKS},
                               "numeric_ratio_gate":.8, "compound_accuracy_gain_gate":.03,
                               "tank_apply":False, "all_rules_experimental":True,
                               "validation_reused":True, "fit_includes_toyota":False})
    model = select_models(data)
    c.dump(out/"rules_before_validation.json", model)
    validation = validate_models(data, model)
    evaluation = {"training":evaluate([p for p in data["pairs"] if p["split"]=="training"], model),
                  "validation":validation}
    c.dump(out/"remaining_rules.json", model)
    c.dump(out/"evaluation.json", evaluation)
    evidence = ambiguity_evidence(data)
    c.dump(out/"ambiguity.json", evidence)
    previous = json.loads(args.previous_rules.read_text(encoding="utf-8"))
    combined = copy.deepcopy(previous)
    combined["remaining7"] = model
    c.dump(out/"rules.json", combined)
    (out/"REPORT.md").write_text(report(model,evaluation,evidence), encoding="utf-8")
    results = {}
    for name, rules, mode in (
        ("toyota-conservative",out/"rules.json","conservative"),
        ("toyota-previous-experimental",args.previous_rules,"experimental"),
        ("toyota-residual-experimental",out/"rules.json","experimental"),
    ):
        results[name] = c.run(c.FM3_DEFAULT,c.FM4_DEFAULT,out/name,
                             calibration_rules=rules,calibration_mode=mode)
    (out/"TOYOTA_COMPARISON.md").write_text(heldout_report(out,model),encoding="utf-8")
    after = {str(p):c.sha(p) for p in (c.FM3_DEFAULT, c.FM4_DEFAULT)}
    if after != hashes:
        raise c.MappingError("Source database changed during residual study")
    c.dump(out/"manifest.json", {"sources_before":hashes,"sources_after":after,"sources_unchanged":True,
                                "previous_rules_sha256":c.sha(args.previous_rules),
                                "code_sha256":{p:c.sha(Path(__file__).parent/p) for p in
                                               ("remaining.py","calibration.py","converter.py")},
                                "runtime_tested":False,
                                "outputs":{str(p.relative_to(out)):c.sha(p) for p in sorted(out.rglob("*")) if p.is_file()}})
    print(json.dumps({"out":str(out), "counts":data["counts"],
                      "models":{t:{k:v for k,v in m.items() if k in
                                   ("name","cv_error","validation_favorable","apply_experimental")}
                                for t,m in model["models"].items()},
                      "toyota":results, "sources_unchanged":True},indent=2))


if __name__ == "__main__":
    main()
