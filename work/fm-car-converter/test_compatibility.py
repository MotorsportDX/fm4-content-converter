"""Compatibility checks must expose mismatches without changing a candidate."""
import copy
import unittest

import compatibility as k
import converter as c


def graph(wrapped=True):
    nodes = {
        "car": {"Id": 10, "MediaName": "EXAMPLE_00", "Year": 2000, "MakeID": 7,
                "DriveTypeID": 2, "EnginePlacementID": 1, "AspirationTypeId": 1, "Displacement": 3000},
        "engine": {"EngineID": 5, "ConfigID": 1, "CylinderID": 3,
                   "Rotary": 0, "Diesel": 0, "AspirationID_Stock": 1},
        "List_UpgradeCarBodyWeight": {"Mass": 1000},
        "torque.full": {"NumTorqueValues": 3, "TorqueScale": 100, "v0": 0, "v1": 1, "v2": -1},
        "List_UpgradeEngineCamshaft": {"NumRPMEntriesArray": 3, "TorqueCurveMaxRPM": 1000,
                                      "RedlineRPM": 800, "StartRPM": 500},
    }
    return {"media_name": "EXAMPLE_00", "nodes": {role: {"row": value} for role, value in nodes.items()}
            if wrapped else nodes}


class CompatibilityTests(unittest.TestCase):
    def test_same_ids_do_not_override_engine_specification_mismatch(self):
        a, b = graph(), graph()
        b["nodes"]["engine"]["row"]["CylinderID"] = 4
        b["nodes"]["car"]["row"]["Displacement"] = 4000
        result = k.pair_eligibility(a, b)
        self.assertFalse(result["eligible"])
        self.assertEqual({r["column"] for r in result["exclusion_reasons"]}, {"CylinderID", "Displacement"})

    def test_minimal_cohort_records_and_graphs_are_equivalent(self):
        self.assertEqual(k.pair_eligibility(graph(), graph()),
                         k.pair_eligibility(graph(False), graph(False)))

    def test_mass_change_requires_review_not_automatic_variant_exclusion(self):
        a, b = graph(), graph()
        b["nodes"]["List_UpgradeCarBodyWeight"]["row"]["Mass"] = 1200
        result = k.audit(a, b)
        self.assertTrue(result["pairing"]["eligible"])
        self.assertEqual(result["pairing"]["review_reasons"][0]["reason"], "large_mass_change_requires_review")
        self.assertTrue(result["requires_manual_review"])

    def test_missing_specification_fails_closed(self):
        a, b = graph(), graph()
        del b["nodes"]["engine"]
        result = k.pair_eligibility(a, b)
        self.assertFalse(result["eligible"])
        self.assertEqual(len(result["missing_required_fields"]), 5)

    def test_small_displacement_revision_is_reviewed(self):
        a, b = graph(), graph()
        b["nodes"]["car"]["row"]["Displacement"] = 3001
        result = k.pair_eligibility(a, b)
        self.assertTrue(result["eligible"])
        self.assertEqual(result["review_reasons"][0]["column"], "Displacement")

    def test_domain_shift_blocks_rpm_aligned_claim_even_with_identical_values(self):
        a, b = graph(), graph()
        b["nodes"]["List_UpgradeEngineCamshaft"]["row"]["TorqueCurveMaxRPM"] = 1100
        result = k.torque_audit(a, b)
        self.assertFalse(result["same_declared_domain"])
        self.assertTrue(result["sampling_domains_differ"])
        self.assertEqual(result["same_index_differences"], [])
        self.assertIn("not_rpm_aligned", result["comparison_interpretation"])
        self.assertFalse(result["resampling_performed"])

    def test_curve_length_and_camshaft_count_must_agree(self):
        a, b = graph(), graph()
        b["nodes"]["List_UpgradeEngineCamshaft"]["row"]["NumRPMEntriesArray"] = 4
        result = k.torque_audit(a, b)
        self.assertFalse(result["same_declared_domain"])
        self.assertIn("camshaft_count_disagrees_with_curve_count", result["reference"]["issues"])
        self.assertEqual(result["same_index_compared"], 0)

    def test_missing_active_sample_is_not_treated_as_zero(self):
        a, b = graph(), graph()
        del b["nodes"]["torque.full"]["row"]["v1"]
        result = k.torque_audit(a, b)
        self.assertFalse(result["same_declared_domain"])
        self.assertIn("missing_or_nonfinite_active_sample_v1", result["reference"]["issues"])

    def test_inactive_padding_is_not_part_of_active_comparison(self):
        a, b = graph(), graph()
        b["nodes"]["torque.full"]["row"]["v99"] = 99
        result = k.torque_audit(a, b)
        self.assertTrue(result["same_declared_domain"])
        self.assertEqual(result["same_index_compared"], 3)
        self.assertFalse(result["runtime_interpolation_verified"])

    def test_missing_optional_part_is_reported_but_zero_throttle_is_expected(self):
        a, b = graph(), graph()
        a["nodes"]["torque.zero"] = {"row": {}}
        b["nodes"][k.RESTRICTOR] = {"row": {"TorqueScale": 1}}
        result = k.audit(a, b)
        self.assertEqual(result["stock_role_changes"],
                         [{"role": k.RESTRICTOR, "source_present": False, "reference_present": True}])
        self.assertTrue(result["requires_manual_review"])

    def test_audit_is_pure_and_handles_missing_torque_role(self):
        a, b = graph(), graph()
        del b["nodes"]["torque.full"]
        before = copy.deepcopy((a, b))
        result = k.audit(a, b)
        self.assertEqual((a, b), before)
        self.assertFalse(result["candidate_mutated"])
        self.assertTrue(result["requires_manual_review"])


@unittest.skipUnless(c.FM3_DEFAULT.exists() and c.FM4_DEFAULT.exists(), "Local source databases unavailable")
class LocalCompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = c.connect(c.FM3_DEFAULT)
        cls.dst = c.connect(c.FM4_DEFAULT)

    @classmethod
    def tearDownClass(cls):
        cls.src.close()
        cls.dst.close()

    def test_shared_registry_domains_are_verified(self):
        domains = k.verify_registry_domains(self.src, self.dst)
        self.assertTrue(all(item["compatible_source_ids"] for item in domains.values()))

    def test_actual_viper_has_configuration_mismatch(self):
        name = "DOD_91_ViperGTSR_00"
        result = k.audit(c.extract_stock(self.src, name), c.extract_stock(self.dst, name))
        self.assertFalse(result["pairing"]["eligible"])
        self.assertEqual({r["column"] for r in result["pairing"]["exclusion_reasons"]},
                         {"CylinderID", "Displacement"})

    def test_actual_ferrari_requires_curve_review_and_keeps_both_domains(self):
        name = "FER_12_333SP_98"
        result = k.audit(c.extract_stock(self.src, name), c.extract_stock(self.dst, name))
        curve = result["torque_domain"]
        self.assertTrue(result["pairing"]["eligible"])
        self.assertEqual((curve["source"]["active_count"], curve["reference"]["active_count"]), (151, 123))
        self.assertEqual((curve["source"]["max_rpm"], curve["reference"]["max_rpm"]), (15000, 12250))
        self.assertFalse(curve["resampling_performed"])
        self.assertEqual(result["stock_role_changes"][0]["role"], k.RESTRICTOR)


if __name__ == "__main__":
    unittest.main()
