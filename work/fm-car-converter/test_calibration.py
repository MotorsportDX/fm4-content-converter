"""Data-leakage, abstention, validation-gate and held-out calibration tests."""
import copy
from contextlib import closing
import sqlite3
import tempfile
from pathlib import Path
import unittest

import converter as c
import calibration as k


@unittest.skipUnless(c.FM3_DEFAULT.exists() and c.FM4_DEFAULT.exists(),"Local FM3/FM4 source databases unavailable")
class CalibrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source=c.connect(c.FM3_DEFAULT)
        cls.target=c.connect(c.FM4_DEFAULT)
        cls.data=k.collect(cls.source,cls.target)
        cls.frozen=k.fit_rules(cls.data)
        cls.model=copy.deepcopy(cls.frozen)
        cls.evaluation=k.validate_rules(cls.data,cls.model)
        cls.graph=c.extract_stock(cls.source,c.MEDIA)
        cls.result=c.convert(cls.source,cls.target,cls.graph)
        cls.reference=c.extract_stock(cls.target,c.MEDIA)

    @classmethod
    def tearDownClass(cls):
        cls.source.close()
        cls.target.close()

    def test_toyota_and_shared_engine_excluded_and_splits_grouped(self):
        self.assertNotIn(247,{p["source"]["id"] for p in self.data["pairs"]})
        self.assertNotIn(1,{p["source"]["engine_id"] for p in self.data["pairs"]})
        self.assertFalse(set(self.model["training_engine_ids"]) & set(self.model["validation_engine_ids"]))
        self.assertEqual(len(self.data["pairs"]),309)

    def test_validation_targets_do_not_train_parameters(self):
        changed=copy.deepcopy(self.data)
        for pair in changed["pairs"]:
            if pair["split"]=="validation":
                for role,col in k.fields36():
                    pair["target"]["nodes"][role][col]=777.125
        self.assertEqual(k.fit_rules(changed),self.frozen)

    def test_validation_does_not_rewrite_frozen_parameters_or_thresholds(self):
        self.assertEqual(self.model["policy"],self.frozen["policy"])
        self.assertEqual(self.model["tier_mappings"],self.frozen["tier_mappings"])
        self.assertEqual(self.model["target_tiers"],self.frozen["target_tiers"])
        for before,after in zip(self.frozen["strong_rules"],self.model["strong_rules"]):
            self.assertEqual(before,{name:after[name] for name in before})

    def test_target_toyota_physics_cannot_affect_rules(self):
        with closing(sqlite3.connect(":memory:")) as changed:
            changed.row_factory=sqlite3.Row
            self.target.backup(changed)
            changed.execute("UPDATE Data_Car SET SteerMaxAngle=999, SteerMaxAngVelTurning=888 WHERE Id=247")
            changed.execute("UPDATE List_UpgradeCarBodyWeight SET CMHeight=777 WHERE CarBodyId=247000")
            changed.execute("UPDATE List_SpringDamperPhysics SET DefSpringRate=666 WHERE Ordinal=247")
            changed.execute("UPDATE Data_Engine SET GasTankSize=555 WHERE EngineID=1")
            self.assertEqual(k.collect(self.source,changed),self.data)

    def test_rejected_profile_is_not_applied_in_estimated_mode(self):
        self.assertFalse(self.model["estimated_profile_accepted"])
        row={"nodes":{r:n["row"] for r,n in self.graph["nodes"].items()}}
        updates,notes=k.propose(row,self.model,"estimated")
        self.assertFalse(any(u["rule"]=="suspension_tier_profile" for u in updates))
        self.assertTrue(any(n["status"]=="estimated_profile_failed_validation_gate" for n in notes))

    def test_unknown_steering_source_value_abstains(self):
        row={"nodes":{r:copy.deepcopy(n["row"]) for r,n in self.graph["nodes"].items()}}
        row["nodes"]["car"]["SteerMaxAngle"]=77
        updates,notes=k.propose(row,self.model)
        self.assertFalse(any(u["column"]=="SteerMaxAngle" for u in updates))
        self.assertTrue(any(n.get("status")=="abstain_unseen_source_value" for n in notes))

    def test_ambiguous_spring_tier_abstains_even_in_experiment(self):
        row={"nodes":{r:copy.deepcopy(n["row"]) for r,n in self.graph["nodes"].items()}}
        row["nodes"]["spring.front"]["DefSpringRate"]=10
        row["nodes"]["spring.rear"]["DefSpringRate"]=10
        updates,notes=k.propose(row,self.model,"experimental")
        self.assertFalse(any(u["rule"]=="suspension_tier_profile" for u in updates))
        self.assertTrue(any(n.get("status")=="abstain_ambiguous_or_unsupported_spring_tier" for n in notes))

    def test_unresolved_properties_are_not_filled_from_target(self):
        result=copy.deepcopy(self.result)
        k.apply_to_result(result,self.graph,self.model,"experimental")
        for role,col in [
            ("List_UpgradeCarBodyWeight","CMHeight"),("engine","GasTankSize"),
            ("List_UpgradeTireCompound","TireCompoundID"),
            *[("List_UpgradeCarBodyChassisStiffness",s+d+"FrictionScale") for s in ("Front","Rear") for d in ("Lat","Long")]
        ]:
            self.assertEqual(result["candidate"]["nodes"][role]["row"][col],self.result["candidate"]["nodes"][role]["row"][col])
        self.assertIn("EXPERIMENT_ONLY_validation_gate_failed",{n["status"] for n in result["calibration"]["notes"]})

    def test_heldout_conservative_and_experimental_comparisons(self):
        counts=[]
        for mode in ("conservative","experimental"):
            result=copy.deepcopy(self.result)
            k.apply_to_result(result,self.graph,self.model,mode)
            with tempfile.TemporaryDirectory() as temp:
                path=Path(temp)/"candidate.slt"
                c.write_patch(path,self.target,result["candidate"])
                valid=c.validate(result["candidate"],self.target,path)
                self.assertTrue(valid["passed"],valid["issues"])
            comparison=c.compare(result["candidate"],self.reference,self.target)
            counts.append(comparison["differences_by_category"]["physics"])
            # No new changes outside the studied columns.
            changes={(x["role"],x["column"]) for x in result["calibration"]["changes"]}
            self.assertFalse(changes-set(k.fields36()))
        self.assertEqual(counts,[31,7])

    def test_fixed_tune_ranges_follow_new_defaults(self):
        result=copy.deepcopy(self.result)
        k.apply_to_result(result,self.graph,self.model,"experimental")
        for role in ("spring.front","spring.rear","antiroll.front","antiroll.rear"):
            fields=("SwaybarStiffness",) if role.startswith("antiroll") else ("SpringRate","DampenBumpRate","DampenReboundRate")
            for field in fields:
                row=result["candidate"]["nodes"][role]["row"]
                self.assertEqual(row["Min"+field],row["Def"+field])
                self.assertEqual(row["Max"+field],row["Def"+field])


if __name__=="__main__":
    unittest.main(verbosity=2)
