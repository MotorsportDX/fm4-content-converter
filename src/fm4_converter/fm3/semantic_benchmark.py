"""Benchmark static-code coordinate policy separately from native calibration fit."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import benchmark as b
from . import converter as c
from . import code_semantics as s
from . import effective_physics as e


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rules",type=Path,required=True)
    parser.add_argument("--previous-benchmark",type=Path,required=True)
    parser.add_argument("--previous-toyota",type=Path,required=True)
    parser.add_argument("--image",type=Path,required=True)
    parser.add_argument("--out",type=Path,required=True)
    args=parser.parse_args()
    out=args.out.resolve()
    if out.exists():
        parser.error("Choose a new output directory")
    for p in (c.FM3_DEFAULT,c.FM4_DEFAULT):
        root=p.resolve().parent.parent.parent
        if out==root or root in out.parents:
            parser.error("Output must be outside source directories")
    image=args.image.read_bytes()
    if c.sha(args.image)!="7a56b178d856c0dabb6d32120de6b5b6d7182a0c35bff836763d08684e3d5c41":
        parser.error("Unsupported executable image for verified instruction slice")
    before={str(p):c.sha(p) for p in (c.FM3_DEFAULT,c.FM4_DEFAULT)}
    out.mkdir(parents=True)
    cars=[]
    for index,(media,_) in enumerate(b.SELECTION+[(c.MEDIA,"original Toyota holdout")]):
        old_folder=args.previous_toyota if media==c.MEDIA else args.previous_benchmark/media/"refined_conservative"
        old_candidate=load(old_folder/"candidate_ir.json")
        prior_comparison=load(old_folder/"comparison.json")
        where=out/media
        result=c.run(c.FM3_DEFAULT,c.FM4_DEFAULT,where,media=media,id_base=c.ID_BASE+1000*index,
                     calibration_rules=args.rules,calibration_mode="conservative",code_semantics=True)
        source,candidate,reference=(load(where/name) for name in ("source_ir.json","candidate_ir.json","reference_fm4_ir.json"))
        eff=load(where/"effective_comparison.json")
        baseline=s.compare_centers(source,old_candidate)
        new=s.inputs(candidate,"fm4")
        oracle=s.run_cg_instruction_slice(image,0x82000000,height=new["height"],
                                         distribution=new["distribution"],front=new["front_height"],rear=new["rear_height"])
        oracle_error=oracle["config_cmheight"]-s.inputs(source,"fm3")["height"]
        c.dump(where/"binary_slice_check.json",{**oracle,"source_height":s.inputs(source,"fm3")["height"],
                                               "error":oracle_error,"within_tolerance":abs(oracle_error)<1e-6})
        # Existing row IDs can differ by namespace; compare calibration fields.
        changed=[]
        mappings={(m["role"],m["target_column"]):m for m in load(where/"mapping.json")["columns"]}
        for role,node in candidate["nodes"].items():
            old=old_candidate["nodes"][role]
            for col,val in node["row"].items():
                mapping=mappings[(role,col)]
                if mapping["action"] in ("allocate_primary_key","remap_reference"):
                    continue
                if old["row"].get(col)!=val:
                    changed.append({"role":role,"column":col,"before":old["row"].get(col),"after":val})
        allowed={(s.WEIGHT,"CMHeight"),("car","FrontStockRideHeight"),("car","RearStockRideHeight")}
        if any((v["role"],v["column"]) not in allowed for v in changed):
            raise c.MappingError("Unexpected changes outside coordinate policy: "+media)
        record={"media_name":media,"validation_passed":result["validation_passed"],
                "before_native_physics_differences":prior_comparison["differences_by_category"].get("physics",0),
                "after_native_physics_differences":result["differences"].get("physics",0),
                "before_center_error_vs_source":baseline["candidate_minus_source"],
                "after_center_error_vs_source":eff["centers"]["candidate_minus_source"],
                "binary_slice_error_vs_source":oracle_error,
                "center_source_preserved":eff["centers"]["source_preserved_within_tolerance"],
                "geometry_source_preserved":eff["suspension_geometry_vs_source"]["preserved"],
                "normalized_suspension_vs_source":eff["suspension_vs_source"]["counts"],
                "source_cmheight":s.row(source,s.WEIGHT)["CMHeight"],"converted_cmheight":new["height"],
                "native_fm4_cmheight":s.row(reference,s.WEIGHT)["CMHeight"],
                "native_center_comparison":eff["centers"].get("candidate_minus_native"),
                "changed_fields":changed}
        cars.append(record)
        print(json.dumps({"progress":index+1,"car":media,"source_center_preserved":record["center_source_preserved"],
                          "raw_native_differences":record["after_native_physics_differences"]}),flush=True)
    panel=cars[:30]
    summary={
        "cars":len(cars),"benchmark_cars":30,"toyota_separate":True,
        "source_center_preserved":sum(r["center_source_preserved"] for r in cars),
        "source_geometry_preserved":sum(r["geometry_source_preserved"] for r in cars),
        "binary_slice_within_tolerance":sum(abs(r["binary_slice_error_vs_source"])<1e-6 for r in cars),
        "max_binary_slice_absolute_error":max(abs(r["binary_slice_error_vs_source"]) for r in cars),
        "normalized_suspension_compared":sum(r["normalized_suspension_vs_source"]["compared"] for r in cars),
        "normalized_suspension_equal":sum(r["normalized_suspension_vs_source"]["equal"] for r in cars),
        "panel_native_differences_before":sum(r["before_native_physics_differences"] for r in panel),
        "panel_native_differences_after":sum(r["after_native_physics_differences"] for r in panel),
        "runtime_tested":False,"independent_test_set":False,
        "validation_target":"Preserve traced FM3 coordinate and coefficients under explicit unchanged-geometry/stock-part assumptions; native FM4 values remain a separate calibration comparison"}
    c.dump(out/"results.json",cars)
    c.dump(out/"summary.json",summary)
    lines=["# Benchmark adapter koordinat dari kode", "",
           "30 mobil panel lama + Toyota terpisah. Prediksi tidak membaca kalibrasi mobil FM4 pembanding. "
           "Seluruh kandidat memakai refined_conservative dan adapter koordinat; model CG/tier empiris tidak dipakai.", "",
           f"- Input pusat massa komponen utama terjaga: **{summary['source_center_preserved']}/31**.",
           f"- Micro-check 11 instruksi FM4 asli: **{summary['binary_slice_within_tolerance']}/31**, "
           f"error maksimum `{summary['max_binary_slice_absolute_error']}` (toleransi 1e-6).",
           f"- Koefisien suspensi ternormalisasi cocok dengan FM3: **{summary['normalized_suspension_equal']}/"
           f"{summary['normalized_suspension_compared']}**. Kesamaan faktor massa runtime belum diukur.",
           f"- Selisih kolom terhadap native FM4 pada panel 30: **{summary['panel_native_differences_before']} → "
           f"{summary['panel_native_differences_after']}**. Ini ukuran berbeda dari pelestarian representasi FM3.", "",
           "Pemeriksaan instruksi adalah evaluator aritmetika kecil atas byte image, tanpa menjalankan game. "
           "Belum menguji solver lengkap, asset/collision, final aggregate CG, title update, atau handling.", "",
           "| Mobil | CMHeight FM3 | Konversi | Native FM4 | Error Y sebelum → sesudah terhadap FM3 | Native fisika sebelum → sesudah |",
           "|---|---:|---:|---:|---:|---:|"]
    for r in cars:
        lines.append(f"| {r['media_name']} | {r['source_cmheight']} | {r['converted_cmheight']:.9g} | "
                     f"{r['native_fm4_cmheight']} | {r['before_center_error_vs_source']:.8g} → "
                     f"{r['after_center_error_vs_source']:.8g} | {r['before_native_physics_differences']} → "
                     f"{r['after_native_physics_differences']} |")
    lines+=["", "Adapter v2 mempertahankan input CMHeight dan memakai MaxRideHeight sumber untuk tinggi "
            "referensi Data_Car. Batas extension yang dipertahankan diaudit terhadap seluruh rentang spring "
            "part stock terpilih. Seluruh perubahan, evaluator efektif, micro-check dan SQLite tersedia per mobil.", ""]
    (out/"REPORT.md").write_text("\n".join(lines),encoding="utf-8")
    after={str(p):c.sha(p) for p in (c.FM3_DEFAULT,c.FM4_DEFAULT)}
    if before!=after:
        raise c.MappingError("Source database changed")
    c.dump(out/"manifest.json",{"sources_before":before,"sources_after":after,"sources_unchanged":True,
                               "rules_sha256":c.sha(args.rules),"image_sha256":c.sha(args.image),
                               "code_sha256":{p.name:c.sha(p) for p in sorted(Path(__file__).parent.glob("*.py"))},
                               "outputs":{str(p.relative_to(out)):c.sha(p) for p in sorted(out.rglob("*")) if p.is_file()}})
    print(json.dumps(summary,indent=2))


if __name__=="__main__":
    main()
