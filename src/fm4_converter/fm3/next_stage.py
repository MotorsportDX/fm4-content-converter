"""Freeze independently studied follow-up profiles and reproduce integration evidence."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

from . import benchmark as b
from . import converter as c


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def previous_arm_replay(previous, current):
    """Compare complete values, not just aggregate scores, for frozen old arms."""
    checks = []
    for media, _ in b.SELECTION:
        for mode in b.MODES:
            for name in ("candidate_ir.json", "comparison.json", "tyre_comparison.json"):
                relative = Path(media)/mode/name
                old, new = previous/relative, current/relative
                equal = old.is_file() and new.is_file() and load(old) == load(new)
                checks.append({"file":relative.as_posix(),"identical":equal})
    return {"passed":all(r["identical"] for r in checks),"checked":len(checks),
            "checks":checks,"previous":str(previous),"current":str(current)}


def text_report(summary, toyota, replay, suspension, drivetrain):
    modes = summary["modes"]
    partial = suspension.get("component_selected_cv",{})
    val = suspension.get("component_validation",{})
    lines = ["# Perbaikan berikutnya converter FM3 → FM4", "",
             "Eksperimen offline terhadap database stock Disc 1. Aturan dipelajari dari training "
             "sebelumnya; validation 73 mobil dan panel 30 dipakai ulang. Hasil ini evaluasi adaptif, "
             "bukan test set independen atau bukti handling runtime.", "",
             "**Keputusan pemakaian:** menjalankan studi ini tidak mengubah profil default. "
             "Peningkatan audit dan pengamanan penerapan aturan digunakan pada converter; "
             "kandidat numerik hanya diterapkan sesuai gerbang masing-masing. "
             "Label `next` menunjukkan urutan eksperimen, bukan jaminan lebih akurat.", "",
             "## Hasil benchmark lengkap", "",
             "| Profil | Selisih fisika sebelumnya | Selisih fisika sekarang | Kolom error membaik / memburuk terhadap tahap sebelumnya |",
             "|---|---:|---:|---|"]
    for base in ("conservative","experimental"):
        old,new = modes["refined_"+base],modes["next_"+base]
        lines.append(f"| {base} | {old['physics_differences']} | {new['physics_differences']} | "
                     f"{new['refinement_vs_previous_mode']} |")
    lines += ["", f"Setiap mode membandingkan {modes['next_experimental']['physics_fields']:,} nilai fisika "
              "dari 30 mobil; 2 stock role target tetap tidak tersedia pada sumber. Raw totals dipertahankan, "
              "termasuk pasangan berbeda spesifikasi dan domain torque. Selisih angka bukan persentase kesamaan handling.",
              f"Reproduksi lima mode lama: {replay['checked']} artefak kandidat/perbandingan identik: **{replay['passed']}**.", "",
              "Jumlah kolom exact dan perubahan besar error adalah dua ukuran berbeda. Estimasi parsial "
              "dapat mendekatkan nilai tanpa menjadi exact; rollback prediksi lama juga dapat menghilangkan "
              "beberapa kecocokan. Semua tradeoff tetap ditampilkan.", ""]
    exp=modes["next_experimental"]
    lines += [f"- Terhadap baseline FM3: `{exp['changed_field_outcomes']}`; "
              f"{len(exp['regression_cars'])} mobil memiliki sedikitnya satu parameter memburuk.",
              f"- Terhadap eksperimen sebelumnya: `{exp['refinement_vs_previous_mode']}`; "
              f"{len(exp['regression_cars_vs_previous_mode'])} mobil memiliki sedikitnya satu parameter memburuk.",
              "- Daftar per mobil, per keluarga, dan setiap parameter ada di `benchmark30/REPORT.md`, "
              "`results.json`, serta `refinement_deltas.json` tiap mobil.", "",
              "## Keputusan aturan", "",
              "**Suspensi:** dalam mode `next`, profil baru menggantikan pemilihan tier lama. Bila abstain, nilai sumber "
              "dipertahankan tanpa fallback. Seluruh kandidat tier gagal gerbang CV. Metode terpisah "
              "hanya mengubah sebagian stiffness fixed Min=Def=Max berdasarkan arah rasio yang konsisten "
              "di training, dengan batas nilai sumber; tidak mengubah suspensi adjustable menjadi fixed.", "",
              f"Partial-component CV: {partial.get('covered')} tercakup, {partial.get('regressed_cars')} mobil "
              f"memburuk; validation: {val.get('covered')} tercakup, {val.get('regressed_cars')} memburuk. "
              f"Gerbang validation diterima: **{suspension.get('component_accepted')}**. "
              "Batas regresi tidak dilonggarkan. Partial estimate tersedia hanya dalam experimental "
              "saat gerbang gagal; conservative/estimated abstain. Dukungan pasangan terkait belum "
              "menjamin independensi seluruh chassis/platform.", "",
              "**Transmisi:** koreksi global ditolak karena dapat merusak nilai FM3 yang sudah cocok. "
              f"Kandidat terpilih `{drivetrain['selected']['name']}` memakai grouping engine/payload/family "
              "pada CV. Dukungan validation lingkup kandidat: "
              f"{drivetrain['validation']['summary'].get('scope_predicted')} mobil. "
              f"Experimental diterima: **{drivetrain['experimental_accepted']}**; "
              f"conservative: **{drivetrain['conservative_accepted']}**. "
              "Tidak ada perubahan inertia ketika gerbang dukungan gagal; final drive dan aero tetap sumber.", "",
              "**Audit kompatibilitas:** perbedaan konfigurasi/displacement, perubahan massa, domain kurva, "
              "dan stock role dicatat sesudah kandidat selesai. Nilai comparator tidak dipakai untuk "
              "mengisi kandidat. Viper GTS-R berbeda spesifikasi; Ferrari 333 SP berbeda jumlah sampel/domain "
              "torque. Raw index difference pada domain berbeda bukan error pada RPM sama. "
              "Restrictor tidak disintesis karena bukti kehadiran/kalibrasinya belum memadai.", "",
              "**Integritas penerapan:** semua proposal diperiksa sebelum ada mutasi; tumpang tindih "
              "kolom, nilai nonfinite, kolom/mapping hilang, atau provenance tidak lengkap menghentikan "
              "penerapan. Mode lama tetap dapat direproduksi.", "",
              "## Toyota 2000GT", "",
              "| Mode | Selisih fisika | Struktur valid |", "|---|---:|---|"]
    for mode, result in toyota.items():
        lines.append(f"| {mode} | {result['differences'].get('physics',0)} | {result['validation_passed']} |")
    lines += ["", "Toyota tetap dikeluarkan dari fitting. Perbandingan seluruh kolom dan kandidat SQLite "
              "tersimpan di `toyota/<mode>/`. Hasil satu mobil tidak dipakai memilih atau memperbaiki model.", "",
              "## Batas dan kelanjutan", "",
              "Prioritas data berikutnya adalah pasangan modern race yang lebih beragam untuk inertia, "
              "serta spesifikasi suspensi independen untuk memisahkan retuning per mobil dari konversi schema. "
              "Seluruh upgrade, swaps, model/collision, packaging DLC dan uji game belum tercakup. "
              "Database game dibuka read-only dan hash sebelum/sesudah diverifikasi. "
              "Kandidat SQLite memakai namespace eksperimen dan belum siap dipasang.", "",
              "Model input, gerbang dan provenance disimpan di `rules.json` serta `manifest.json`; "
              "detail CV/validation berada di direktori studi yang dirujuk manifest.", ""]
    return "\n".join(lines)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-rules",type=Path,required=True)
    parser.add_argument("--suspension-model",type=Path,required=True)
    parser.add_argument("--drivetrain-model",type=Path,required=True)
    parser.add_argument("--previous-benchmark",type=Path,required=True)
    parser.add_argument("--out",type=Path,required=True)
    args=parser.parse_args()
    out=args.out.resolve()
    if out.exists():
        parser.error("Choose a new output directory")
    for db in (c.FM3_DEFAULT,c.FM4_DEFAULT):
        game=db.resolve().parent.parent.parent
        if out==game or game in out.parents:
            parser.error("Output must be outside game directories")
    rules=load(args.base_rules)
    suspension,drivetrain=load(args.suspension_model),load(args.drivetrain_model)
    if "component_validation" not in suspension or not drivetrain.get("validated"):
        parser.error("Both studies must be evaluated before integration")
    rules.update(suspension_v2=suspension,drivetrain_v2=drivetrain)
    before={str(p):c.sha(p) for p in (c.FM3_DEFAULT,c.FM4_DEFAULT)}
    out.mkdir(parents=True)
    c.dump(out/"rules.json",rules)
    print("Frozen profiles; running all 30 cars in seven modes.",flush=True)
    with (out/"benchmark.log").open("w",encoding="utf-8") as log:
        subprocess.run([sys.executable,"-m",__package__+".benchmark",
                        "--rules",str(out/"rules.json"),"--out",str(out/"benchmark30")],
                       stdout=log,stderr=subprocess.STDOUT,check=True)
    summary=load(out/"benchmark30"/"summary.json")
    replay=previous_arm_replay(args.previous_benchmark.resolve(),out/"benchmark30")
    c.dump(out/"previous_arm_replay.json",replay)
    if not replay["passed"] or summary["failures"]:
        raise c.MappingError("Integration failed: inspect replay and benchmark failures")
    toyota={}
    for phase,path in (("refined",args.base_rules),("next",out/"rules.json")):
        for mode in ("conservative","experimental"):
            key=phase+"_"+mode
            toyota[key]=c.run(c.FM3_DEFAULT,c.FM4_DEFAULT,out/"toyota"/key,
                              calibration_rules=path,calibration_mode=mode)
    c.dump(out/"toyota_summary.json",toyota)
    (out/"REPORT.md").write_text(text_report(summary,toyota,replay,suspension,drivetrain),encoding="utf-8")
    after={str(p):c.sha(p) for p in (c.FM3_DEFAULT,c.FM4_DEFAULT)}
    if before!=after:
        raise c.MappingError("Source hashes changed")
    c.dump(out/"manifest.json",{
        "sources_before":before,"sources_after":after,"sources_unchanged":True,
        "runtime_tested":False,"installable":False,"new_independent_validation":False,
        "input_models":{str(p.resolve()):c.sha(p) for p in
                        (args.base_rules,args.suspension_model,args.drivetrain_model)},
        "previous_benchmark":str(args.previous_benchmark.resolve()),
        "code_sha256":{p.name:c.sha(p) for p in sorted(Path(__file__).parent.glob("*.py"))},
        "outputs":{str(p.relative_to(out)):c.sha(p) for p in sorted(out.rglob("*")) if p.is_file()}})
    print(json.dumps({"out":str(out),"replay_identical":replay["passed"],
                      "benchmark_differences":{m:s["physics_differences"] for m,s in summary["modes"].items()},
                      "toyota_differences":{m:r["differences"].get("physics",0) for m,r in toyota.items()}},indent=2))


if __name__=="__main__":
    main()
