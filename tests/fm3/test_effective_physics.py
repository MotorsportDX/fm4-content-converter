"""Boundary and provenance tests for the code-derived coefficient evaluator."""
import copy
import math
import unittest

from fm4_converter.fm3 import effective_physics as e


def graph():
    spring = {
        "DefSpringRate": 60., "MinSpringRate": 40., "MaxSpringRate": 80.,
        "DefDampenBumpRate": 4., "MinDampenBumpRate": 2., "MaxDampenBumpRate": 6.,
        "DefDampenReboundRate": 8., "MinDampenReboundRate": 4., "MaxDampenReboundRate": 12.,
        "DampenBumpClamp": 11., "DampenReboundClamp": 13.,
        "BumpstopStiffness": 100., "BumpstopDamping": 10.,
    }
    antiroll = {"DefSwaybarStiffness": 30., "MinSwaybarStiffness": 10.,
                "MaxSwaybarStiffness": 50., "SwaybarDamping": 3.}
    return {"media_name": "TEST", "nodes": {
        **{f"spring.{axle}": {"row": dict(spring)} for axle in ("front", "rear")},
        **{f"antiroll.{axle}": {"row": dict(antiroll)} for axle in ("front", "rear")},
        "List_UpgradeCarBodyWeight": {"row": {"Mass": 1000.}},
        "List_UpgradeEngine": {"row": {"MassDiff": 25.}},
    }}


class NormalizeTests(unittest.TestCase):
    def test_negative_slider_requests_default_positive_slider_does_not(self):
        self.assertEqual(e.normalize_slider(-1, 60, 40, 80), .5)
        self.assertEqual(e.normalize_slider(-.01, 50, 40, 80), .25)
        self.assertEqual(e.normalize_slider(0, 60, 40, 80), 0)
        self.assertEqual(e.normalize_slider(.75, 60, 40, 80), .75)
        self.assertEqual(e.normalize_slider(3, 60, 40, 80), 1)

    def test_fixed_range_uses_half_slider_and_constant_coefficient(self):
        self.assertEqual(e.normalize_slider(-1, 100, 40, 40), .5)
        g = graph()
        g["nodes"]["spring.front"]["row"].update(
            DefSpringRate=100., MinSpringRate=40., MaxSpringRate=40.)
        self.assertEqual(e.evaluate(g)["coefficients"]["front.spring"], 40)
        self.assertEqual(e.evaluate(g, tuning={"front": {"spring": .9}})
                         ["coefficients"]["front.spring"], 40)

    def test_default_outside_interval_clamps_without_rewriting_database(self):
        g = graph()
        g["nodes"]["spring.rear"]["row"].update(
            DefSpringRate=151.1875, MinSpringRate=50., MaxSpringRate=150.)
        before = copy.deepcopy(g)
        result = e.evaluate(g)
        self.assertEqual(result["coefficients"]["rear.spring"], 150.)
        self.assertEqual(result["fields"]["rear.spring"]["normalized_slider"], 1.)
        self.assertEqual(g, before)
        self.assertEqual(e.normalize_slider(-1, 5, 10, 20), 0.)

    def test_reversed_bounds_follow_actual_normalization_then_original_lerp(self):
        self.assertEqual(e.normalize_slider(-1, 50, 80, 40), .25)
        g = graph()
        g["nodes"]["spring.front"]["row"].update(
            DefSpringRate=50, MinSpringRate=80, MaxSpringRate=40)
        self.assertEqual(e.evaluate(g)["coefficients"]["front.spring"], 70.)

    def test_nonfinite_and_boolean_values_are_not_valid_parameters(self):
        for value in (float("nan"), float("inf"), True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                e.normalize_slider(value, 1, 0, 2)


class EvaluationTests(unittest.TestCase):
    def test_explicit_mass_factor_applies_once_to_all_verified_coefficients(self):
        g = graph()
        unscaled, scaled = e.evaluate(g), e.evaluate(g, mass_factor=10.25)
        self.assertEqual(len(unscaled["coefficients"]), 18)
        for key, value in unscaled["coefficients"].items():
            self.assertAlmostEqual(scaled["coefficients"][key], value * 10.25)
        self.assertEqual(unscaled["coefficients"]["front.spring"], 60.)
        self.assertFalse(unscaled["mass_factor_supplied"])
        self.assertFalse(unscaled["mass_context"]["runtime_factor_inferred"])

    def test_missing_inputs_are_unavailable_not_zero_and_plain_rows_work(self):
        g = graph()
        del g["nodes"]["spring.front"]["row"]["DampenBumpClamp"]
        g["nodes"]["spring.front"]["row"]["BumpstopDamping"] = float("nan")
        g["nodes"]["antiroll.rear"] = g["nodes"]["antiroll.rear"]["row"]
        result = e.evaluate(g)
        self.assertNotIn("front.bump_clamp", result["coefficients"])
        self.assertNotIn("front.bumpstop_damping", result["coefficients"])
        self.assertEqual(len(result["missing"]), 2)
        self.assertEqual(result["coefficients"]["rear.antiroll"], 30.)

    def test_independent_evaluation_exposes_tuning_change_without_mutation(self):
        g, target = graph(), graph()
        before = copy.deepcopy((g, target))
        result = e.compare_effective(
            g, target, candidate_tuning={"front": {"spring": 1, "bump": 0}})
        self.assertEqual(result["counts"], {"compared": 18, "equal": 16,
                                           "different": 2, "unavailable": 0})
        differences = {v["field"]: v["delta"] for v in result["fields"]}
        self.assertEqual(differences["front.spring"], 20.)
        self.assertEqual(differences["front.bump"], -2.)
        self.assertEqual((g, target), before)

    def test_raw_default_difference_can_have_equal_effective_coefficient(self):
        a, b = graph(), graph()
        a["nodes"]["spring.front"]["row"]["DefSpringRate"] = 81
        b["nodes"]["spring.front"]["row"]["DefSpringRate"] = 90
        result = e.compare_effective(a, b)
        self.assertEqual(result["counts"]["different"], 0)
        self.assertEqual(result["source"]["coefficients"]["front.spring"], 80)

    def test_visible_mass_change_is_flagged_but_not_guessed_into_coefficients(self):
        a, b = graph(), graph()
        b["nodes"]["List_UpgradeEngine"]["row"]["MassDiff"] = 50
        result = e.compare_effective(a, b)
        self.assertEqual(result["counts"]["different"], 0)
        self.assertFalse(result["mass_context"]["visible_fields_equal"])
        self.assertFalse(result["mass_context"]["runtime_factor_equality_proven"])
        result = e.compare_effective(a, b, source_mass_factor=10, candidate_mass_factor=12)
        self.assertEqual(result["counts"]["different"], 18)

    def test_mixed_bases_do_not_report_misleading_equal_or_error_counts(self):
        result = e.compare_effective(graph(), graph(), source_mass_factor=10)
        self.assertEqual(result["basis"], "mixed_bases_not_comparable")
        self.assertEqual(result["counts"]["compared"], 0)
        self.assertEqual(result["counts"]["unavailable"], 18)

    def test_invalid_tuning_mass_factor_and_tolerance_rejected(self):
        for kwargs in ({"mass_factor": 0}, {"mass_factor": math.inf},
                       {"tuning": {"left": {}}}, {"tuning": {"front": {"typo": 1}}}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                e.evaluate(graph(), **kwargs)
        with self.assertRaises(ValueError):
            e.compare_effective(graph(), graph(), abs_tol=-1)


try:
    from fm4_converter.fm3 import converter as c
    HAS_DATABASES = c.FM3_DEFAULT.exists() and c.FM4_DEFAULT.exists()
except ImportError:
    HAS_DATABASES = False


@unittest.skipUnless(HAS_DATABASES, "Local source databases unavailable")
class LocalAudiTests(unittest.TestCase):
    def test_actual_audi_r10_out_of_range_default_evaluates_to_native_endpoint(self):
        for path in (c.FM3_DEFAULT, c.FM4_DEFAULT):
            with self.subTest(database=path):
                db = c.connect(path)
                try:
                    g = c.extract_stock(db, "AUD_2_R10_08")
                finally:
                    db.close()
                source = g["nodes"]["spring.rear"]["row"]
                self.assertEqual(source["DefSpringRate"], 151.1875)
                self.assertEqual(source["MaxSpringRate"], 150.)
                result = e.evaluate(g)
                self.assertEqual(result["coefficients"]["rear.spring"], 150.)
                self.assertEqual(source["DefSpringRate"], 151.1875)


if __name__ == "__main__":
    unittest.main()
