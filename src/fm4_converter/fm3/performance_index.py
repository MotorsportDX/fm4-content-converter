"""FM3 -> FM4 PerformanceIndex scale and the class that FM4 derives from it.

FM4 shows a car's PI by interpolating its raw `Data_Car.PerformanceIndex`
between the `CarClasses.MaxPerformanceIndex` bounds, but shows the class
letter from the stored `ClassID`. All 503 FM4 cars (and all 415 FM3 cars)
keep `ClassID` equal to the class whose bound first covers the raw PI. The
two games use different bounds, so a raw FM3 value copied verbatim shows a
lower FM4 PI under a stale FM3 class letter (Cobalt v6: "D 209", where FM4
cars of PI 209 are E).

`class_for` restores the FM4 invariant for whatever PI is written. The study
fits the raw-scale mapping on the TRAINING pairs of `calibration.collect`
(engine-grouped split), picks a candidate by engine-grouped CV on training,
and only then measures validation. Applying a model uses the standard library.
"""
from contextlib import closing
import hashlib
import json
from pathlib import Path

from . import converter as c


POLICY = {"min_validation_class_match":0.75,"folds":5,"cv_tolerance":1.05}


def classes(target_db):
    rows = [tuple(r) for r in target_db.execute(
        "SELECT Id,MaxPerformanceIndex FROM CarClasses ORDER BY MaxPerformanceIndex")]
    if not rows or any(b[1]<=a[1] for a,b in zip(rows,rows[1:])):
        raise c.MappingError("CarClasses bounds are missing or not increasing")
    return rows


def class_for(pi, bounds):
    for cid,bound in bounds:
        if pi<=bound:
            return cid
    raise c.MappingError(f"PerformanceIndex {pi} is above every class bound")


def predict(model, x):
    k = model["coef"]
    return k[0]+k[1]*x+sum(w*max(0.0,x-knot) for w,knot in zip(k[2:],model["knots"]))


def apply(car, target_db, model=None):
    """Map PI when an accepted model covers it; always rewrite ClassID to match."""
    bounds = classes(target_db)
    before = {"PerformanceIndex":car["PerformanceIndex"],"ClassID":car["ClassID"]}
    pi,status = car["PerformanceIndex"],"source_raw_pi_kept"
    if model is not None:
        lo,hi = model["domain"]
        if not model.get("accepted"):
            status = "model_not_accepted"
        elif not lo<=pi<=hi:
            status = "outside_training_domain"
        else:
            mapped = predict(model,pi)
            if not 0.0<mapped<=bounds[-1][1]:
                raise c.MappingError(f"Mapped PerformanceIndex {mapped} is outside the FM4 class bounds")
            pi,status = round(mapped,6),"mapped_"+model["kind"]
    car["PerformanceIndex"],car["ClassID"] = pi,class_for(pi,bounds)
    return {"status":status,"before":before,
            "after":{"PerformanceIndex":car["PerformanceIndex"],"ClassID":car["ClassID"]},
            "rule":"ClassID = first FM4 CarClasses bound >= PerformanceIndex (0/503 native exceptions)"}


# --- study (NumPy) -------------------------------------------------------------

def fit(kind, x, y, knots):
    import numpy as np
    if kind=="identity":
        return {"kind":kind,"coef":[0.0,1.0],"knots":[]}
    used = [k for k in knots if x.min()<k<x.max()] if kind=="hinge" else []
    basis = np.column_stack([np.ones_like(x),x]+[np.maximum(0.0,x-k) for k in used])
    coef = np.linalg.lstsq(basis,y,rcond=None)[0]
    return {"kind":kind,"coef":[float(v) for v in coef],"knots":[float(k) for k in used]}


def monotone(model):
    slope = model["coef"][1]
    for w in model["coef"][2:]:
        if slope<=0:
            return False
        slope += w
    return slope>0


def metrics(model, x, y, bounds):
    pred = [predict(model,v) for v in x]
    errors = sorted(abs(p-t) for p,t in zip(pred,y))
    match = sum(class_for(min(max(p,0.0),bounds[-1][1]),bounds)==class_for(t,bounds) for p,t in zip(pred,y))
    return {"n":len(errors),"mae":sum(errors)/len(errors),"p90":errors[int(0.9*(len(errors)-1))],
            "class_match":match,"class_match_rate":match/len(errors)}


def study(source_db, target_db):
    import numpy as np
    from .calibration import collect
    data = collect(source_db,target_db)
    p3 = {r[0]:r[1] for r in source_db.execute("SELECT Id,PerformanceIndex FROM Data_Car")}
    p4 = {r[0]:r[1] for r in target_db.execute("SELECT Id,PerformanceIndex FROM Data_Car")}
    bounds = classes(target_db)
    knots = [b for _,b in classes(source_db)]  # FM3 class bounds as candidate knots
    split = lambda name: [p for p in data["pairs"] if p["split"]==name]
    arrays = lambda ps: (np.array([p3[p["source"]["id"]] for p in ps]),
                         np.array([p4[p["source"]["id"]] for p in ps]))
    train,valid = split("training"),split("validation")
    xt,yt = arrays(train)
    fold = np.array([int(hashlib.sha256(("fm3-fm4-pi-cv-v1:"+str(p["source"]["engine_id"])).encode())
                         .hexdigest()[:8],16)%POLICY["folds"] for p in train])
    cv = {}
    for kind in ("identity","linear","hinge"):
        errors, monotone_all = [], True
        for f in range(POLICY["folds"]):
            m = fit(kind,xt[fold!=f],yt[fold!=f],knots)
            monotone_all &= monotone(m)
            errors += [abs(predict(m,v)-t) for v,t in zip(xt[fold==f],yt[fold==f])]
        cv[kind] = {"mae":float(np.mean(errors)),"monotone_every_fold":bool(monotone_all)}
    # Simplest monotone candidate within the CV tolerance of the best one
    # (identity, then linear, then hinge).
    eligible = [k for k in cv if cv[k]["monotone_every_fold"]]
    best = min(cv[k]["mae"] for k in eligible)
    chosen = next(k for k in eligible if cv[k]["mae"]<=best*POLICY["cv_tolerance"])
    # Frozen before validation is read.
    model = fit(chosen,xt,yt,knots)
    model.update({"version":1,"domain":[float(xt.min()),float(xt.max())],"policy":POLICY,
                  "training_ids":[p["source"]["id"] for p in train],
                  "validation_ids":[p["source"]["id"] for p in valid],"cv":cv})
    xv,yv = arrays(valid)
    model["training"] = metrics(model,xt,yt,bounds)
    model["validation"] = metrics(model,xv,yv,bounds)
    model["validation_identity"] = metrics(fit("identity",xt,yt,knots),xv,yv,bounds)
    model["accepted"] = bool(monotone(model)
        and model["validation"]["class_match_rate"]>=POLICY["min_validation_class_match"]
        and model["validation"]["mae"]<model["validation_identity"]["mae"])
    return model


def main():
    import argparse
    p = argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--fm3",type=Path,default=c.FM3_DEFAULT)
    p.add_argument("--fm4",type=Path,default=c.FM4_DEFAULT)
    p.add_argument("--out",type=Path,required=True,help="new JSON file for the model")
    a = p.parse_args()
    if a.out.exists():
        raise SystemExit("Choose a new output file")
    with closing(c.connect(a.fm3)) as s, closing(c.connect(a.fm4)) as t:
        model = study(s,t)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(model,indent=1))
    print(json.dumps({k:model[k] for k in ("kind","coef","knots","domain","cv","training",
                                           "validation","validation_identity","accepted")},indent=1))


if __name__=="__main__":
    main()
