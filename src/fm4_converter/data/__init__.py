"""Frozen calibration data that the one-command converter (`fm4_converter.cli`) ships with.

The files are the reviewed outputs the tested packages were built with (FM3: `fm3-only-v3`,
FM2: `package-v5`), so a player's conversion uses the same rules without the local
`outputs/` evidence. They hold fitted rules, model coefficients and car names, not game
assets. `FILES` records where each file came from, and what was removed from it:

- `fm3/rules.json`: `remaining7.selection_results` (2.7 MB of model-selection diagnostics)
  is removed. Batch packaging runs the conservative mode, where `remaining.propose` only
  notes that the remaining-seven estimates are experimental and reads no model.
- `fm2/cars.json`: the FM2 MediaNames whose inventory route is `fm2_only`, the 55 cars of
  `package-v5`.
"""
from hashlib import sha256
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent

FILES = {
    "fm3/rules.json": dict(
        sha256="9d62748d7cf89dc5cf08d703d28dece75a81ff9114990656d9c550983232aacd",
        origin="outputs/fm-car-converter/benchmark30-refinements-v1/rules.json",
        origin_sha256="ab79d65eb4e85412b7d5e2399e1705406ea771dc70be531e46775ad26d2553df",
        removed=["remaining7.selection_results"]),
    "fm3/pi-model.json": dict(
        sha256="aa3dbc57424ab4c89a3f5febbfadbe8de8ac6d08406621c75e559c08fb2e2edf",
        origin="outputs/fm-car-converter/pi-class-v1/pi-model.json",
        origin_sha256="aa3dbc57424ab4c89a3f5febbfadbe8de8ac6d08406621c75e559c08fb2e2edf",
        removed=[]),
    "fm3/value-scales.json": dict(
        sha256="8250fb98cd80929cab668c97ea9b379b02213194814fa9d9ebd1bf846aa26e5f",
        origin="outputs/fm-car-converter/value-scales-v1/rules.json",
        origin_sha256="8250fb98cd80929cab668c97ea9b379b02213194814fa9d9ebd1bf846aa26e5f",
        removed=[]),
    "fm2/study.json": dict(
        sha256="49ddaf43a983def5dc26ca982c447a436fc463fd2e7b1d27129a75f0251dc035",
        origin="outputs/car-fm2-research-2026-11-02/physics/study.json",
        origin_sha256="49ddaf43a983def5dc26ca982c447a436fc463fd2e7b1d27129a75f0251dc035",
        removed=[]),
    "fm2/cars.json": dict(
        sha256="29d7863accd3d9b10a7b0dcb6cca02a3807adade4b766c30bfdd5c678acec50f",
        origin="outputs/car-fm2-research-2026-11-02/inventory.json",
        origin_sha256="f2badf5cfba1817f4c01499a9ed5b9d8bc5203db84e3585ed389482ee4985212",
        removed=["cars whose route is not fm2_only", "every field but MediaName"]),
}


def path(name):
    """Path of a frozen file after checking its SHA-256."""
    found = ROOT / name
    expected = FILES[name]["sha256"]
    actual = sha256(found.read_bytes()).hexdigest()
    if actual != expected:
        raise ValueError(f"Frozen data {name} changed: {actual}, expected {expected}")
    return found


def load(name):
    return json.loads(path(name).read_text(encoding="utf-8"))
