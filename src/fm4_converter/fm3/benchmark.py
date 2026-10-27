"""Reproducible diverse stock-car benchmark. Does not fit rules or install data."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from contextlib import closing
import copy
import json
import math
from pathlib import Path
import re
import traceback

from . import calibration as cal
from . import converter as c
from . import compatibility


# Fixed from source metadata before looking at full-conversion outcomes. All are
# in the existing validation split, none in the rule-fitting training split.
SELECTION = [
    ("CHE_CamaroZ28_69", "classic US coupe"),
    ("PON_TransAm_73", "1970s US coupe"),
    ("LAN_Stratos_74", "classic mid engine"),
    ("TOY_Sprinter_85", "1980s light RWD"),
    ("MAZ_RX7_90", "rotary turbo"),
    ("HON_CivicVti_94", "1990s FWD hatch"),
    ("FOR_MustangSVTCobraR_93", "1990s US RWD"),
    ("MIT_GTO_97", "1990s AWD twin turbo"),
    ("TOY_SupraRZ_98", "inline six twin turbo"),
    ("FER_360_99", "1990s mid engine V8"),
    ("MIN_CooperS_03", "FWD supercharger"),
    ("VW_Beetle_04", "FWD turbo"),
    ("PEU_206RC_04", "FWD naturally aspirated"),
    ("SCI_xD_09", "small modern FWD"),
    ("FOR_FocusRS_09", "high output FWD turbo"),
    ("MIT_LancerEvoIXMR_06", "AWD turbo sedan"),
    ("VW_GolfR32_03", "AWD naturally aspirated hatch"),
    ("SAA_93TurboX_08", "AWD turbo V6 sedan"),
    ("AUD_R8_08", "AWD mid engine"),
    ("BUG_Veyron_09", "AWD W configuration"),
    ("CHE_CorvetteZR1_09", "supercharged RWD"),
    ("HON_NSXRGT_05", "mid engine Japanese coupe"),
    ("LOT_Evora_09", "mid engine V6"),
    ("KOE_CCGT_08", "special type 2 car"),
    ("BMW_2_M3GTR_05", "front engine race"),
    ("BMW_15_LMR_99", "prototype naturally aspirated"),
    ("TOY_3_GT1_99", "prototype twin turbo"),
    ("AUD_2_R10_08", "diesel race prototype"),
    ("DOD_91_ViperGTSR_00", "front engine V10 race"),
    ("FER_12_333SP_98", "prototype V12"),
]
MODES = ("baseline", "conservative", "experimental", "refined_conservative", "refined_experimental")
NEXT_KEYS = ("suspension_v2","drivetrain_v2")
GOOD = {"exact", "within_numeric_tolerance", "equivalent_registry_payload"}
BAD = {"different", "missing_role", "inactive_padding_difference"}


def modes_for(rules):
    return MODES + (("next_conservative","next_experimental") if any(k in rules for k in NEXT_KEYS) else ())


def profile_for_mode(rules, mode):
    """Keep previous comparison arms frozen when adding a new profile."""
    profile = {k:v for k,v in rules.items() if mode.startswith("next_") or k not in NEXT_KEYS}
    if not mode.startswith(("refined_","next_")):
        profile = {k:v for k,v in profile.items() if k!="benchmark_refinements"}
    return profile, mode.removeprefix("refined_").removeprefix("next_")


def selection(data):
    by_name = {p["source"]["media_name"]:p for p in data["pairs"]}
    out = []
    for index, (name, reason) in enumerate(SELECTION):
        pair = by_name[name]
        if pair["split"] != "validation":
            raise c.MappingError("Benchmark car was used to fit calibration: "+name)
        s, car = pair["source"], pair["source"]["nodes"]["car"]
        out.append({"media_name":name, "reason":reason, "id":s["id"], "source_engine_id":s["engine_id"],
                    "year":car["Year"], "drive":{1:"FWD",2:"RWD",3:"AWD"}[car["DriveTypeID"]],
                    "placement":{1:"Front",2:"Mid",3:"Rear"}[car["EnginePlacementID"]],
                    "car_type_id":car["CarTypeID"], "body_type_id":car["FamilyBodyID"],
                    "aspiration_id":car["AspirationTypeId"], "make_id":car["MakeID"],
                    "rotary":s["nodes"]["engine"]["Rotary"], "diesel":s["nodes"]["engine"]["Diesel"],
                    "id_base":c.ID_BASE+index*1000})
    if len(out) != 30 or len({r["media_name"] for r in out}) != 30:
        raise c.MappingError("Expected 30 distinct benchmark cars")
    return {"cars":out, "selection_rule":"Fixed metadata diversity panel from previous validation split; failures retained",
            "reused_validation":True, "new_independent_test_set":False, "fitting_performed":False,
            "coverage":{key:dict(Counter(str(r[key]) for r in out))
                        for key in ("drive","placement","car_type_id","rotary","diesel")},
            "year_range":[min(r["year"] for r in out),max(r["year"] for r in out)],
            "makes":len({r["make_id"] for r in out})}


def family(role, column=""):
    if role == "car":
        if column.startswith("BodyAero") or column == "GameDragScale": return "aero"
        if column in {"CurbWeight","WeightDistribution"}: return "body_geometry_mass"
        if column in {"Displacement","GameTorqueScale"}: return "engine"
        if "Tire" in column or "WheelDiameter" in column: return "tires_wheels"
        if column == "NumGears": return "drivetrain"
        if column.endswith("StockRideHeight"): return "suspension"
    if role.startswith(("spring.", "antiroll.")): return "suspension"
    if role.startswith("torque."): return "torque_curve"
    if role.startswith("aero."): return "aero"
    if role in ("body", "List_UpgradeCarBodyWeight"): return "body_geometry_mass"
    if "Chassis" in role or role == "tire.modifier": return "chassis_grip"
    if "Tire" in role or "Wheel" in role or role == "wheel": return "tires_wheels"
    if "Drivetrain" in role or role == "drivetrain": return "drivetrain"
    if role == "engine" or "Engine" in role: return "engine"
    if "Brake" in role: return "brakes"
    return "car_controls_and_other"


def summarise(comp):
    physical = [f for f in comp["fields"] if f["category"]=="physics"]
    groups = {}
    for name in sorted({family(f["role"],f.get("column","")) for f in physical}):
        fs = [f for f in physical if family(f["role"],f.get("column",""))==name]
        groups[name] = {"fields":len(fs),"matched":sum(f["status"] in GOOD for f in fs),
                        "different":sum(f["status"] in BAD for f in fs)}
    return {"physics_fields":len(physical), "physics_matches":sum(f["status"] in GOOD for f in physical),
            "physics_differences":sum(f["status"] in BAD for f in physical),
            "structure_differences":sum(f["category"]=="structure" for f in comp["differences"]),
            "differences_by_category":comp["differences_by_category"],"families":groups}


def registry_comparison(db, candidate, reference):
    """Compare full selected tyre payloads by dependency role, never average IDs."""
    schema = c.schema(db)
    def gather(graph):
        result = {}
        def visit(table, ident, path):
            pk = c.pk(schema[table])
            row = c.one(c.rows(db,table,c.qi(pk)+"=?",(ident,)),path)
            result[path] = {"table":table,"id":ident,"row":row,"pk":pk}
            for key,value in row.items():
                target = None
                if table == "List_TireCompound":
                    if key.startswith("FrictionMultiCurve"): target = "List_TireFrictionMultiCurve"
                    elif key.startswith("AffectCurve"): target = "List_TireAffectCurve"
                elif table == "List_TireFrictionMultiCurve" and key.startswith("TireFrictionCurve"):
                    target = "List_TireFrictionCurve"
                if target:
                    visit(target,value,path+"/"+key)
        visit("List_TireCompound",graph["nodes"]["List_UpgradeTireCompound"]["row"]["TireCompoundID"],"compound")
        return result
    a,b = gather(candidate),gather(reference)
    fields = []
    for role in sorted(a.keys()|b.keys()):
        if role not in a or role not in b:
            fields.append({"role":role,"status":"missing_role"})
            continue
        for col,value in a[role]["row"].items():
            actual = b[role]["row"][col]
            if col == a[role]["pk"]:
                status = "registry_id_same" if value==actual else "registry_id_different"
            elif role+"/"+col in a or role+"/"+col in b:
                status = "dependency_pointer_same" if value==actual else "dependency_pointer_different"
            elif not isinstance(value,(int,float)):
                status = "metadata_same" if value==actual else "metadata_different"
            elif value == actual or math.isclose(value,actual,rel_tol=1e-6,abs_tol=1e-6):
                status = "numeric_match"
            else:
                status = "numeric_different"
            fields.append({"role":role,"table":a[role]["table"],"column":col,
                           "candidate":value,"reference":actual,"status":status})
    return {"counts":dict(Counter(f["status"] for f in fields)), "fields":fields,
            "scope":"Native FM4 selected tyre dependency graph; counts are separate from car physics totals."}


def transitions(comparisons):
    """Per-field improvements/regressions without mixing incompatible units."""
    lookups = {mode:{(f["role"],f.get("column")):f for f in comp["fields"] if f["category"]=="physics"}
               for mode,comp in comparisons.items()}
    output = []
    if "baseline" not in lookups:
        return output
    for mode,lookup in lookups.items():
        if mode == "baseline": continue
        for key,b in lookups["baseline"].items():
            if key not in lookup: continue
            a = lookup[key]
            if a.get("candidate") == b.get("candidate"): continue
            r = {"mode":mode,"role":key[0],"column":key[1],"baseline":b["candidate"],
                 "candidate":a["candidate"],"native":a["fm4_reference"],"family":family(key[0],key[1]),
                 "baseline_match":b["status"] in GOOD,"predicted_match":a["status"] in GOOD}
            av,bv,target = a["candidate"],b["candidate"],a["fm4_reference"]
            # Enum IDs are classifications, not numeric distances.
            if key[1].lower().endswith("id") or not all(isinstance(x,(int,float)) for x in (av,bv,target)):
                eb,ea = int(bv!=target),int(av!=target)
            else:
                eb,ea = abs(bv-target),abs(av-target)
            r.update(baseline_error=eb,predicted_error=ea,
                     result="improved" if ea<eb-1e-6 else "regressed" if ea>eb+1e-6 else "unchanged")
            output.append(r)
    return output


def run_car(src, dst, rules, car, folder):
    folder.mkdir()
    results, comps = {}, {}
    try:
        source = c.extract_stock(src,car["media_name"])
        baseline = c.convert(src,dst,source,car["id_base"])
    except (c.MappingError,KeyError,ValueError) as error:
        c.dump(folder/"failure.json", {"stage":"extract_or_convert","type":type(error).__name__,
                                      "error":str(error),"traceback":traceback.format_exc()})
        return {"media_name":car["media_name"],"failure":str(error),"stage":"extract_or_convert"}
    c.dump(folder/"source_ir.json",source)
    c.dump(folder/"baseline_mapping.json",baseline["mapping"])
    c.dump(folder/"assumptions.json",baseline["assumptions"])
    c.dump(folder/"dropped_fields.json",baseline["dropped_source_fields"])
    candidates = {}
    for mode in modes_for(rules):
        where = folder/mode
        where.mkdir()
        try:
            result = copy.deepcopy(baseline)
            if mode != "baseline":
                profile, inference_mode = profile_for_mode(rules,mode)
                cal.apply_to_result(result,source,profile,inference_mode)
                c.refresh_tire_dependencies(dst,result)
            patch = c.write_patch(where/"candidate_stock.slt",dst,result["candidate"])
            valid = c.validate(result["candidate"],dst,where/"candidate_stock.slt",source=source)
            c.dump(where/"validation.json",valid)
            candidates[mode] = result["candidate"]
            c.dump(where/"candidate_ir.json",result["candidate"])
            c.dump(where/"external_dependencies.json",{"registries":result["external_dependencies"],
                                                       "native_tires":result["native_tire_dependencies"]})
            if mode != "baseline":
                c.dump(where/"calibration_changes.json",result["calibration"])
            results[mode] = {"validation_passed":valid["passed"],"validation_issues":valid["issues"],
                             "validation_warnings":valid["warnings"],"rows":patch["rows"],"tables":patch["tables"]}
        except (c.MappingError,KeyError,ValueError) as error:
            results[mode] = {"failure":str(error),"stage":"calibrate_write_validate"}
            c.dump(where/"failure.json",{**results[mode],"traceback":traceback.format_exc()})
    # Native car data is loaded only after all predictions and patches exist.
    try:
        reference = c.extract_stock(dst,car["media_name"])
        c.dump(folder/"reference_fm4_ir.json",reference)
    except (c.MappingError,KeyError,ValueError) as error:
        return {"media_name":car["media_name"],"modes":results,"failure":str(error),"stage":"reference_extraction"}
    for mode, candidate in candidates.items():
        comparison = c.compare(candidate,reference,dst)
        c.dump(folder/mode/"comparison.json",comparison)
        tyre = registry_comparison(dst,candidate,reference)
        c.dump(folder/mode/"tyre_comparison.json",tyre)
        results[mode].update(summarise(comparison))
        results[mode]["tyre_dependency_counts"] = tyre["counts"]
        comps[mode] = comparison
    changes = transitions(comps)
    c.dump(folder/"transitions.json",changes)
    improvements = []
    for mode in ("conservative","experimental"):
        if mode in comps and "refined_"+mode in comps:
            improvements += transitions({"baseline":comps[mode],"refined_"+mode:comps["refined_"+mode]})
        if "refined_"+mode in comps and "next_"+mode in comps:
            improvements += transitions({"baseline":comps["refined_"+mode],"next_"+mode:comps["next_"+mode]})
    c.dump(folder/"refinement_deltas.json",improvements)
    audit = diagnostic_audit(source,reference,comps)
    c.dump(folder/"diagnostics.json",audit)
    return {"media_name":car["media_name"],"modes":results,"transitions":changes,
            "refinement_deltas":improvements,"diagnostics":audit}


def diagnostic_audit(source, reference, comps):
    """Post-conversion checks never feed reference values back into candidates."""
    a,b = source["nodes"],reference["nodes"]
    sensitive = [("car","Displacement"),("engine","CylinderID"),("engine","ConfigID"),
                 ("engine","Rotary"),("engine","Diesel"),("List_UpgradeCarBodyWeight","Mass")]
    variant = []
    for role,col in sensitive:
        x,y = a[role]["row"][col],b[role]["row"][col]
        if x!=y:
            variant.append({"role":role,"column":col,"source":x,"reference":y})
    missing = [{"role":role,"source_present":role in a,"reference_present":role in b}
               for role in sorted(a.keys()^b.keys()) if role!="torque.zero"]
    ta,tb = a["torque.full"]["row"],b["torque.full"]["row"]
    ca,cb = a["List_UpgradeEngineCamshaft"]["row"],b["List_UpgradeEngineCamshaft"]["row"]
    curve = {"source_count":ta["NumTorqueValues"],"reference_count":tb["NumTorqueValues"],
             "source_max_rpm":ca["TorqueCurveMaxRPM"],"reference_max_rpm":cb["TorqueCurveMaxRPM"],
             "sampling_domains_differ":(ta["NumTorqueValues"],ca["TorqueCurveMaxRPM"]) != (tb["NumTorqueValues"],cb["TorqueCurveMaxRPM"]),
             "common_index_value_differences":sum(not cal.equal(ta["v"+str(i)],tb["v"+str(i)])
                                                  for i in range(min(ta["NumTorqueValues"],tb["NumTorqueValues"]))),
             "warning":"Raw table/index comparison only; solver RPM interpolation and zero-throttle shape equivalence not verified."}
    known = set(cal.fields36())
    baseline_comp = comps.get("baseline",{"differences":[]})
    novel = [f for f in baseline_comp["differences"] if f["category"]=="physics" and
             (f["role"],f.get("column")) not in known]
    return {"variant_review_required":bool(variant),"variant_changes":variant,
            "stock_role_changes":missing,"torque_domain":curve,"differences_outside_original_36":novel,
            "compatibility":compatibility.audit(source,reference)}


def comparison_strata(cars, modes):
    """Keep raw totals and report explicitly named, overlapping audit strata."""
    audited = [car for car in cars if car.get("diagnostics",{}).get("compatibility")]
    strata = {
        "all_attempted": cars,
        "same_specification": [car for car in audited if car["diagnostics"]["compatibility"]["pairing"]["eligible"]],
        "same_specification_domain_and_roles": [car for car in audited if
            car["diagnostics"]["compatibility"]["pairing"]["eligible"] and
            car["diagnostics"]["compatibility"]["torque_domain"]["same_declared_domain"] and
            not car["diagnostics"]["compatibility"]["stock_role_changes"]],
        "requires_manual_review": [car for car in audited if car["diagnostics"]["compatibility"]["requires_manual_review"]],
    }
    result = {}
    for name, members in strata.items():
        stats = {}
        for mode in modes:
            completed = [r["modes"][mode] for r in members if mode in r.get("modes",{}) and
                         "physics_fields" in r["modes"][mode]]
            stats[mode] = {"completed":len(completed), **{
                key:sum(r[key] for r in completed) for key in
                ("physics_fields","physics_matches","physics_differences","structure_differences")}}
        result[name] = {"attempted":len(members),"media_names":[r["media_name"] for r in members],"modes":stats}
    return {"strata":result,"unaudited_media_names":[car["media_name"] for car in cars if car not in audited],
            "policy":"Overlapping descriptive strata; all-attempted raw totals retained. Same specification does not exclude mass-review cases or establish runtime equivalence."}


def aggregate(cars, modes=None):
    modes = modes or MODES
    output = {"attempted_cars":len(cars),"modes":{},"failures":[]}
    novel = defaultdict(list)
    for car in cars:
        for field in car.get("diagnostics",{}).get("differences_outside_original_36",[]):
            column = field["column"]
            key = (field["role"],"active_samples" if re.fullmatch(r"v\d+",column) else column)
            novel[key].append({"media_name":car["media_name"],**field})
    output["new_differences"] = [
        {"role":role,"column":col,"cars":len({f["media_name"] for f in fields}),"examples":fields[:5]}
        for (role,col),fields in sorted(novel.items(),key=lambda x:(-len({f["media_name"] for f in x[1]}),x[0]))]
    for car in cars:
        if "failure" in car:
            output["failures"].append({k:v for k,v in car.items() if k!="transitions"})
        for mode,stats in car.get("modes",{}).items():
            if "failure" in stats or not stats.get("validation_passed"):
                output["failures"].append({"media_name":car["media_name"],"mode":mode,
                                           "failure":stats.get("failure",stats.get("validation_issues"))})
    for mode in modes:
        completed = [(car,car.get("modes",{}).get(mode)) for car in cars]
        good = [(car,stats) for car,stats in completed if stats and "failure" not in stats and "physics_fields" in stats]
        total = {"completed":len(good), "physics_fields":sum(s["physics_fields"] for _,s in good),
                 "structural_validation_passed":sum(s["validation_passed"] for _,s in good),
                 "warning_cars":[car["media_name"] for car,s in good if s["validation_warnings"]],
                 "physics_matches":sum(s["physics_matches"] for _,s in good),
                 "physics_differences":sum(s["physics_differences"] for _,s in good),
                 "structure_differences":sum(s["structure_differences"] for _,s in good)}
        changed = [t for car,_ in good for t in car["transitions"] if t["mode"]==mode]
        total["changed_field_outcomes"] = dict(Counter(t["result"] for t in changed))
        refined = [t for car,_ in good for t in car.get("refinement_deltas",[]) if t["mode"]==mode]
        total["refinement_vs_previous_mode"] = dict(Counter(t["result"] for t in refined))
        total["regression_cars_vs_previous_mode"] = [
            car["media_name"] for car,_ in good if any(t["mode"]==mode and t["result"]=="regressed"
                                                      for t in car.get("refinement_deltas",[]))]
        total["regression_cars"] = [car["media_name"] for car,_ in good
                                  if any(t["mode"]==mode and t["result"]=="regressed" for t in car["transitions"])]
        total["families"] = {}
        for name in sorted({name for _,s in good for name in s["families"]}):
            total["families"][name] = {key:sum(s["families"].get(name,{}).get(key,0) for _,s in good)
                                      for key in ("fields","matched","different")}
        output["modes"][mode] = total
    output["comparison_strata"] = comparison_strata(cars,modes)
    return output


def report(panel, cars, summary, rules):
    modes = tuple(summary["modes"])
    lines = ["# Benchmark converter FM3 → FM4: 30 mobil", "",
             "Panel dipilih dari metadata sumber sebelum melihat hasil konversi lengkap. Semua 30 mobil "
             "berasal dari split validation sebelumnya dan tidak masuk fitting 236 mobil. "
             "Validation sudah dipakai dalam studi terdahulu: ini benchmark integrasi lebih luas, bukan "
             "test set independen baru. Profil awal dibekukan. Aturan tambahan ditemukan setelah "
             "benchmark awal, lalu dipasang dari fitting training dan evaluasi validation lama; "
             "hasil refined adalah evaluasi adaptif, bukan pengujian buta.", "",
             f"Cakupan: tahun {panel['year_range'][0]}–{panel['year_range'][1]}, {panel['makes']} merek; "
             f"penggerak `{panel['coverage']['drive']}`, posisi mesin `{panel['coverage']['placement']}`. "
             "Terdapat rotary, diesel balap, supercharger, turbo dan naturally aspirated. "
             "Tidak mencakup rear-engine, EV, seluruh DLC/TU, upgrade non-stock atau swaps.", "",
             "Seluruh kolom pada graph fisika stock yang diekstrak dibandingkan, termasuk body, engine, "
             "drivetrain, torque aktif, aero, brakes, suspensi, ban dan kontrol. Kurva ban global FM4 yang "
             "dipilih dibandingkan terpisah. Asset/collision/model dan handling runtime tidak diuji. "
             "Skor jumlah kolom bukan persentase kesamaan handling; sampel torque dan batas tuning "
             "yang berkorelasi dapat memperbesar jumlah selisih.", "",
             "| Mode | Dibandingkan / struktur valid | Kolom fisika | Cocok | Berbeda | Struktur hilang |",
             "|---|---:|---:|---:|---:|---:|"]
    for mode,s in summary["modes"].items():
        lines.append(f"| {mode} | {s['completed']}/30 / {s['structural_validation_passed']} | {s['physics_fields']} | {s['physics_matches']} | "
                     f"{s['physics_differences']} | {s['structure_differences']} |")
    lines += ["", "Conservative memakai lima aturan steering/ABS. Experimental juga memakai prediksi "
              "grip/CG dan profil suspensi yang sebelumnya gagal ambang generalisasi; tidak dipromosikan "
              "menjadi default. Refined menambahkan lookup pengereman, camber independen dan front toe "
              "sesuai gerbang masing-masing. Jumlah field membaik/memburuk membandingkan error terhadap baseline, "
              "tanpa merata-ratakan satuan fisika yang berbeda.", "",
              "## Hasil per mobil", "",
              "| Mobil | Tahun | Drive / posisi | "+" | ".join(modes)+" |",
              "|---|---:|---|"+"---:|"*len(modes)]
    by_name = {r["media_name"]:r for r in cars}
    for entry in panel["cars"]:
        result = by_name[entry["media_name"]]
        values = [result.get("modes",{}).get(m,{}).get("physics_differences","GAGAL") for m in modes]
        lines.append(f"| {entry['media_name']} | {entry['year']} | {entry['drive']} / {entry['placement']} | "
                     +" | ".join(map(str,values))+" |")
    lines += ["", "## Selisih per kelompok", "",
              "| Kelompok | "+" | ".join(modes)+" |",
              "|---|"+"---:|"*len(modes)]
    names = sorted({n for s in summary["modes"].values() for n in s["families"]})
    for n in names:
        lines.append(f"| {n} | "+" | ".join(str(summary["modes"][m]["families"].get(n,{}).get("different",0)) for m in modes)+" |")
    lines += ["", "## Perubahan error dari baseline", ""]
    for m in modes[1:]:
        s = summary["modes"][m]
        lines.append(f"- {m}: `{s['changed_field_outcomes']}`; mobil dengan sedikitnya satu kolom memburuk: "
                     +", ".join(s["regression_cars"])+".")
        if m.startswith(("refined","next")):
            lines.append(f"  Perubahan terhadap tahap sebelumnya pada mode yang sama: `{s['refinement_vs_previous_mode']}`.")
    if any(k in rules for k in NEXT_KEYS):
        lines += ["", "Mode `next` mengganti prediksi suspensi lama dengan profil baru; abstention "
                  "mempertahankan nilai FM3, tanpa fallback ke aturan lama yang ditolak. "
                  "Aturan transmisi tambahan hanya diterapkan sesuai gerbang profilnya. "
                  "Semua mode sebelumnya tetap memakai aturan semula. Laporan model di direktori "
                  "studi menjelaskan CV, pengecualian training, dan validation yang digunakan kembali.", ""]
    lines += ["", "## Audit pasangan dan strata pembanding", "",
              "Semua mobil tetap masuk total utama. Strata di bawah saling tumpang tindih; "
              "tidak dijumlahkan. Same-spec hanya lolos pemeriksaan identitas/konfigurasi dan displacement; "
              "perubahan massa tetap diberi review. Domain sama belum membuktikan interpolasi runtime sama.", "",
              "| Strata | Mobil | "+" | ".join(modes)+" |",
              "|---|---:|"+"---:|"*len(modes)]
    for name,stratum in summary["comparison_strata"]["strata"].items():
        lines.append(f"| {name} | {stratum['attempted']} | "+" | ".join(
            str(stratum["modes"][m]["physics_differences"]) for m in modes)+" |")
    lines += ["", "Jumlah di tabel adalah selisih kolom fisika mentah. Pada domain torque berbeda, "
              "nilai indeks tersebut tidak menunjukkan error pada RPM identik. Tidak dilakukan resampling "
              "atau penambahan stock restrictor tanpa bukti yang memadai.", ""]
    lines += ["", "## Aturan tambahan dan dukungannya", "",
              "| Aturan | Nilai sumber → prediksi | Mobil training | Mobil validation cocok / diuji | Diterima conservative |",
              "|---|---|---:|---:|---|"]
    for entry in rules.get("benchmark_refinements",{}).get("entries",[]):
        lines.append(f"| {entry['family']} | {entry['source']} → {entry['value']} | {entry['training_cars']} | "
                     f"{entry['validation_matching_cars']}/{entry['validation_cars']} | {entry['accepted']} |")
    lines += ["", "Camber hanya untuk suspensi independen dengan nilai sumber 0. Dukungan dihitung per "
              "mobil, bukan per axle/kolom. Pengereman 1,03 → 1,005 masih kurang jumlah validation; "
              "1,05 → 1,01 memiliki pengecualian Audi R8 V10 2010, yang targetnya 1,005. "
              "Keduanya dan front toe tetap eksperimen meski cocok pada panel 30 mobil.", "",
              "## Selisih baru di luar 36 kolom Toyota", "",
              "| Kolom / kelompok | Mobil berbeda pada baseline |", "|---|---:|"]
    for row in summary["new_differences"]:
        lines.append(f"| {row['role']}.{row['column']} | {row['cars']} |")
    lines += ["", "## Temuan integrasi dan aturan yang perlu diperbaiki", "",
              "- **Validasi tuning stock:** nilai Def di luar rentang Min–Max yang diwarisi persis dari "
              "sumber sekarang dicatat sebagai peringatan, bukan di-clamp. Rentang terbalik atau "
              "pelanggaran baru tetap gagal. Audi R10 memiliki kondisi ini pada kedua game; perlu uji runtime.",
              "- **Pencocokan varian:** ID/nama/tahun/merek sama belum menjamin spesifikasi mesin sama. "
              "Perbedaan massa, silinder dan displacement ditandai untuk ditinjau; mobilnya tidak dibuang "
              "dari hasil benchmark.",
              "- **Suspensi:** pemilihan tingkat dan rounding perlu diperbaiki. Race dengan tuning "
              "adjustable sering tidak tercakup; aturan fixed Min=Def=Max tidak boleh diterapkan sembarang.",
              "- **Drivetrain/aero:** inertia transmisi, final drive dan aero balap memiliki perubahan "
              "per mobil; tidak diberi faktor universal. Gearbox dengan level/jumlah gear sama juga "
              "memiliki delta inertia berbeda pada training.",
              "- **Kurva/part mesin:** active sample count/RPM domain berbeda dan stock restrictor baru "
              "harus ditangani sebagai perubahan representasi/komponen. Tidak mengisi part dengan "
              "menyalin target mobil pembanding.",
              "- **CG, tank dan compound:** estimasi CG belum exact, tangki tetap memerlukan spesifikasi "
              "independen, dan pemilihan compound masih perlu model atau data tambahan.",
              "- **Klasifikasi laporan:** EngineGraphingMaxTorque/Power dipisahkan sebagai metadata "
              "grafik, PartManufacturerID sebagai metadata part; semua nilainya tetap ada di comparator.", ""]
    for car in cars:
        d = car.get("diagnostics",{})
        if d.get("variant_review_required"):
            lines.append(f"- Review varian `{car['media_name']}`: `{json.dumps(d['variant_changes'])}`.")
        if d.get("stock_role_changes"):
            lines.append(f"- Stock role `{car['media_name']}`: `{json.dumps(d['stock_role_changes'])}`.")
        if d.get("torque_domain",{}).get("sampling_domains_differ"):
            lines.append(f"- Domain torque `{car['media_name']}`: `{json.dumps(d['torque_domain'])}`.")
    if summary["failures"]:
        lines += ["", "## Kegagalan yang tetap dihitung", ""]
        for e in summary["failures"]:
            lines.append(f"- {e['media_name']}: {e.get('stage',e.get('mode'))}: `{e['failure']}`")
    lines += ["", "File per mobil memuat seluruh kandidat SQLite, source/reference IR, comparison setiap "
              "kolom, dependensi ban, mapping, asumsi dan perubahan kalibrasi. `selection.json` dan "
              "`rules_frozen.json` tersimpan sebelum benchmark. `manifest.json` mencatat hash sumber "
              "sebelum/sesudah dan semua artefak.", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out",type=Path,required=True)
    parser.add_argument("--rules",type=Path,required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    if out.exists():
        parser.error("Use a new output directory")
    for p in (c.FM3_DEFAULT,c.FM4_DEFAULT):
        root = p.resolve().parent.parent.parent
        if out==root or root in out.parents:
            parser.error("Output must be outside game directories")
    before = {str(p):c.sha(p) for p in (c.FM3_DEFAULT,c.FM4_DEFAULT)}
    rules = json.loads(args.rules.read_text(encoding="utf-8"))
    out.mkdir(parents=True)
    with closing(c.connect(c.FM3_DEFAULT)) as src, closing(c.connect(c.FM4_DEFAULT)) as dst:
        panel = selection(cal.collect(src,dst))
        c.dump(out/"selection.json",panel)
        c.dump(out/"rules_frozen.json",rules)
        cars = []
        for i,car in enumerate(panel["cars"]):
            result = run_car(src,dst,rules,car,out/car["media_name"])
            cars.append(result)
            print(json.dumps({"progress":i+1,"car":car["media_name"],"failure":result.get("failure"),
                              "differences":{m:r.get("physics_differences",r.get("failure"))
                                             for m,r in result.get("modes",{}).items()}}),flush=True)
    summary = aggregate(cars,modes_for(rules))
    c.dump(out/"results.json",cars)
    c.dump(out/"summary.json",summary)
    (out/"REPORT.md").write_text(report(panel,cars,summary,rules),encoding="utf-8")
    after = {str(p):c.sha(p) for p in (c.FM3_DEFAULT,c.FM4_DEFAULT)}
    if before!=after:
        raise c.MappingError("Source database changed during benchmark")
    c.dump(out/"manifest.json",{"sources_before":before,"sources_after":after,"sources_unchanged":True,
                               "rules_input_sha256":c.sha(args.rules),"runtime_tested":False,
                               "code_sha256":{n:c.sha(Path(__file__).with_name(n)) for n in
                                              ("benchmark.py","converter.py","calibration.py","remaining.py","refinements.py","compatibility.py")
                                              +tuple(k+".py" for k in NEXT_KEYS if k in rules)},
                               "outputs":{str(p.relative_to(out)):c.sha(p) for p in sorted(out.rglob("*")) if p.is_file()}})
    print(json.dumps({"out":str(out),"summary":summary["modes"],"failures":summary["failures"]},indent=2))


if __name__ == "__main__":
    main()
