"""Check fitting isolation, abstention, inference and native tyre dependencies."""
import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest

from fm4_converter.fm3 import calibration as cal
from fm4_converter.fm3 import converter as c
from fm4_converter.fm3 import remaining as r


AVAILABLE = (c.FM3_DEFAULT.exists() and c.FM4_DEFAULT.exists()
             and importlib.util.find_spec("numpy") is not None)


@unittest.skipUnless(AVAILABLE, "Local FM3/FM4 databases and NumPy required for fitting")
class RemainingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src, cls.dst = c.connect(c.FM3_DEFAULT), c.connect(c.FM4_DEFAULT)
        cls.data = cal.collect(cls.src,cls.dst)
        cls.frozen = r.select_models(cls.data)
        cls.model = copy.deepcopy(cls.frozen)
        cls.metrics = r.validate_models(cls.data,cls.model)
        cls.graph = c.extract_stock(cls.src,c.MEDIA)
        cls.record = {"nodes":{k:v["row"] for k,v in cls.graph["nodes"].items()}}
        cls.old = cal.fit_rules(cls.data)
        cal.validate_rules(cls.data,cls.old)
        cls.combined = {**cls.old, "remaining7":cls.model}

    @classmethod
    def tearDownClass(cls):
        cls.src.close()
        cls.dst.close()

    def test_fit_does_not_read_validation_targets(self):
        changed = copy.deepcopy(self.data)
        for p in changed["pairs"]:
            if p["split"] == "validation":
                p["target"] = {"unreadable":"No calibration may be read during selection"}
        self.assertEqual(self.frozen, r.select_models(changed))

    def test_validation_does_not_refit_parameters_or_policy(self):
        self.assertEqual(self.frozen["policy"], self.model["policy"])
        self.assertEqual(self.frozen["selection_results"], self.model["selection_results"])
        for task in r.TASKS:
            self.assertEqual(self.frozen["models"][task],
                             {k:v for k,v in self.model["models"][task].items()
                              if k not in ("validation_favorable","apply_experimental")})

    def test_new_rules_do_not_change_conservative_or_estimated_modes(self):
        for mode in ("conservative","estimated"):
            a = c.convert(self.src,self.dst,self.graph)
            b = copy.deepcopy(a)
            cal.apply_to_result(a,self.graph,self.old,mode)
            cal.apply_to_result(b,self.graph,self.combined,mode)
            self.assertEqual(a["candidate"],b["candidate"])

    def test_identity_metadata_is_not_a_predictor(self):
        changed = copy.deepcopy(self.record)
        for key in ("Id","MediaName","MakeID","ModelId","PerformanceIndex"):
            changed["nodes"]["car"][key] = "not_available"
        self.assertEqual(r.predictions(changed,self.model),r.predictions(self.record,self.model))

    def test_outside_training_domain_abstains(self):
        changed = copy.deepcopy(self.record)
        changed["nodes"]["car"]["Year"] = 2026
        changed["nodes"]["body"]["ModelFrontStockRideHeight"] = 99
        updates, notes = r.propose(changed,self.model,"experimental")
        self.assertFalse(any(u["rule"] in ("remaining7_grip","remaining7_cg") for u in updates))
        self.assertTrue(any(n["reason"]=="outside_training_domain" for n in notes))

    def test_nonfinite_features_fail_closed(self):
        changed = copy.deepcopy(self.record)
        changed["nodes"][r.WEIGHT]["CMHeight"] = float("nan")
        with self.assertRaises(c.MappingError):
            r.propose(changed,self.model,"experimental")

    def test_tank_is_not_applied_even_when_its_numeric_gate_passes(self):
        model = copy.deepcopy(self.model)
        model["models"]["tank"]["apply_experimental"] = True
        updates, notes = r.propose(self.record,model,"experimental")
        self.assertFalse(any(u["column"]=="GasTankSize" for u in updates))
        self.assertTrue(any(n["reason"]=="independent_specification_required" for n in notes))

    def test_experimental_sqlite_and_toyota_comparison(self):
        result = c.convert(self.src,self.dst,self.graph)
        cal.apply_to_result(result,self.graph,self.combined,"experimental")
        c.refresh_tire_dependencies(self.dst,result)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"candidate.slt"
            c.write_patch(path,self.dst,result["candidate"])
            self.assertTrue(c.validate(result["candidate"],self.dst,path)["passed"])
        native = c.extract_stock(self.dst,c.MEDIA)
        comparison = c.compare(result["candidate"],native,self.dst)
        self.assertEqual(comparison["differences_by_category"]["physics"],7)
        for role,col in r.FIELDS[:5]:
            b = cal.source_baseline(self.record,role,col)
            a = result["candidate"]["nodes"][role]["row"][col]
            t = native["nodes"][role]["row"][col]
            self.assertLess(abs(a-t),abs(b-t))
        self.assertEqual(result["candidate"]["nodes"]["engine"]["row"]["GasTankSize"],20)

    def test_compound_changes_refresh_all_selected_native_curves(self):
        result = c.convert(self.src,self.dst,self.graph)
        result["candidate"]["nodes"][r.TIRE]["row"]["TireCompoundID"] = 2
        c.refresh_tire_dependencies(self.dst,result)
        selected = result["native_tire_dependencies"][0]
        self.assertEqual(selected["id"],2)
        registry = next(e for e in result["external_dependencies"] if e["table"]=="List_TireCompound")
        self.assertEqual(registry["target_id"],2)
        self.assertEqual(registry["row"],selected["row"])
        self.assertEqual(registry["baseline_target_id"],5)
        self.assertGreater(len(result["native_tire_dependencies"]),1)
        self.assertNotIn("List_TireCompound",{n["table"] for n in result["candidate"]["nodes"].values()})

    def test_missing_compound_reference_fails_closed(self):
        result = c.convert(self.src,self.dst,self.graph)
        result["candidate"]["nodes"][r.TIRE]["row"]["TireCompoundID"] = -9876543
        with self.assertRaises(c.MappingError):
            c.refresh_tire_dependencies(self.dst,result)

    def test_chassis_relation_and_model_match_are_separate_metrics(self):
        self.assertEqual(self.metrics["relations"]["exceptions"],[])
        self.assertEqual(self.metrics["relations"]["n"],73)
        self.assertLess(self.metrics["grip"]["predicted_matches"],73)
        self.assertTrue(any(x["matches"]<73 for x in self.metrics["chassis_fields"]))

    def test_model_json_roundtrip_does_not_change_predictions(self):
        import json
        loaded = json.loads(json.dumps(self.model))
        # Leaf-distribution JSON keys become strings, but numeric predictions do not.
        self.assertEqual({t:v[0] for t,v in r.predictions(self.record,self.model).items()},
                         {t:v[0] for t,v in r.predictions(self.record,loaded).items()})


if __name__ == "__main__":
    unittest.main()
