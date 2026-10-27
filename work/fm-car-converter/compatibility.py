"""Post-conversion compatibility evidence, never a source of candidate values.

The pairing predicate is also usable during training-data curation. It is not
an inference-time predictor: a new FM3-only car has no native FM4 reference.
"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import closing
import math
from pathlib import Path

import converter as c


RESTRICTOR = "List_UpgradeEngineRestrictorPlate"
PAIR_POLICY = {
    "displacement_relative_difference_exclusion": 0.01,
    "mass_relative_difference_review": 0.05,
    "enum_comparison": "FM3/FM4 shared registry IDs; verify registry semantics for other versions",
    "use": "Training-pair curation and post-conversion audit, never target-dependent inference",
}


def row(graph, role):
    """Accept both converter graphs and calibration cohort records."""
    node = graph.get("nodes", {}).get(role, {})
    return node.get("row", node)


def close(a, b):
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return math.isclose(a, b, rel_tol=1e-6, abs_tol=1e-6)
    return a == b


def relative_difference(a, b):
    return abs(a-b) / max(abs(a), abs(b), 1e-12)


def pair_eligibility(source, reference):
    """Conservative specification screen; never removes a benchmark result.

    A mass change alone is a review reason, since it can be a native calibration
    correction. Categorical engine/drivetrain mismatches or >1% displacement
    changes prevent treating the pair as the same-spec conversion target.
    """
    excluded, review, missing = [], [], []
    fields = {
        "car": ("MediaName", "Year", "MakeID", "DriveTypeID", "EnginePlacementID", "AspirationTypeId"),
        "engine": ("ConfigID", "CylinderID", "Rotary", "Diesel", "AspirationID_Stock"),
    }
    for role, columns in fields.items():
        a, b = row(source, role), row(reference, role)
        for col in columns:
            if col not in a or col not in b:
                missing.append({"role": role, "column": col})
            elif a[col] != b[col]:
                excluded.append({"role": role, "column": col, "source": a[col],
                                 "reference": b[col], "reason": "identity_or_configuration_mismatch"})
    for role, column in (("car", "Displacement"), ("List_UpgradeCarBodyWeight", "Mass")):
        a, b = row(source, role).get(column), row(reference, role).get(column)
        if not all(isinstance(v, (int, float)) and math.isfinite(v) and v > 0 for v in (a, b)):
            missing.append({"role": role, "column": column})
            continue
        if close(a, b):
            continue
        delta = relative_difference(a, b)
        entry = {"role": role, "column": column, "source": a, "reference": b,
                 "relative_difference": delta}
        if column == "Displacement" and delta > PAIR_POLICY["displacement_relative_difference_exclusion"]:
            excluded.append({**entry, "reason": "displacement_change_over_policy_limit"})
        elif column == "Mass" and delta > PAIR_POLICY["mass_relative_difference_review"]:
            review.append({**entry, "reason": "large_mass_change_requires_review"})
        else:
            review.append({**entry, "reason": "specification_value_changed"})
    return {"eligible": not excluded and not missing, "exclusion_reasons": excluded,
            "review_reasons": review, "missing_required_fields": missing, "policy": dict(PAIR_POLICY)}


def curve_description(graph):
    torque = row(graph, "torque.full")
    camshaft = row(graph, "List_UpgradeEngineCamshaft")
    issues = []
    count = torque.get("NumTorqueValues")
    valid_count = isinstance(count, int) and not isinstance(count, bool) and count >= 2
    if not valid_count:
        issues.append("invalid_or_missing_active_sample_count")
    samples = []
    if valid_count:
        for i in range(count):
            value = torque.get(f"v{i}")
            if not isinstance(value, (int, float)) or not math.isfinite(value):
                issues.append(f"missing_or_nonfinite_active_sample_v{i}")
            else:
                samples.append(value)
    cam_count = camshaft.get("NumRPMEntriesArray")
    if cam_count != count:
        issues.append("camshaft_count_disagrees_with_curve_count")
    max_rpm = camshaft.get("TorqueCurveMaxRPM")
    if not isinstance(max_rpm, (int, float)) or not math.isfinite(max_rpm) or max_rpm <= 0:
        issues.append("invalid_or_missing_max_rpm")
    return {"active_count": count, "camshaft_count": cam_count, "max_rpm": max_rpm,
            "redline_rpm": camshaft.get("RedlineRPM"), "start_rpm": camshaft.get("StartRPM"),
            "torque_scale": torque.get("TorqueScale"), "samples": samples, "issues": issues}


def torque_audit(source, reference):
    a, b = curve_description(source), curve_description(reference)
    same_domain = not a["issues"] and not b["issues"] and all(
        a[k] == b[k] for k in ("active_count", "camshaft_count", "max_rpm"))
    domain_changes = [{"field": key, "source": a[key], "reference": b[key]}
                      for key in ("active_count", "camshaft_count", "max_rpm")
                      if a[key] != b[key]]
    index_only = []
    if not a["issues"] and not b["issues"]:
        for i, (av, bv) in enumerate(zip(a["samples"], b["samples"])):
            if not close(av, bv):
                index_only.append({"index": i, "source": av, "reference": bv})
    return {
        "source": {k: v for k, v in a.items() if k != "samples"},
        "reference": {k: v for k, v in b.items() if k != "samples"},
        "same_declared_domain": same_domain,
        "sampling_domains_differ": bool(domain_changes),
        "domain_changes": domain_changes,
        "same_index_differences": index_only,
        "same_index_compared": min(len(a["samples"]), len(b["samples"])) if not a["issues"] and not b["issues"] else 0,
        "comparison_interpretation": ("same_declared_domain_array_comparison"
                                      if same_domain else "index_differences_are_not_rpm_aligned_physics_errors"),
        "runtime_interpolation_verified": False,
        "resampling_performed": False,
        "warning": "No assumption about solver sample spacing, interpolation, endpoint handling, or zero-throttle shape.",
    }


def audit(source_graph, reference_graph):
    """Pure audit: does not mutate graphs or supply native calibration to fitting."""
    a, b = source_graph.get("nodes", {}), reference_graph.get("nodes", {})
    role_changes = [{"role": role, "source_present": role in a, "reference_present": role in b}
                    for role in sorted(a.keys() ^ b.keys()) if role != "torque.zero"]
    pair = pair_eligibility(source_graph, reference_graph)
    curves = torque_audit(source_graph, reference_graph)
    return {"media_name": source_graph.get("media_name", row(source_graph, "car").get("MediaName")),
            "pairing": pair, "variant_review_required": not pair["eligible"] or bool(pair["review_reasons"]),
            "stock_role_changes": role_changes, "torque_domain": curves,
            "requires_manual_review": (not pair["eligible"] or bool(pair["review_reasons"])
                                       or bool(role_changes) or not curves["same_declared_domain"]),
            "candidate_mutated": False,
            "expected_representation_changes": {"FM3_separate_zero_throttle_curve": "torque.zero" in a,
                                                "FM4_separate_zero_throttle_curve": "torque.zero" in b}}


def restrictor_study(source_db, target_db, audited_pairs):
    """Evidence only: a neutral payload does not establish that a part is needed."""
    source_rows = c.rows(source_db, RESTRICTOR, "IsStock=1")
    target_rows = c.rows(target_db, RESTRICTOR, "IsStock=1")
    target_by_engine = {r["EngineID"]: r for r in target_rows}
    source_by_engine = {r["EngineID"]: r for r in source_rows}
    missing, cases = [], []
    for pair in audited_pairs:
        source, target = pair["source_record"], pair["target_record"]
        a = source_by_engine.get(source["engine_id"])
        b = target_by_engine.get(target["engine_id"])
        case = {"media_name": source["media_name"], "split": pair["split"],
                "source_car_type": source["nodes"]["car"]["CarTypeID"],
                "source_aspiration": source["nodes"]["car"]["AspirationTypeId"],
                "source_present": a is not None, "target_present": b is not None,
                "target_torque_scale": b.get("TorqueScale") if b else None}
        cases.append(case)
        if a is None and b is not None:
            missing.append({**case, "target_payload": {k: v for k, v in b.items() if k not in ("Id", "EngineID")}})
    nonneutral = [r for r in target_rows if not close(r["TorqueScale"], 1.0) or not close(r["MassDiff"], 0.0)]
    training_absent = [r for r in cases if r["split"] == "training" and not r["source_present"]]
    by_source_type = {}
    for key in sorted({(r["source_car_type"], r["source_aspiration"]) for r in training_absent}):
        group = [r for r in training_absent if (r["source_car_type"], r["source_aspiration"]) == key]
        by_source_type[str(key)] = {"cars": len(group), "target_part_present": sum(r["target_present"] for r in group)}
    return {"source_stock_rows": len(source_rows), "target_stock_rows": len(target_rows),
            "target_nonneutral_stock_rows": nonneutral, "missing_source_stock_roles": missing,
            "source_absent_training_by_car_type_aspiration": by_source_type,
            "all_pair_presence_cases": cases, "synthesis_accepted": False,
            "recommendation": "Abstain. Optional-part presence is not implied by a neutral stock payload; "
                              "FM4 also contains non-neutral stock restrictors. No mandatory row is synthesized.",
            "independent_spec_required": "Determine restrictor availability and intended stock restriction for the imported vehicle."}


def report(results, restrictors, summary):
    lines = ["# Compatibility audit FM3 / FM4", "",
             "Audit seluruh 309 pasangan pada cohort terdahulu. Ini audit sesudah konversi/pencocokan, "
             "bukan pengujian handling atau test set independen baru. Nilai FM4 pembanding tidak digunakan "
             "untuk mengisi kandidat.", "",
             f"- Pasangan lolos pemeriksaan spesifikasi: {summary['eligible_pairs']}/{summary['pairs']}.",
             f"- Domain torque berbeda: {summary['different_torque_domains']}.",
             f"- Pasangan memiliki stock role berbeda: {summary['changed_stock_roles']}.",
             f"- Pasangan membutuhkan review nilai spesifikasi: {summary['specification_review_pairs']}.", "",
             "## Pasangan yang tidak boleh dianggap target spesifikasi identik", ""]
    for result in results:
        p = result["pairing"]
        if not p["eligible"]:
            lines += [f"- `{result['media_name']}` ({result['split']}): `{p['exclusion_reasons']}`."]
    lines += ["", "Exclusion hanya untuk fitting aturan yang mengasumsikan spesifikasi sama. Mobil tetap "
              "ditampilkan pada benchmark, dengan strata tersendiri; angka benchmark lama tidak dihapus. "
              "Predicate memerlukan dua database untuk kurasi. Pada impor mobil FM3-only tidak ada target "
              "FM4 yang bisa dipakai; jangan menganggap absence warning membuktikan kompatibilitas.", "",
              "## Domain kurva torque", ""]
    for result in results:
        t = result["torque_domain"]
        if t["sampling_domains_differ"] or t["source"]["issues"] or t["reference"]["issues"]:
            lines += [f"- `{result['media_name']}`: `{t['domain_changes']}`; "
                      f"{len(t['same_index_differences'])}/{t['same_index_compared']} nilai indeks berbeda. "
                      "Indeks pada domain berbeda tidak dianggap error fisika pada RPM yang sama."]
    lines += ["", "Tidak dilakukan resampling. Distribusi RPM tiap sampel dan interpolasi engine belum "
              "terverifikasi, sehingga NumTorqueValues/MaxRPM tidak cukup untuk membuktikan kurva setara.", "",
              "## Stock restrictor", "",
              f"FM3 memiliki {restrictors['source_stock_rows']} stock rows; FM4 "
              f"{restrictors['target_stock_rows']}. {len(restrictors['target_nonneutral_stock_rows'])} row "
              "FM4 memiliki TorqueScale atau MassDiff non-neutral. Kehadiran part tidak dapat disimpulkan "
              "dari payload neutral saja.", ""]
    for case in restrictors["missing_source_stock_roles"]:
        lines += [f"- `{case['media_name']}` ({case['split']}): tidak ada stock restrictor FM3; "
                  f"FM4 `{case['target_payload']}`."]
    lines += ["", "Synthesizing restrictor ditolak. Pola source CarType=3 dan aspiration=1 saat restrictor "
              "sumber tidak ada hanya didukung dua mobil training, keduanya Viper; tiga validation juga "
              "memiliki part FM4, tetapi ini dukungan kecil dan berkorelasi. CarType dan aspiration "
              "belum membuktikan row wajib ada pada impor lain, dan metadata manufacturer juga "
              "tidak konstan. Converter harus mencatat perbedaan "
              "komponen sebagai review, mempertahankan source stock graph, dan meminta bukti spesifikasi "
              "independen bila availability/restriction hendak direkonstruksi.", "",
              "## Artefak", "", "`audit.json` menyimpan semua pasangan; `restrictor_study.json` memuat "
              "distribusi presence dan payload; `manifest.json` merekam hash sumber sebelum/sesudah. "
              "Registry engine/cylinder/drive/placement yang dipakai predicate diverifikasi pada audit run. "
              "Audit tidak membuktikan kesamaan asset, collision, atau handling runtime.", ""]
    return "\n".join(lines)


def verify_registry_domains(src, dst):
    checks = {}
    semantic_columns = {"List_Cylinders": ("Number", "Rotors"), "List_EngineConfig": ("EngineConfig",),
                        "List_DriveType": ("DriveType",), "List_EnginePlacement": ("EnginePlacement",),
                        "List_Aspiration": ("Aspiration",)}
    for table, columns in semantic_columns.items():
        a, b = c.rows(src, table), c.rows(dst, table)
        primary = c.pk(c.schema(src)[table])
        lookup = {r[primary]: r for r in b}
        # KeyPartEnum is an implementation pointer that shifts between games;
        # classification is checked by reviewed semantic fields, not that pointer.
        differences = [{"id": r[primary], "source": r, "target": lookup.get(r[primary])}
                       for r in a if r[primary] not in lookup or any(
                           r[col] != lookup[r[primary]].get(col) for col in columns)]
        checks[table] = {"semantic_columns": columns, "compatible_source_ids": not differences,
                         "differences": differences}
    return checks


def main():
    import calibration as cal

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    if out.exists():
        parser.error("Use a new output directory")
    for path in (c.FM3_DEFAULT, c.FM4_DEFAULT):
        game_root = path.resolve().parent.parent.parent
        if game_root == out or game_root in out.parents:
            parser.error("Output must be outside game directories")
    before = {str(path): c.sha(path) for path in (c.FM3_DEFAULT, c.FM4_DEFAULT)}
    out.mkdir(parents=True)
    with closing(c.connect(c.FM3_DEFAULT)) as src, closing(c.connect(c.FM4_DEFAULT)) as dst:
        domains = verify_registry_domains(src, dst)
        if not all(item["compatible_source_ids"] for item in domains.values()):
            raise c.MappingError("Registry IDs need semantic normalization before pairing audit")
        cohort = cal.collect(src, dst)
        results, records = [], []
        for pair in cohort["pairs"]:
            name = pair["source"]["media_name"]
            result = audit(c.extract_stock(src, name), c.extract_stock(dst, name))
            result["split"] = pair["split"]
            results.append(result)
            records.append({"source_record": pair["source"], "target_record": pair["target"], "split": pair["split"]})
        restrictors = restrictor_study(src, dst, records)
    summary = {"pairs": len(results), "eligible_pairs": sum(r["pairing"]["eligible"] for r in results),
               "different_torque_domains": sum(r["torque_domain"]["sampling_domains_differ"] for r in results),
               "changed_stock_roles": sum(bool(r["stock_role_changes"]) for r in results),
               "specification_review_pairs": sum(bool(r["pairing"]["review_reasons"]) for r in results),
               "role_change_counts": dict(Counter(change["role"] for r in results for change in r["stock_role_changes"]))}
    c.dump(out / "audit.json", {"summary": summary, "registry_domains": domains, "cars": results})
    c.dump(out / "restrictor_study.json", restrictors)
    (out / "REPORT.md").write_text(report(results, restrictors, summary), encoding="utf-8")
    after = {str(path): c.sha(path) for path in (c.FM3_DEFAULT, c.FM4_DEFAULT)}
    if before != after:
        raise c.MappingError("Source database changed")
    c.dump(out / "manifest.json", {"sources_before": before, "sources_after": after, "sources_unchanged": True,
                                   "code_sha256": c.sha(Path(__file__)), "runtime_tested": False,
                                   "outputs": {p.name: c.sha(p) for p in out.iterdir() if p.is_file()}})
    print(summary)


if __name__ == "__main__":
    main()
