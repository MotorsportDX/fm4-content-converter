"""Suspension fitting isolation, uncertainty gates and fixed-range safety."""
import copy
import json
from pathlib import Path
import unittest

import calibration as cal
import converter as c
import suspension_v2 as s


@unittest.skipUnless(c.FM3_DEFAULT.exists() and c.FM4_DEFAULT.exists(),
                     "Local paired databases required")
class SuspensionV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src, cls.dst = c.connect(c.FM3_DEFAULT), c.connect(c.FM4_DEFAULT)
        cls.data = cal.collect(cls.src, cls.dst)
        cls.frozen = s.fit(cls.data)
        cls.model = copy.deepcopy(cls.frozen)
        s.validate(cls.data, cls.model)
        cls.example = next(p["source"] for p in cls.data["pairs"]
                           if s.propose(p["source"], cls.model, "experimental")[0])

    @classmethod
    def tearDownClass(cls):
        cls.src.close()
        cls.dst.close()

    def test_validation_targets_not_read_during_fit(self):
        changed = copy.deepcopy(self.data)
        for pair in changed["pairs"]:
            if pair["split"] == "validation":
                pair["target"] = {"unreadable": True}
        self.assertEqual(s.fit(changed), self.frozen)

    def test_validation_adds_decision_without_refitting(self):
        for key in ("policy", "candidates", "component_candidates", "selected",
                    "component_selected", "component_selected_cv", "cv_groups"):
            self.assertEqual(self.frozen[key], self.model[key])
        self.assertNotIn(247, self.model["training_ids"])
        self.assertNotIn(1, self.model["training_engine_ids"])
        for pair in self.data["pairs"]:
            if pair["split"] == "training":
                key = str(pair["source"]["engine_id"])
                self.assertEqual(self.model["cv_groups"][key],
                                 s.fold(pair["source"], self.model["policy"]))

    def test_rejected_components_do_not_apply_in_estimated_or_conservative(self):
        rejected = copy.deepcopy(self.model)
        rejected["accepted"] = rejected["component_accepted"] = False
        for mode in ("conservative", "estimated"):
            updates, _ = s.propose(self.example, rejected, mode)
            self.assertEqual(updates, [])
        updates, notes = s.propose(self.example, rejected, "experimental")
        self.assertTrue(updates)
        self.assertIn("EXPERIMENT_ONLY_validation_gate_failed", {n["status"] for n in notes})

    def test_inference_identity_and_target_are_not_required(self):
        changed = copy.deepcopy(self.example)
        for key in ("id", "media_name", "engine_id", "body_id"):
            changed.pop(key, None)
        for key in ("Id", "MediaName", "MakeID", "ModelId", "PerformanceIndex"):
            changed["nodes"]["car"][key] = "unavailable"
        self.assertEqual(s.propose(changed, self.model, "experimental"),
                         s.propose(self.example, self.model, "experimental"))

    def test_fixed_triplets_are_atomic_and_no_other_fields_are_changed(self):
        updates, _ = s.propose(self.example, self.model, "experimental")
        keys = {(u["role"], u["column"]) for u in updates}
        self.assertFalse(keys - set(s.FIELDS))
        for role, field in s.BASE_FIELDS:
            values = [u["value"] for u in updates if u["role"] == role
                      and u["column"] in [p + field for p in ("Min", "Def", "Max")]]
            self.assertIn(len(values), (0, 3))
            self.assertLessEqual(len(set(values)), 1)

    def test_race_adjustable_and_source_anomaly_abstain(self):
        for kind in ("race", "adjustable", "source_tuning_anomaly"):
            changed = copy.deepcopy(self.example)
            if kind == "race":
                changed["nodes"]["car"]["CarTypeID"] = 3
            elif kind == "adjustable":
                changed["nodes"]["spring.front"]["MinSpringRate"] *= .5
            else:
                changed["nodes"]["spring.front"]["DefSpringRate"] *= 10
            updates, notes = s.propose(changed, self.model, "experimental")
            self.assertFalse(updates)
            self.assertIn("abstain_" + kind, {n["status"] for n in notes})

    def test_malformed_missing_nonfinite_and_unknown_tier_abstain(self):
        missing = copy.deepcopy(self.example)
        del missing["nodes"]["spring.front"]
        malformed = copy.deepcopy(self.example)
        malformed["nodes"]["car"]["DriveTypeID"] = None
        nonfinite = copy.deepcopy(self.example)
        nonfinite["nodes"][s.WEIGHT]["Mass"] = float("nan")
        for record in ({}, missing, malformed, nonfinite):
            updates, notes = s.propose(record, self.model, "experimental")
            self.assertFalse(updates)
            self.assertTrue(notes)
        unseen = copy.deepcopy(self.example)
        for prefix in ("Min", "Def", "Max"):
            unseen["nodes"]["spring.front"][prefix + "SpringRate"] = 12345
        self.assertFalse(s.propose(unseen, self.model, "experimental")[0])

    def test_component_training_intervals_do_not_cross_identity(self):
        fitted = self.model["component_selected"]
        for group in fitted["groups"].values():
            self.assertGreaterEqual(group["support"], fitted["spec"]["min_leaf"])
            for rule in group["rules"]:
                lo, hi = rule["training_ratio_min"], rule["training_ratio_max"]
                self.assertTrue(hi < 1 or lo > 1)
                self.assertGreaterEqual(rule["ratio"], min(1, lo))
                self.assertLessEqual(rule["ratio"], max(1, hi))

    def test_specification_mismatch_and_missing_spec_flagged(self):
        pair = copy.deepcopy(self.data["pairs"][0])
        pair["target"]["nodes"]["engine"]["CylinderID"] += 1
        self.assertTrue(s.spec_flags(pair))
        del pair["target"]["nodes"]["car"]["DriveTypeID"]
        self.assertTrue(any(f.startswith("missing:") for f in s.spec_flags(pair)))

    def test_serialization_preserves_inference_and_source_record(self):
        before = copy.deepcopy(self.example)
        restored = json.loads(json.dumps(self.model))
        self.assertEqual(s.propose(self.example, restored, "experimental"),
                         s.propose(self.example, self.model, "experimental"))
        self.assertEqual(self.example, before)


if __name__ == "__main__":
    unittest.main()
