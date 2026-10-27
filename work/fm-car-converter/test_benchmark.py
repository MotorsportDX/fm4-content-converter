"""Benchmark completeness, inherited data anomalies and new-rule safeguards."""
import copy
from pathlib import Path
import tempfile
import unittest

import benchmark as b
import calibration as cal
import converter as c
import refinements as r


@unittest.skipUnless(c.FM3_DEFAULT.exists() and c.FM4_DEFAULT.exists(),"Local databases unavailable")
class BenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src,cls.dst=c.connect(c.FM3_DEFAULT),c.connect(c.FM4_DEFAULT)
        cls.data=cal.collect(cls.src,cls.dst)
        cls.panel=b.selection(cls.data)
        cls.frozen=r.fit(cls.data)
        cls.model=r.validate(cls.data,copy.deepcopy(cls.frozen))
        cls.audi=c.extract_stock(cls.src,"AUD_2_R10_08")

    @classmethod
    def tearDownClass(cls):
        cls.src.close()
        cls.dst.close()

    def test_panel_is_30_distinct_validation_cars_with_diversity(self):
        p=self.panel
        self.assertEqual(len(p["cars"]),30)
        self.assertEqual(p["coverage"]["drive"],{"RWD":18,"FWD":6,"AWD":6})
        self.assertEqual(p["coverage"]["placement"],{"Front":19,"Mid":11})
        self.assertEqual(len({x["source_engine_id"] for x in p["cars"]}),30)
        training={x["source"]["engine_id"] for x in self.data["pairs"] if x["split"]=="training"}
        self.assertFalse(training & {x["source_engine_id"] for x in p["cars"]})
        self.assertFalse(p["new_independent_test_set"])

    def test_new_fitting_does_not_read_validation_targets(self):
        changed=copy.deepcopy(self.data)
        for p in changed["pairs"]:
            if p["split"]=="validation": p["target"]=None
        self.assertEqual(self.frozen,r.fit(changed))

    def test_validation_does_not_change_fitted_parameters(self):
        self.assertEqual(self.frozen["policy"],self.model["policy"])
        for before,after in zip(self.frozen["entries"],self.model["entries"]):
            self.assertEqual(before,{k:after[k] for k in before})

    def test_rules_gate_each_brake_branch_separately(self):
        accepted={e["source"]:e["accepted"] for e in self.model["entries"] if e["family"]=="braking"}
        self.assertEqual(accepted,{1.01:True,1.03:False,1.05:False})
        # Source 1.05 cannot become a conservative rule despite perfect training.
        graph=c.extract_stock(self.src,"BUG_Veyron_09")
        record={"nodes":{k:v["row"] for k,v in graph["nodes"].items()}}
        updates,_=r.propose(record,self.model,"conservative")
        self.assertFalse(any(x["rule"]=="refined_braking" for x in updates))
        updates,_=r.propose(record,self.model,"experimental")
        self.assertTrue(any(x["rule"]=="refined_braking" and not x["accepted"] for x in updates))

    def test_camber_car_support_is_not_doubled_by_axles_or_columns(self):
        rule=next(x for x in self.model["entries"] if x["family"]=="independent_camber")
        self.assertEqual(rule["training_cars"],60)
        self.assertGreater(len(rule["training_observations"]),rule["training_cars"])
        self.assertEqual(rule["validation_cars"],30)

    def test_solid_axle_and_unknown_brake_values_abstain(self):
        graph=c.extract_stock(self.src,"HON_CivicVti_94")
        record={"nodes":{k:copy.deepcopy(v["row"]) for k,v in graph["nodes"].items()}}
        record["nodes"]["List_UpgradeBrakes"]["GameFrictionScaleBraking"]=1.234
        for axle in ("front","rear"):
            row=record["nodes"]["spring."+axle]
            row["SuspensionPhysicsTypeID"]=1
            row["CamberChangeRatioCompression"]=row["CamberChangeRatioExpansion"]=0
            row["StaticToe"]=.5
        updates,_=r.propose(record,self.model,"experimental")
        self.assertEqual(updates,[])

    def test_inherited_stock_bound_violation_warns_without_changing_values(self):
        result=c.convert(self.src,self.dst,self.audi)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"candidate.slt"
            c.write_patch(path,self.dst,result["candidate"])
            strict=c.validate(result["candidate"],self.dst,path)
            self.assertFalse(strict["passed"])
            inherited=c.validate(result["candidate"],self.dst,path,source=self.audi)
            self.assertTrue(inherited["passed"])
            self.assertTrue(inherited["stock_tuning_review_required"])
            self.assertEqual(len(inherited["warnings"]),1)
            self.assertEqual(result["candidate"]["nodes"]["spring.rear"]["row"]["DefSpringRate"],151.1875)

    def test_new_bound_violation_still_fails_with_source_provenance(self):
        result=c.convert(self.src,self.dst,self.audi)
        result["candidate"]["nodes"]["spring.rear"]["row"]["DefSpringRate"]=160
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"candidate.slt"
            c.write_patch(path,self.dst,result["candidate"])
            self.assertFalse(c.validate(result["candidate"],self.dst,path,source=self.audi)["passed"])

    def test_inverted_source_bounds_are_not_accepted_as_inherited(self):
        source=copy.deepcopy(self.audi)
        source["nodes"]["spring.rear"]["row"]["MinSpringRate"]=180
        result=c.convert(self.src,self.dst,source)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"candidate.slt"
            c.write_patch(path,self.dst,result["candidate"])
            self.assertFalse(c.validate(result["candidate"],self.dst,path,source=source)["passed"])

    def test_variant_and_missing_restrictor_are_visible(self):
        name="DOD_91_ViperGTSR_00"
        source,reference=c.extract_stock(self.src,name),c.extract_stock(self.dst,name)
        result=c.convert(self.src,self.dst,source)
        comp=c.compare(result["candidate"],reference,self.dst)
        audit=b.diagnostic_audit(source,reference,{"baseline":comp})
        self.assertTrue(audit["variant_review_required"])
        self.assertTrue(any(r["column"]=="CylinderID" for r in audit["variant_changes"]))
        self.assertTrue(any(r["role"]=="List_UpgradeEngineRestrictorPlate" for r in audit["stock_role_changes"]))

    def test_torque_sampling_domain_change_is_visible(self):
        name="FER_12_333SP_98"
        a,z=c.extract_stock(self.src,name),c.extract_stock(self.dst,name)
        audit=b.diagnostic_audit(a,z,{})
        self.assertTrue(audit["torque_domain"]["sampling_domains_differ"])
        self.assertEqual(audit["torque_domain"]["source_count"],151)
        self.assertEqual(audit["torque_domain"]["reference_count"],123)

    def test_chart_and_part_metadata_are_not_counted_as_physics(self):
        self.assertEqual(c.category("Data_Engine","EngineGraphingMaxPower"),"stored_performance_metadata")
        self.assertEqual(c.category("List_Wheels","PartManufacturerID"),"part_metadata")
        self.assertEqual(c.category("Data_Engine","EngineMass-kg"),"physics")

    def test_failures_are_kept_in_denominator_and_reported(self):
        summary=b.aggregate([{"media_name":"broken","modes":{"baseline":{"failure":"broken edge"}}}])
        self.assertEqual(summary["attempted_cars"],1)
        self.assertEqual(summary["modes"]["baseline"]["completed"],0)
        self.assertEqual(len(summary["failures"]),1)


if __name__=="__main__":
    unittest.main()
