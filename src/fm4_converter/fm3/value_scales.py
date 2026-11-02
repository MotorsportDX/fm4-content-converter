"""FM3 values that FM4 stores on a different scale or by a different convention.

The study runs the current conversion (refined conservative rules and the code
semantics adapter, as `integration.build_plan` does) for every same-car pair
of `calibration.collect`, compares each converted column with the native FM4
car, and fits one rule per systematically different column on TRAINING only:

- `constant`: every FM4 row of the table holds one value (a convention such as
  `Data_Car.MakeIcon = 'BOING'`), so the source value is not used at all;
- `lookup`: an enumeration that FM4 renumbered or regrouped, learned per
  source value and only where the training mapping is unambiguous;
- `linear` / `loglinear`: a continuous scale, monotone, within the training
  domain only.

Candidates are chosen by engine-grouped CV on training, then frozen before
validation, and a rule is accepted only when validation beats identity by the
policy margin. Columns that another adapter owns (identity, integration
metadata, PerformanceIndex/ClassID, code-semantics heights) are excluded.
Applying rules uses the standard library.
"""
from collections import Counter, defaultdict
from contextlib import closing
import copy
import hashlib
import json
import math
from pathlib import Path

from . import converter as c


POLICY = {"folds":5,"min_training_difference":0.2,"min_training_rows":30,"min_validation_rows":10,
          "constant_coverage":0.99,"lookup_consistency":0.95,"lookup_min_support":3,
          "categorical_validation_match":0.95,"continuous_mae_ratio":0.5,"cv_tolerance":1.05,
          "grids":(0.01,0.005,0.0025,0.001),"grid_coverage":0.99}
# Written by other adapters; a scale rule must never override them.
OWNED = {("Data_Car",k) for k in ("PerformanceIndex","ClassID","ModelId","ContentId","IsInstalled",
                                  "IsPurchased","IsArcade","IsUnicorn","IsDrivable","HasCarExperience",
                                  "IsCarExperienceUnlocked","DisplayName","ModelShort",
                                  "FrontStockRideHeight","RearStockRideHeight")}
OWNED |= {("List_UpgradeCarBodyWeight","CMHeight"),("List_SpringDamperPhysics","MaxStretchDeltaFromRideHeight")}
# Both games normalize these rates identically (code_semantics, 558/558 traced
# coefficients); FM4 values differ by per-car retuning, not by unit. The
# adapter also audits the extension cap against them, so they stay FM3's.
RATES = ("SpringRate","DampenBumpRate","DampenReboundRate","SwaybarStiffness")


def owned(table, column):
    return ((table,column) in OWNED or column in {"Id","ID","Ordinal","Level","IsStock"}
            or table in {"List_SpringDamperPhysics","List_AntiSwayPhysics"} and column.endswith(RATES)
            or column.endswith(("ID","Id")) and column not in {"FamilyBodyID","GaugeID"}
            or table=="List_TorqueCurve" and column[:1]=="v" and column[1:].isdigit())


def number(v):
    return isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v)


def predict(rule, value):
    kind = rule["kind"]
    if kind=="constant":
        return rule["value"]
    if kind=="lookup":
        return rule["values"].get(json.dumps(value))
    if not number(value):
        return None
    if kind=="linear":
        y = rule["coef"][0]+rule["coef"][1]*value
    elif value<=0:
        return None
    else:
        y = math.exp(rule["coef"][0]+rule["coef"][1]*math.log(value))
    if rule.get("integer"):
        step = rule.get("step",1)
        return int(round(y/step)*step)
    if rule.get("grid"):
        return round(round(y/rule["grid"])*rule["grid"],6)
    return round(y,6)  # the precision of the native FM4 floats


def in_domain(rule, value):
    if rule["kind"] in {"constant","lookup"}:
        return predict(rule,value) is not None
    return number(value) and rule["domain"][0]<=value<=rule["domain"][1]


def apply(result, rules, physics=False):
    """Rewrite candidate nodes in place; every change and abstention is recorded.

    Physics rules change handling, so they apply only when asked for."""
    changes, abstained = [], []
    by_column = {(r["table"],r["column"]):r for r in rules.get("rules",[])
                 if r.get("accepted") and (physics or r["category"]!="physics")}
    for role,node in result["candidate"]["nodes"].items():
        for column,value in list(node["row"].items()):
            rule = by_column.get((node["table"],column))
            if rule is None:
                continue
            if not in_domain(rule,value):
                abstained.append({"role":role,"column":column,"value":value,"reason":"outside_training_domain"})
                continue
            new = predict(rule,value)
            if new!=value:
                node["row"][column] = new
                changes.append({"role":role,"table":node["table"],"column":column,"before":value,
                                "after":new,"rule":rule["kind"]})
    for mapping in result.get("mapping",[]):
        row = result["candidate"]["nodes"].get(mapping.get("role"),{}).get("row",{})
        if mapping.get("target_column") in row:
            mapping["target_value"] = row[mapping["target_column"]]
    result["value_scales"] = {"version":rules.get("version"),"physics":physics,"changes":changes,
                              "abstained":abstained}
    return result["value_scales"]


# --- study ---------------------------------------------------------------------

def observations(source_db, target_db, rules):
    from . import calibration as cal, code_semantics
    data = cal.collect(source_db,target_db)
    rows = []
    for pair in data["pairs"]:
        media = pair["source"]["media_name"]
        source = c.extract_stock(source_db,media)
        result = c.convert(source_db,target_db,source,c.ID_BASE)
        if rules is not None:
            cal.apply_to_result(result,source,rules,"conservative")
        code_semantics.apply(result,source)
        reference = c.extract_stock(target_db,media)  # read only after the candidate exists
        for role,node in result["candidate"]["nodes"].items():
            ref = reference["nodes"].get(role)
            if ref is None or ref["table"]!=node["table"]:
                continue
            for column,value in node["row"].items():
                if column in ref["row"] and not owned(node["table"],column):
                    rows.append({"media":media,"split":pair["split"],"engine":pair["source"]["engine_id"],
                                 "table":node["table"],"column":column,"x":value,"y":ref["row"][column]})
    return rows


def same(a, b):
    if number(a) and number(b):
        return math.isclose(a,b,rel_tol=1e-6,abs_tol=1e-6)
    return a==b


def fit(kind, xs, ys, target_db, table, column):
    if kind=="identity":
        return {"kind":"identity"}
    if kind=="constant":
        counts = Counter(r[0] for r in target_db.execute(f"SELECT {c.qi(column)} FROM {c.qi(table)}"))
        value,n = counts.most_common(1)[0]
        if n/sum(counts.values())<POLICY["constant_coverage"]:
            return None
        return {"kind":kind,"value":value,"fm4_rows":sum(counts.values()),"fm4_coverage":n/sum(counts.values())}
    if kind=="lookup":
        groups = defaultdict(Counter)
        for x,y in zip(xs,ys):
            groups[json.dumps(x)][y] += 1
        table_ = {}
        for key,counts in groups.items():
            y,n = counts.most_common(1)[0]
            total = sum(counts.values())
            if total>=POLICY["lookup_min_support"] and n/total>=POLICY["lookup_consistency"]:
                table_[key] = y
        return {"kind":kind,"values":table_} if table_ else None
    pts = [(x,y) for x,y in zip(xs,ys) if number(x) and number(y) and (kind=="linear" or x>0 and y>0)]
    if len(pts)<POLICY["min_training_rows"]:
        return None
    tx = [x if kind=="linear" else math.log(x) for x,_ in pts]
    ty = [y if kind=="linear" else math.log(y) for _,y in pts]
    mx,my = sum(tx)/len(tx),sum(ty)/len(ty)
    sxx = sum((x-mx)**2 for x in tx)
    if sxx==0:
        return None
    slope = sum((x-mx)*(y-my) for x,y in zip(tx,ty))/sxx
    if slope<=0:
        return None
    rule = {"kind":kind,"coef":[my-slope*mx,slope],"domain":[min(x for x,_ in pts),max(x for x,_ in pts)]}
    if all(isinstance(y,int) for _,y in pts):
        # Keep the FM4 granularity of integer columns such as prices.
        steps = [s for s in (1000,500,100,10,1) if all(y%s==0 for _,y in pts)]
        rule.update(integer=True,step=steps[0])
    else:
        grid = native_grid(target_db,table,column)
        if grid:
            rule["grid"] = grid
    return rule


def native_grid(target_db, table, column):
    """The coarsest decimal grid that holds the column in nearly every FM4 row."""
    values = [r[0] for r in target_db.execute(f"SELECT {c.qi(column)} FROM {c.qi(table)}") if number(r[0])]
    for step in POLICY["grids"]:
        if values and sum(abs(v/step-round(v/step))<1e-6 for v in values)/len(values)>=POLICY["grid_coverage"]:
            return step
    return None


def score(rule, xs, ys, continuous):
    pred = [x if rule["kind"]=="identity" else (predict(rule,x) if in_domain(rule,x) else x)
            for x in xs]
    matches = sum(same(p,y) for p,y in zip(pred,ys))
    out = {"n":len(ys),"match":matches,"match_rate":matches/len(ys) if ys else 0.0}
    if continuous:
        errors = [abs(p-y) for p,y in zip(pred,ys)]
        out["mae"] = sum(errors)/len(errors)
    return out


def study(source_db, target_db, rules=None):
    rows = observations(source_db,target_db,rules)
    columns = defaultdict(list)
    for r in rows:
        columns[(r["table"],r["column"])].append(r)
    fold = lambda engine: int(hashlib.sha256(("fm3-fm4-values-cv-v1:"+str(engine)).encode())
                              .hexdigest()[:8],16)%POLICY["folds"]
    report = []
    for (table,column),items in sorted(columns.items()):
        train = [r for r in items if r["split"]=="training"]
        valid = [r for r in items if r["split"]=="validation"]
        differ = sum(not same(r["x"],r["y"]) for r in train)/max(len(train),1)
        entry = {"table":table,"column":column,"category":c.category(table,column),
                 "training_rows":len(train),"validation_rows":len(valid),
                 "training_difference_rate":differ,"accepted":False}
        report.append(entry)
        if differ<POLICY["min_training_difference"] or len(train)<POLICY["min_training_rows"] \
                or len(valid)<POLICY["min_validation_rows"]:
            entry["status"] = "not_systematic"
            continue
        continuous = all(number(r["x"]) and number(r["y"]) for r in items) \
            and not all(isinstance(r["x"],int) and isinstance(r["y"],int) and len({q["y"] for q in items})<=50
                        for r in items)
        kinds = ["constant","linear","loglinear"] if continuous else ["constant","lookup"]
        cv = {}
        for kind in ["identity"]+kinds:
            preds_ok, errors, matches, n = True, [], 0, 0
            for f in range(POLICY["folds"]):
                fit_rows = [r for r in train if fold(r["engine"])!=f]
                held = [r for r in train if fold(r["engine"])==f]
                rule = fit(kind,[r["x"] for r in fit_rows],[r["y"] for r in fit_rows],target_db,table,column)
                if rule is None:
                    preds_ok = False
                    break
                s = score(rule,[r["x"] for r in held],[r["y"] for r in held],continuous)
                matches += s["match"]; n += s["n"]
                if continuous:
                    errors.append(s["mae"]*s["n"])
            if preds_ok and n:
                cv[kind] = {"match_rate":matches/n,**({"mae":sum(errors)/n} if continuous else {})}
        entry["cv"] = cv
        candidates = [k for k in kinds if k in cv]
        if not candidates:
            entry["status"] = "no_valid_candidate"
            continue
        if continuous:
            best = min(cv[k]["mae"] for k in candidates)
            chosen = next(k for k in candidates if cv[k]["mae"]<=best*POLICY["cv_tolerance"])
        else:
            chosen = max(candidates,key=lambda k:(cv[k]["match_rate"],k=="constant"))
        # Frozen before validation is read.
        rule = fit(chosen,[r["x"] for r in train],[r["y"] for r in train],target_db,table,column)
        entry["rule"] = rule
        vx,vy = [r["x"] for r in valid],[r["y"] for r in valid]
        entry["validation"] = score(rule,vx,vy,continuous)
        entry["validation_identity"] = score({"kind":"identity"},vx,vy,continuous)
        if continuous:
            entry["accepted"] = entry["validation"]["mae"]<=POLICY["continuous_mae_ratio"]*entry["validation_identity"]["mae"]
        else:
            entry["accepted"] = (entry["validation"]["match_rate"]>=POLICY["categorical_validation_match"]
                                 and entry["validation"]["match"]>entry["validation_identity"]["match"])
        entry["status"] = "accepted" if entry["accepted"] else "rejected_by_validation"
    return {"version":1,"policy":POLICY,"columns":report,
            "rules":[{"table":e["table"],"column":e["column"],"category":e["category"],"accepted":True,
                      **e["rule"]}
                     for e in report if e["accepted"]]}


def main():
    import argparse
    p = argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--fm3",type=Path,default=c.FM3_DEFAULT)
    p.add_argument("--fm4",type=Path,default=c.FM4_DEFAULT)
    p.add_argument("--rules",type=Path,help="calibration rules used by the packaging path")
    p.add_argument("--out",type=Path,required=True,help="new JSON file")
    a = p.parse_args()
    if a.out.exists():
        raise SystemExit("Choose a new output file")
    rules = json.loads(a.rules.read_text()) if a.rules else None
    with closing(c.connect(a.fm3)) as s, closing(c.connect(a.fm4)) as t:
        result = study(s,t,rules)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(result,indent=1))
    for e in result["columns"]:
        if e.get("status")!="not_systematic":
            print(f'{e["status"]:24s} {e["table"]}.{e["column"]} diff={e["training_difference_rate"]:.2f} '
                  f'{(e.get("rule") or {}).get("kind","-")} val={e.get("validation")} id={e.get("validation_identity")}')


if __name__=="__main__":
    main()
