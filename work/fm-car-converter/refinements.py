"""Post-benchmark hypotheses. Train-only lookup fit, reused validation gates."""
from __future__ import annotations
import argparse
from collections import Counter
from contextlib import closing
import copy
import json
from pathlib import Path

import calibration as cal
import converter as c


def observations(pairs, family):
    values = []
    for p in pairs:
        roles = ["List_UpgradeBrakes"] if family == "braking" else (
            ["spring.front","spring.rear"] if family == "independent_camber" else ["spring.front"])
        columns = {"braking":["GameFrictionScaleBraking"],
                   "independent_camber":["CamberChangeRatioCompression","CamberChangeRatioExpansion"],
                   "front_toe":["StaticToe"]}[family]
        for role in roles:
            for col in columns:
                source,target = p["source"]["nodes"][role],p["target"]["nodes"][role]
                # Keys are source data; target is used only as training label.
                if family == "independent_camber":
                    if source["SuspensionPhysicsTypeID"] != 0 or source[col] != 0: continue
                if family == "front_toe":
                    if source["SuspensionPhysicsTypeID"] != 0 or source[col] != .5: continue
                values.append({"id":p["source"]["id"],"media_name":p["source"]["media_name"],
                               "role":role,"column":col,"source":source[col],"target":target[col]})
    return values


def fit(data):
    train = [p for p in data["pairs"] if p["split"]=="training"]
    model = {"version":"benchmark-refinements-v1",
             "policy":{"strong_min_training_cars":30,"strong_min_validation_cars":10,
                       "strong_training_match":.99,"strong_validation_match":.98,
                       "experimental_min_training_cars":10,"experimental_training_match":1.0},
             "provenance":"Hypotheses discovered after inspecting benchmark30; fitted only on original training. Validation reused.",
             "entries":[]}
    for family in ("braking","independent_camber","front_toe"):
        obs = observations(train,family)
        for source in sorted({r["source"] for r in obs}):
            group = [r for r in obs if r["source"]==source]
            counts = Counter(r["target"] for r in group)
            target = sorted(counts,key=lambda k:(-counts[k],k))[0]
            if target == source: continue
            vehicles = {r["id"] for r in group}
            matched = {i for i in vehicles if all(cal.equal(r["target"],target) for r in group if r["id"]==i)}
            n,ratio = len(vehicles),len(matched)/len(vehicles)
            model["entries"].append({"family":family,"source":source,"value":target,
                                     "training_cars":n,"training_match":ratio,
                                     "training_distribution":dict(counts),
                                     "training_observations":group,
                                     "strong_training_eligible":n>=30 and ratio>=.99,
                                     "experimental_eligible":n>=10 and ratio==1})
    return model


def validate(data, model):
    pairs = [p for p in data["pairs"] if p["split"]=="validation"]
    for entry in model["entries"]:
        obs = [r for r in observations(pairs,entry["family"]) if r["source"]==entry["source"]]
        ids = {r["id"] for r in obs}
        matched = {i for i in ids if all(cal.equal(r["target"],entry["value"]) for r in obs if r["id"]==i)}
        entry["validation_cars"] = len(ids)
        entry["validation_matching_cars"] = len(matched)
        entry["validation_match"] = len(matched)/len(ids) if ids else None
        entry["validation_observations"] = obs
        entry["validation_exceptions"] = [r for r in obs if not cal.equal(r["target"],entry["value"])]
        entry["accepted"] = (entry["strong_training_eligible"] and
                             len(ids)>=model["policy"]["strong_min_validation_cars"] and
                             entry["validation_match"]>=model["policy"]["strong_validation_match"])
    return model


def propose(record, model, mode):
    updates,notes = [],[]
    for entry in model["entries"]:
        eligible = entry.get("accepted") or (mode=="experimental" and entry["experimental_eligible"])
        roles = (["List_UpgradeBrakes"] if entry["family"]=="braking" else
                 ["spring.front","spring.rear"] if entry["family"]=="independent_camber" else ["spring.front"])
        columns = {"braking":["GameFrictionScaleBraking"],
                   "independent_camber":["CamberChangeRatioCompression","CamberChangeRatioExpansion"],
                   "front_toe":["StaticToe"]}[entry["family"]]
        for role in roles:
            row = record["nodes"][role]
            if role.startswith("spring.") and row["SuspensionPhysicsTypeID"] != 0: continue
            for col in columns:
                if not cal.equal(row[col],entry["source"]): continue
                if not eligible:
                    notes.append({"rule":"refined_"+entry["family"],"role":role,"column":col,
                                  "status":"not_enough_support_or_failed_validation"})
                    continue
                updates.append({"role":role,"column":col,"value":entry["value"],
                                "rule":"refined_"+entry["family"],
                                "confidence":"validated_cross_car_pattern" if entry["accepted"] else "experimental_only",
                                "training_cars":entry["training_cars"],
                                "validation_cars":entry["validation_cars"],
                                "validation_matching_cars":entry["validation_matching_cars"],
                                "accepted":entry["accepted"],"input_value":row[col]})
    return updates,notes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out",type=Path,required=True)
    parser.add_argument("--rules",type=Path,required=True)
    args=parser.parse_args()
    out=args.out.resolve()
    if out.exists(): parser.error("Use a new output directory")
    for p in (c.FM3_DEFAULT,c.FM4_DEFAULT):
        root=p.resolve().parent.parent.parent
        if out==root or root in out.parents: parser.error("Output must be outside game directories")
    hashes={str(p):c.sha(p) for p in (c.FM3_DEFAULT,c.FM4_DEFAULT)}
    with closing(c.connect(c.FM3_DEFAULT)) as src,closing(c.connect(c.FM4_DEFAULT)) as dst:
        data=cal.collect(src,dst)
    model=fit(data)
    out.mkdir(parents=True)
    c.dump(out/"rules_before_validation.json",model)
    validate(data,model)
    c.dump(out/"refinements.json",model)
    combined=json.loads(args.rules.read_text(encoding="utf-8"))
    combined["benchmark_refinements"]=model
    c.dump(out/"rules.json",combined)
    lines=["# Aturan tambahan setelah benchmark 30 mobil","",
           "Hipotesis ditemukan setelah benchmark; fitting memakai 236 training dan gerbang memakai "
           "73 validation lama. Ini bukan konfirmasi pada data baru. Dukungan dihitung per mobil, "
           "bukan menggandakan sampel dari axle atau dua kolom camber. Aturan default memerlukan "
           "minimal 30 training/10 validation, akurasi 99%/98%. Mode eksperimen mengizinkan aturan "
           "dengan minimal 10 training dan kecocokan training 100%, sambil mempertahankan flag penolakan.","",
           "| Aturan | Sumber → target | Training | Validation | Diterima default dengan profil baru |",
           "|---|---|---:|---:|---|"]
    for e in model["entries"]:
        lines.append(f"| {e['family']} | {e['source']} → {e['value']} | {e['training_cars']} | "
                     f"{e['validation_matching_cars']}/{e['validation_cars']} | {e['accepted']} |")
    lines+=["","`independent_camber` hanya untuk SuspensionPhysicsTypeID=0 (INDEPENDANT), "
            "camber compression/expansion yang bernilai 0; solid axle tidak berubah. `front_toe` "
            "hanya front independent dengan StaticToe=0.5. Nilai sumber yang belum diamati tidak diubah.",
            "","Pengecualian validation braking:", ""]
    for e in model["entries"]:
        for row in e["validation_exceptions"]:
            lines.append(f"- {row['media_name']}: {row['source']} → {row['target']}, prediksi {e['value']}.")
    (out/"REPORT.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    after={str(p):c.sha(p) for p in (c.FM3_DEFAULT,c.FM4_DEFAULT)}
    if after!=hashes: raise c.MappingError("Source changed")
    c.dump(out/"manifest.json",{"sources_before":hashes,"sources_after":after,"sources_unchanged":True,
                               "code_sha256":c.sha(__file__),"input_rules_sha256":c.sha(args.rules),
                               "outputs":{p.name:c.sha(p) for p in out.iterdir() if p.is_file()}})
    print(json.dumps([{k:v for k,v in e.items() if k not in
                       ("training_observations","validation_observations")} for e in model["entries"]],indent=2))


if __name__=="__main__":
    main()
