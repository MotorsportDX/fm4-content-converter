"""FM3 -> FM4 scale and convention rules: gating, domain and ownership."""
import math
import unittest

from fm4_converter.fm3 import value_scales as vs


RULES = {"version":1,"rules":[
    {"table":"Data_Car","column":"MakeIcon","category":"catalog_or_integration","accepted":True,
     "kind":"constant","value":"BOING"},
    {"table":"Data_Car","column":"SpeedRating","category":"stored_performance_metadata","accepted":True,
     "kind":"linear","coef":[-2.0,1.5],"domain":[2.0,9.0]},
    {"table":"Data_Car","column":"AccelerationRating","category":"stored_performance_metadata",
     "accepted":True,"kind":"loglinear","coef":[0.9,0.6],"domain":[1.0,10.0]},
    {"table":"List_Wheels","column":"DisplayName","category":"part_metadata","accepted":True,
     "kind":"lookup","values":{'""':"NULL"}},
    {"table":"List_UpgradeCarBodyChassisStiffness","column":"FrontLatFrictionScale","category":"physics",
     "accepted":True,"kind":"linear","coef":[0.42,0.58],"domain":[0.9,1.1]},
]}


def result(speed=5.0):
    return {"candidate":{"nodes":{
        "car":{"table":"Data_Car","row":{"MakeIcon":"GAME:\\x.tga","SpeedRating":speed,"AccelerationRating":4.0}},
        "wheel":{"table":"List_Wheels","row":{"DisplayName":""}},
        "chassis":{"table":"List_UpgradeCarBodyChassisStiffness","row":{"FrontLatFrictionScale":1.05}},
    }},"mapping":[{"role":"car","target_column":"SpeedRating","target_value":speed}]}


class ApplyTests(unittest.TestCase):
    def test_metadata_and_conventions_apply_but_physics_needs_opt_in(self):
        r = result()
        record = vs.apply(r,RULES)
        row = r["candidate"]["nodes"]["car"]["row"]
        self.assertEqual(row["MakeIcon"],"BOING")
        self.assertAlmostEqual(row["SpeedRating"],5.5)
        self.assertEqual(row["AccelerationRating"],round(math.exp(0.9+0.6*math.log(4.0)),6))
        self.assertEqual(r["candidate"]["nodes"]["wheel"]["row"]["DisplayName"],"NULL")
        self.assertEqual(r["candidate"]["nodes"]["chassis"]["row"]["FrontLatFrictionScale"],1.05)
        self.assertEqual(r["mapping"][0]["target_value"],row["SpeedRating"])
        self.assertFalse(record["physics"])
        r = result()
        vs.apply(r,RULES,physics=True)
        self.assertAlmostEqual(r["candidate"]["nodes"]["chassis"]["row"]["FrontLatFrictionScale"],1.029)

    def test_outside_training_domain_abstains(self):
        r = result(speed=9.5)
        record = vs.apply(r,RULES)
        self.assertEqual(r["candidate"]["nodes"]["car"]["row"]["SpeedRating"],9.5)
        self.assertEqual(record["abstained"][0]["reason"],"outside_training_domain")

    def test_unaccepted_rule_is_ignored(self):
        rules = {"rules":[dict(RULES["rules"][0],accepted=False)]}
        r = result()
        vs.apply(r,rules)
        self.assertEqual(r["candidate"]["nodes"]["car"]["row"]["MakeIcon"],"GAME:\\x.tga")

    def test_integer_rules_keep_target_granularity(self):
        rule = {"kind":"linear","coef":[0.0,0.83],"domain":[0,1e9],"integer":True,"step":1000}
        self.assertEqual(vs.predict(rule,15000),12000)
        rule = {"kind":"linear","coef":[0.8245,0.1761],"domain":[0.9,1.1],"grid":0.0025}
        self.assertEqual(vs.predict(rule,1.0),1.0)
        self.assertEqual(vs.predict(rule,1.05),1.01)

    def test_columns_owned_by_other_adapters_are_never_studied(self):
        for table,column in [("Data_Car","PerformanceIndex"),("Data_Car","ClassID"),
                             ("Data_Car","FrontStockRideHeight"),("List_UpgradeCarBodyWeight","CMHeight"),
                             ("List_SpringDamperPhysics","DefSpringRate"),
                             ("List_SpringDamperPhysics","MinDampenReboundRate"),
                             ("List_AntiSwayPhysics","MaxSwaybarStiffness"),("List_TorqueCurve","v12"),
                             ("Data_Car","EngineID")]:
            self.assertTrue(vs.owned(table,column),(table,column))
        for table,column in [("Data_Car","SpeedRating"),("Data_Car","FamilyBodyID"),
                             ("List_UpgradeCarBodyChassisStiffness","FrontLatFrictionScale")]:
            self.assertFalse(vs.owned(table,column),(table,column))


if __name__=="__main__":
    unittest.main()
