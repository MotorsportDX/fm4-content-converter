"""Paired static-code stock-height mapping and extension-cap audit.

These formulas describe suspension setup inputs, not measured vehicle motion.
The selected parts, geometry, distribution and rate fields must be preserved.
Evidence and original-byte checks: ride_height_audit.py / ride-height-v2.
"""
from __future__ import annotations

import math

import converter as c
import effective_physics as e


# Identical float32 constants decoded from both retail images.
HALF_GRAVITY = 4.903325080871582
EXTENSION_THRESHOLD = 0.07000000029802322
EXTENSION_SCALE = 0.75
NUMERIC_MARGIN = 1e-6
EVIDENCE = {
    "fm3_reference_height": "0x827294D8..0x82729578: axle.MaxRideHeight",
    "fm4_reference_height": "0x8281EC20..0x8281ECC8: Data_Car stock heights",
    "fm4_height_loads": "0x828A616C / 0x828A61A8",
    "fm3_extension": "0x82728010..0x82728050",
    "fm4_extension": "0x8281AC40..0x8281AC98",
    "fm3_spring_rest_setup": "0x82729E84..0x82729EE4",
    "fm4_spring_rest_setup": "0x8281F5F4..0x8281F654",
}


def number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise c.MappingError("Invalid finite suspension input: " + label)
    return float(value)


def row(graph, role):
    return graph["nodes"][role]["row"]


def effective(row, name, slider=-1.0):
    values = [number(row[p + name], p + name) for p in ("Def", "Min", "Max")]
    default, low, high = values
    if low > high:
        raise c.MappingError("Reversed " + name + " bounds")
    q = e.normalize_slider(slider, default, low, high)
    return low + (high - low) * q


def legacy_extension(sag):
    """Distance from the selected ride position to FM3's setup extension bound."""
    sag = number(sag, "sag")
    return sag if sag <= EXTENSION_THRESHOLD else max(EXTENSION_THRESHOLD, EXTENSION_SCALE * sag)


def extension_bound(reference_y, rest_y, cap=None):
    """FM4 adds max(legacy_bound, reference_y - cap) to the shared FM3 helper."""
    reference_y, rest_y = number(reference_y, "reference_y"), number(rest_y, "rest_y")
    result = reference_y - legacy_extension(reference_y - rest_y)
    if cap is not None:
        cap = number(cap, "MaxStretchDeltaFromRideHeight")
        if cap < 0:
            raise c.MappingError("Negative extension cap")
        result = max(result, reference_y - cap)
    return result


def plan(source, candidate):
    """Validate both axles before the caller mutates anything.

The shared two-axle spring-rest solve reduces to sag = g/2 * axle_fraction /
normalized_spring_rate. Runtime mass cancels because both spring coefficients
and weight use the same positive mass factor. Radius, ride height and CMHeight
translate the positions, but cancel in this difference. This is a setup identity,
not an assertion about final aggregate CG or dynamic contact behavior.
    """
    w = number(row(source, "List_UpgradeCarBodyWeight")["CMBackFront"], "CMBackFront")
    if not .01 <= w <= .99:
        raise c.MappingError("Suspension policy requires stock distribution in [.01,.99]")
    if number(row(source, "body")["ModelWheelbase"], "ModelWheelbase") <= 0:
        raise c.MappingError("Suspension policy requires positive wheelbase")
    if number(row(source, "List_UpgradeCarBodyWeight")["Mass"], "Mass") <= 0:
        raise c.MappingError("Suspension policy requires positive base mass")
    result = {}
    for axle, fraction in (("front", w), ("rear", 1 - w)):
        a, b = row(source, "spring." + axle), row(candidate, "spring." + axle)
        # PK/owner/registry IDs can be remapped; all numeric suspension inputs
        # participating in this policy must remain the source values.
        fields = ("DefRideHeight", "MinRideHeight", "MaxRideHeight", "MaxCompressHeight",
                  "DefSpringRate", "MinSpringRate", "MaxSpringRate",
                  "ChassisPivotX", "ChassisPivotY", "TirePivotX")
        for field in fields:
            if number(a[field], axle + "." + field) != number(b[field], axle + "." + field):
                raise c.MappingError("Changed suspension input outside stock policy: " + axle + "." + field)
        height = effective(a, "RideHeight")
        rate = effective(a, "SpringRate")
        low_rate = number(a["MinSpringRate"], axle + ".MinSpringRate")
        if a["MinRideHeight"] < 0 or a["MaxRideHeight"] < 0 or low_rate <= 0 or rate <= 0:
            raise c.MappingError("Suspension policy needs nonnegative heights and positive spring range")
        # The cap is retained, not fitted to the native counterpart. Check the
        # entire selected-part spring slider interval, including default clamps.
        cap = number(b["MaxStretchDeltaFromRideHeight"], axle + ".MaxStretchDeltaFromRideHeight")
        default_sag = HALF_GRAVITY * fraction / rate
        max_sag = HALF_GRAVITY * fraction / low_rate
        required = legacy_extension(max_sag)
        slack = cap - required
        margin = NUMERIC_MARGIN * max(1.0, abs(required))
        if not math.isfinite(required) or slack <= margin:
            raise c.MappingError(
                f"{axle} extension cap cannot preserve FM3 over the selected spring range: "
                f"cap={cap:g}, required>{required:g} plus numerical margin")
        result[axle] = {
            "source_reference_height": a["MaxRideHeight"],
            "source_reference_column": "MaxRideHeight",
            "old_candidate_stock_height": row(candidate, "car")[axle.title() + "StockRideHeight"],
            "target_stock_height": a["MaxRideHeight"],
            "effective_default_ride_height": height,
            "effective_default_spring_rate": rate,
            "axle_fraction": fraction,
            "default_sag": default_sag,
            "default_extension": legacy_extension(default_sag),
            "maximum_sag_over_spring_slider": max_sag,
            "maximum_extension_over_spring_slider": required,
            "retained_max_stretch": cap,
            "cap_slack": slack,
            "numerical_guard_margin": margin,
            "cap_nonbinding_over_selected_spring_range": True,
            "separate_calibration_changes": [
                {"column": field, "source": a[field], "candidate": b[field]}
                for field in ("CamberChangeRatioCompression", "CamberChangeRatioExpansion",
                              "StaticToe", "StaticCamber", "Caster")
                if a[field] != b[field]],
        }
    return {"version": "stock-suspension-v2", "evidence": EVIDENCE, "axles": result,
            "policy": "Preserve FM3 setup reference using source MaxRideHeight; retain and audit FM4 extension cap.",
            "scope": "Selected stock parts, unchanged body/pivot/ride/rate/distribution inputs; slider range of these parts only. Separate camber/toe calibration is not covered by the scalar position proof.",
            "runtime_tested": False, "full_solver_equivalence": False,
            "mass_factor": "Positive shared runtime factor cancels in the traced setup sag identity.",
            "upgrades_and_swaps_supported": False}


def compare_geometry(source, candidate):
    """Compare offsets relative to tire radius without inventing asset geometry."""
    source_h = number(row(source, "List_UpgradeCarBodyWeight")["CMHeight"], "CMHeight")
    car = row(candidate, "car")
    w = row(candidate, "List_UpgradeCarBodyWeight")["CMBackFront"]
    target_h = row(candidate, "List_UpgradeCarBodyWeight")["CMHeight"] - (
        car["RearStockRideHeight"] + (car["FrontStockRideHeight"] - car["RearStockRideHeight"]) * w)
    axes = {}
    for axle in ("front", "rear"):
        a, b = row(source, "spring." + axle), row(candidate, "spring." + axle)
        source_ref = -(a["MaxRideHeight"] + source_h)
        target_ref = -(car[axle.title() + "StockRideHeight"] + target_h)
        tune_deltas = {}
        for slider in (-1.0, 0.0, 0.5, 1.0):
            tune_deltas[str(slider)] = (
                -(effective(b, "RideHeight", slider) + target_h)
                + effective(a, "RideHeight", slider) + source_h)
        axes[axle] = {"reference_minus_radius_source": source_ref,
                      "reference_minus_radius_candidate": target_ref,
                      "reference_delta": target_ref - source_ref,
                      "selected_position_deltas_by_slider": tune_deltas}
    return {"axles": axes, "preserved": all(
        abs(a["reference_delta"]) <= 1e-6 and all(abs(v) <= 1e-6 for v in a["selected_position_deltas_by_slider"].values())
        for a in axes.values()), "scope": "Scalar setup offsets relative to tire radius; actual tire/asset geometry is not validated."}
