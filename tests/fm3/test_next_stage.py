"""Integration guards for replacement profiles, frozen arms and atomic updates."""
import copy
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fm4_converter.fm3 import benchmark as b
from fm4_converter.fm3 import calibration as cal
from fm4_converter.fm3 import converter as c


class ModeTests(unittest.TestCase):
    def test_previous_benchmark_arms_do_not_get_next_profiles(self):
        model={"base":1,"benchmark_refinements":{"old":True},"suspension_v2":{"new":1},"drivetrain_v2":{"new":2}}
        old,mode=b.profile_for_mode(model,"experimental")
        self.assertEqual(old,{"base":1})
        self.assertEqual(mode,"experimental")
        refined,mode=b.profile_for_mode(model,"refined_conservative")
        self.assertEqual(refined,{"base":1,"benchmark_refinements":{"old":True}})
        self.assertEqual(mode,"conservative")
        upcoming,mode=b.profile_for_mode(model,"next_experimental")
        self.assertEqual(upcoming,model)
        self.assertEqual(mode,"experimental")

    def test_existing_rules_keep_five_modes(self):
        self.assertEqual(b.modes_for({}),b.MODES)
        self.assertEqual(len(b.modes_for({"suspension_v2":{}})),7)

    def test_audit_strata_keep_changed_variants_in_raw_totals(self):
        def entry(name,eligible=True,same_domain=True,roles=False,review=False):
            return {"media_name":name,"modes":{},"diagnostics":{"compatibility":{
                "pairing":{"eligible":eligible},"torque_domain":{"same_declared_domain":same_domain},
                "stock_role_changes":[{"role":"restrictor"}] if roles else [],
                "requires_manual_review":review}}}
        cars=[entry("normal"),entry("variant",eligible=False,review=True),
              entry("domain",same_domain=False,roles=True,review=True),
              {"media_name":"failed","failure":"extraction"}]
        summary=b.comparison_strata(cars,b.MODES)
        self.assertEqual(summary["strata"]["all_attempted"]["attempted"],4)
        self.assertEqual(summary["strata"]["same_specification"]["attempted"],2)
        self.assertEqual(summary["strata"]["same_specification_domain_and_roles"]["media_names"],["normal"])
        self.assertEqual(summary["strata"]["requires_manual_review"]["attempted"],2)
        self.assertEqual(summary["unaudited_media_names"],["failed"])


@unittest.skipUnless(c.FM3_DEFAULT.exists() and c.FM4_DEFAULT.exists(),"Local databases unavailable")
class NextIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src,cls.dst=c.connect(c.FM3_DEFAULT),c.connect(c.FM4_DEFAULT)
        cls.graph=c.extract_stock(cls.src,c.MEDIA)
        data=cal.collect(cls.src,cls.dst)
        cls.model=cal.fit_rules(data)
        cal.validate_rules(data,cls.model)

    @classmethod
    def tearDownClass(cls):
        cls.src.close()
        cls.dst.close()

    def test_replacement_abstention_does_not_apply_legacy_suspension(self):
        base=c.convert(self.src,self.dst,self.graph)
        old=copy.deepcopy(base)
        cal.apply_to_result(old,self.graph,self.model,"experimental")
        self.assertNotEqual(old["candidate"]["nodes"]["spring.front"]["row"]["DefSpringRate"],
                            base["candidate"]["nodes"]["spring.front"]["row"]["DefSpringRate"])
        stub=SimpleNamespace(propose=lambda record,model,mode:([],[{"status":"abstain"}]))
        upcoming={**self.model,"suspension_v2":{}}
        with patch.dict(sys.modules,{"fm4_converter.fm3.suspension_v2":stub}):
            cal.apply_to_result(base,self.graph,upcoming,"experimental")
        for role in ("spring.front","spring.rear","antiroll.front","antiroll.rear"):
            self.assertEqual(base["candidate"]["nodes"][role]["row"]["Def"+(
                             "SpringRate" if role.startswith("spring") else "SwaybarStiffness")],
                             self.graph["nodes"][role]["row"]["Def"+(
                             "SpringRate" if role.startswith("spring") else "SwaybarStiffness")])
        self.assertEqual(base["calibration"]["active_suspension_profile"],"suspension_v2")

    def test_bad_proposals_leave_all_candidate_rows_unchanged(self):
        valid={"role":"car","column":"SteerMaxAngle","value":42.0,
               "rule":"test","confidence":"test"}
        cases=[
            [valid,{**valid,"value":43.0}],
            [valid,{**valid,"column":"SteerMaxAngVelTurning","value":float("nan")}],
            [valid,{**valid,"column":"unknown_column","value":1.0}],
        ]
        for proposals in cases:
            result=c.convert(self.src,self.dst,self.graph)
            saved=copy.deepcopy(result)
            with patch.object(cal,"propose",return_value=(proposals,[])):
                with self.assertRaises(c.MappingError):
                    cal.apply_to_result(result,self.graph,self.model,"conservative")
            self.assertEqual(result,saved)

    def test_missing_mapping_preflight_is_atomic(self):
        result=c.convert(self.src,self.dst,self.graph)
        result["mapping"]=[m for m in result["mapping"] if not (
            m["role"]=="car" and m["target_column"]=="SteerMaxAngVelStraighten")]
        saved=copy.deepcopy(result)
        with self.assertRaises(c.MappingError):
            cal.apply_to_result(result,self.graph,self.model,"conservative")
        self.assertEqual(result,saved)

    def test_missing_metadata_or_unserializable_model_is_atomic(self):
        for broken in (
            {k:v for k,v in self.model.items() if k!="heldout_media"},
            {**self.model,"bad_metadata":object()},
        ):
            result=c.convert(self.src,self.dst,self.graph)
            saved=copy.deepcopy(result)
            with self.assertRaises(c.MappingError):
                cal.apply_to_result(result,self.graph,broken,"conservative")
            self.assertEqual(result,saved)


if __name__=="__main__":
    unittest.main()
