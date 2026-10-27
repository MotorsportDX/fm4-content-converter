"""Drivetrain safeguards: frozen selection, family grouping and abstention."""
import copy
from pathlib import Path
import unittest

import converter as c
import drivetrain_v2 as d


@unittest.skipUnless(c.FM3_DEFAULT.exists() and c.FM4_DEFAULT.exists(),
                     "Local FM3/FM4 source databases unavailable")
class DrivetrainV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = d.collect()
        cls.frozen = d.fit(cls.data)
        cls.model = d.validate(cls.data, cls.frozen)

    def test_full_drivetrain_collection_preserves_holdout_exclusion(self):
        self.assertEqual(len(self.data["pairs"]), 309)
        self.assertNotIn(247, {p["source"]["id"] for p in self.data["pairs"]})
        self.assertNotIn(1, {p["source"]["engine_id"] for p in self.data["pairs"]})
        for pair in self.data["pairs"]:
            for side in ("source", "target"):
                self.assertIn("MomentInertia", pair[side]["nodes"][d.TRANS])
                self.assertIn("aero.front", pair[side]["nodes"])

    def test_validation_targets_cannot_train_any_parameters_or_selection(self):
        changed = copy.deepcopy(self.data)
        for pair in changed["pairs"]:
            if pair["split"] == "validation":
                pair["target"]["nodes"][d.TRANS]["MomentInertia"] = 777
                pair["target"]["nodes"]["car"]["Displacement"] = 99999
        self.assertEqual(d.fit(changed), self.frozen)

    def test_validate_preserves_frozen_parameters_thresholds_and_grouping(self):
        for key in ("selected", "policy", "candidate_menu", "cv", "grouping",
                    "training_exclusions", "selected_cv", "cv_gate_passed"):
            self.assertEqual(self.frozen[key], self.model[key])
        self.assertFalse(self.frozen["validated"])
        self.assertTrue(self.model["validated"])
        self.assertEqual(self.model["validation"]["summary"]["n"], 73)

    def test_engine_and_normalized_family_never_cross_cv_folds(self):
        pairs = [p for p in self.data["pairs"] if p["split"] == "training" and not d.parity(p)]
        folds, _ = d.fold_groups(pairs)
        engines, families = {}, {}
        for pair, fold in zip(pairs, folds):
            source = pair["source"]
            for mapping, key in ((engines, source["engine_id"]),
                                 (families, d.family_key(source["media_name"]))):
                if key in mapping:
                    self.assertEqual(mapping[key], fold)
                mapping[key] = fold
        self.assertEqual(d.family_key("NIS_23_GTR_08"), d.family_key("NIS_24_GTR_09"))

    def test_changed_specifications_do_not_fit_but_validation_is_retained(self):
        self.assertEqual(self.frozen["eligible_training_pairs"], 231)
        self.assertEqual(len(self.frozen["training_exclusions"]), 5)
        viper = next(r for r in self.model["validation"]["cars"] if r["media_name"] == "DOD_91_ViperGTSR_00")
        self.assertTrue(viper["specification_mismatches"])

    def test_supported_cv_scope_is_not_promoted_with_one_validation_family(self):
        self.assertTrue(self.frozen["cv_gate_passed"])
        self.assertEqual(self.model["validation"]["summary"]["scope_predicted"], 1)
        self.assertFalse(self.model["experimental_accepted"])
        self.assertFalse(self.model["conservative_accepted"])
        pair = next(p for p in self.data["pairs"] if p["source"]["media_name"] == "AUD_2_R10_08")
        for mode in ("conservative", "experimental", "estimated"):
            updates, notes = d.propose(pair["source"], self.model, mode)
            self.assertEqual(updates, [])
            self.assertEqual(notes[0]["reason"], "frozen_rule_gate_not_passed")

    def test_predicate_and_domain_abstain_without_target_reads(self):
        model = copy.deepcopy(self.model)
        model["experimental_accepted"] = True  # Exercise an inference branch in isolation.
        record = copy.deepcopy(next(p["source"] for p in self.data["pairs"]
                                    if p["source"]["media_name"] == "AUD_2_R10_08"))
        updates, notes = d.propose(record, model, "experimental")
        self.assertEqual(len(updates), 1)
        self.assertEqual(updates[0]["role"], d.TRANS)
        self.assertEqual(updates[0]["column"], "MomentInertia")
        self.assertTrue(notes)
        record["nodes"]["car"]["Year"] = 2026
        self.assertEqual(d.propose(record, model, "experimental")[0], [])
        record["nodes"]["car"]["Year"] = 1969
        self.assertEqual(d.propose(record, model, "experimental")[0], [])

    def test_inertia_precision_does_not_hide_retuning(self):
        self.assertFalse(d.cal.equal(0.01, 0.0101))
        raw = copy.deepcopy(self.data["pairs"][0]["source"])
        raw["nodes"][d.TRANS]["MomentInertia"] = float("nan")
        with self.assertRaises(c.MappingError):
            d.features(raw)

    def test_grouping_and_inference_features_exclude_identity_predictors(self):
        record = copy.deepcopy(self.data["pairs"][0]["source"])
        initial = d.features(record)
        record["media_name"] = "UNSEEN_EXAMPLE_00"
        record["engine_id"] = 999999
        record["nodes"]["car"]["MakeID"] = 999999
        record["nodes"]["car"]["Id"] = 999999
        record["nodes"]["engine"]["EngineName"] = "Unseen engine"
        self.assertEqual(d.features(record), initial)


if __name__ == "__main__":
    unittest.main(verbosity=2)
