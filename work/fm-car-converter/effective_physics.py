"""Pure evaluators for the statically traced FM3/FM4 suspension setup.

This is a mathematical interpretation in Python double precision, not a
bit-exact PowerPC emulator or a complete solver/handling simulation. The
negative-slider default path and coefficient setup were verified in both
executables. An omitted slider explicitly selects that path; it does not
assert that an arbitrary saved tuning file contains the default sentinel.

Without an explicit mass_factor, outputs are normalized coefficients only.
No component masses are summed and no native target value informs evaluation.
Evidence: outputs/fm-car-converter/code-semantics-v1/suspension/REPORT.md.
"""
from __future__ import annotations

import math


REL_TOL = 1e-6
ABS_TOL = 1e-6
EVIDENCE = {
    "FM3": {"normalize": "0x8272A310", "setup": "0x82729458"},
    "FM4": {"normalize": "0x8281FAA0", "setup": "0x8281EBA0",
            "antiroll_setup": "0x8281AAA0", "force": "0x8230C350"},
}
LIMITATIONS = [
    "Python double-precision formulas; not bit-exact PowerPC float32/FMA execution.",
    "Omitted tuning chooses the negative-slider/default path explicitly.",
    "Normalized coefficients do not establish equal physical forces when runtime mass factors differ.",
    "Visible mass-field equality does not prove identical component aggregation or runtime mass.",
    "MaxStretchDeltaFromRideHeight is an additional FM4 extension constraint; "
    "no FM3 value or safe conversion is inferred here.",
    "Geometry, contact state, tire behavior and the complete timestep solver are outside this evaluator.",
]
INTERPOLATED = {
    "spring": ("spring", "DefSpringRate", "MinSpringRate", "MaxSpringRate"),
    "bump": ("spring", "DefDampenBumpRate", "MinDampenBumpRate", "MaxDampenBumpRate"),
    "rebound": ("spring", "DefDampenReboundRate", "MinDampenReboundRate", "MaxDampenReboundRate"),
    "antiroll": ("antiroll", "DefSwaybarStiffness", "MinSwaybarStiffness", "MaxSwaybarStiffness"),
}
DIRECT = {
    "bump_clamp": ("spring", "DampenBumpClamp"),
    "rebound_clamp": ("spring", "DampenReboundClamp"),
    "bumpstop_stiffness": ("spring", "BumpstopStiffness"),
    "bumpstop_damping": ("spring", "BumpstopDamping"),
    "antiroll_damping": ("antiroll", "SwaybarDamping"),
}


def _number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{label} must be a finite number")
    return float(value)


def _row(graph, role):
    node = graph.get("nodes", {}).get(role, {})
    return node.get("row", node)


def normalize_slider(value, default, minimum, maximum):
    """Mirror the traced helper for finite inputs, including reversed bounds.

    A nonnegative input is already a slider and is clamped to [0,1].
    A negative input requests the default. The helper orders bounds for that
    normalization; interpolation later uses the original Min/Max ordering.
    """
    value, default, minimum, maximum = (
        _number(v, name) for v, name in
        ((value, "slider"), (default, "default"), (minimum, "minimum"), (maximum, "maximum"))
    )
    if value < 0:
        low, high = sorted((minimum, maximum))
        value = 0.5 if low == high else (default - low) / (high - low)
    return max(0.0, min(1.0, value))


def _mass_context(graph):
    """Inventory visible mass inputs without guessing which ones are summed."""
    values = {}
    for role, node in graph.get("nodes", {}).items():
        row = node.get("row", node)
        for column, value in row.items():
            if "mass" in column.lower() or column == "CurbWeight":
                values[f"{role}.{column}"] = value
    return {
        "visible_fields": values,
        "base_mass": _row(graph, "List_UpgradeCarBodyWeight").get("Mass"),
        "runtime_factor_inferred": False,
    }


def evaluate(graph, *, tuning=None, mass_factor=None):
    """Evaluate each axle from its own rows, optionally applying a supplied factor.

    tuning is {"front": {"spring": slider, "bump": slider, ...}, "rear": {...}}.
    Missing sliders select the default path. Coefficient names are
    ``front.spring``, ``front.bump``, ``front.rebound``, ``front.antiroll``, etc.
    Missing/nonfinite database fields are reported, never replaced with zero.
    """
    tuning = {} if tuning is None else tuning
    if set(tuning) - {"front", "rear"}:
        raise ValueError("tuning contains an unknown axle")
    for axle, sliders in tuning.items():
        if set(sliders) - set(INTERPOLATED):
            raise ValueError(f"tuning for {axle} contains an unknown coefficient")
        for name, slider in sliders.items():
            _number(slider, f"{axle}.{name}.slider")
    factor = 1.0 if mass_factor is None else _number(mass_factor, "mass_factor")
    if factor <= 0:
        raise ValueError("mass_factor must be positive")
    fields, missing = {}, []
    for axle in ("front", "rear"):
        for name, spec in {**INTERPOLATED, **DIRECT}.items():
            role = spec[0] + "." + axle
            columns = spec[1:]
            row = _row(graph, role)
            key = axle + "." + name
            entry = {"role": role, "columns": list(columns), "available": False}
            try:
                raw = [_number(row.get(col), role + "." + col) for col in columns]
            except ValueError as exc:
                entry["reason"] = str(exc)
                fields[key] = entry
                missing.append({"field": key, "reason": str(exc)})
                continue
            entry["input_values"] = dict(zip(columns, raw))
            if name in INTERPOLATED:
                default, minimum, maximum = raw
                supplied_slider = tuning.get(axle, {}).get(name, -1.0)
                slider = normalize_slider(supplied_slider, default, minimum, maximum)
                selected = minimum + (maximum - minimum) * slider
                entry.update({
                    "slider_input": supplied_slider, "normalized_slider": slider,
                    "default_path": supplied_slider < 0,
                    "formula": "factor * (minimum + (maximum - minimum) * normalized_slider)",
                })
            else:
                selected = raw[0]
                entry["formula"] = "factor * database_value"
            value = selected * factor
            if not math.isfinite(value):
                entry["reason"] = "coefficient computation produced a nonfinite value"
                fields[key] = entry
                missing.append({"field": key, "reason": entry["reason"]})
                continue
            entry.update({"available": True, "normalized_value": selected,
                          "mass_factor": factor, "value": value})
            fields[key] = entry
    return {
        "media_name": graph.get("media_name"),
        "basis": "normalized_coefficients" if mass_factor is None else "supplied_runtime_mass_factor",
        "mass_factor": factor, "mass_factor_supplied": mass_factor is not None,
        "fields": fields,
        "coefficients": {key: entry["value"] for key, entry in fields.items() if entry["available"]},
        "missing": missing, "mass_context": _mass_context(graph),
        "limitations": list(LIMITATIONS), "evidence": EVIDENCE,
        "candidate_mutated": False,
    }


def compare_effective(source, candidate, *, source_tuning=None, candidate_tuning=None,
                      source_mass_factor=None, candidate_mass_factor=None,
                      rel_tol=REL_TOL, abs_tol=ABS_TOL):
    """Compare independently evaluated graphs, retaining every available delta.

    If only one mass factor is supplied the coefficient bases differ and no
    matching/error totals are asserted. The caller must supply both factors
    or compare both normalized graphs.
    """
    rel_tol = _number(rel_tol, "rel_tol")
    abs_tol = _number(abs_tol, "abs_tol")
    if rel_tol < 0 or abs_tol < 0:
        raise ValueError("comparison tolerances must be nonnegative")
    left = evaluate(source, tuning=source_tuning, mass_factor=source_mass_factor)
    right = evaluate(candidate, tuning=candidate_tuning, mass_factor=candidate_mass_factor)
    same_basis = left["basis"] == right["basis"]
    fields, compared, equal, differing, unavailable = [], 0, 0, 0, 0
    for key in left["fields"]:
        a, b = left["fields"][key], right["fields"][key]
        entry = {"field": key, "source": a, "candidate": b, "basis_comparable": same_basis}
        if a["available"] and b["available"]:
            av, bv = a["value"], b["value"]
            if same_basis:
                match = math.isclose(av, bv, rel_tol=rel_tol, abs_tol=abs_tol)
                entry.update({"delta": bv - av, "absolute_delta": abs(bv - av),
                              "relative_delta": (bv - av) / abs(av) if av else None,
                              "equal_within_tolerance": match})
                compared += 1
                equal += int(match)
                differing += int(not match)
            else:
                entry["reason"] = "mixed_normalized_and_mass_scaled_bases"
                unavailable += 1
        else:
            entry["reason"] = "missing_or_invalid_inputs"
            unavailable += 1
        fields.append(entry)
    lm = left["mass_context"]["visible_fields"]
    rm = right["mass_context"]["visible_fields"]
    mass_differences = []
    for key in sorted(set(lm) | set(rm)):
        a, b = lm.get(key), rm.get(key)
        try:
            match = math.isclose(_number(a, key), _number(b, key), rel_tol=rel_tol, abs_tol=abs_tol)
        except ValueError:
            match = False
        if not match:
            mass_differences.append({"field": key, "source": a, "candidate": b})
    return {
        "basis": left["basis"] if same_basis else "mixed_bases_not_comparable",
        "source": left, "candidate": right, "fields": fields,
        "counts": {"compared": compared, "equal": equal, "different": differing,
                   "unavailable": unavailable},
        "tolerance": {"relative": rel_tol, "absolute": abs_tol},
        "mass_context": {
            "visible_fields_equal": not mass_differences if lm or rm else None,
            "base_mass_available": left["mass_context"]["base_mass"] is not None
                                   and right["mass_context"]["base_mass"] is not None,
            "differences": mass_differences,
            "runtime_factor_equality_proven": False,
        },
        "limitations": list(LIMITATIONS), "candidate_mutated": False,
    }
