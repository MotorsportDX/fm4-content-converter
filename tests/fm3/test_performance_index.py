"""ClassID follows FM4's own class bounds for whatever PerformanceIndex is written."""
from contextlib import closing
import sqlite3
import unittest

from fm4_converter.fm3 import converter as c
from fm4_converter.fm3 import performance_index as pi


def bounds_db():
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE CarClasses(Id INTEGER, MaxPerformanceIndex REAL)")
    db.executemany("INSERT INTO CarClasses VALUES (?,?)",[(0,0.157),(1,0.2224),(2,0.282493),(3,0.347),(10,1.0)])
    return db


MODEL = {"kind":"linear","coef":[0.1687949,0.7721120],"knots":[],"domain":[0.0,0.99445],"accepted":True}


class ApplyTests(unittest.TestCase):
    def test_cobalt_v6_mismatch_resolved_both_ways(self):
        with closing(bounds_db()) as db:
            car = {"PerformanceIndex":0.164646,"ClassID":2}
            self.assertEqual(pi.apply(car,db)["status"],"source_raw_pi_kept")
            self.assertEqual(car,{"PerformanceIndex":0.164646,"ClassID":1})  # E, as FM4 shows PI 209
            car = {"PerformanceIndex":0.164646,"ClassID":2}
            record = pi.apply(car,db,MODEL)
            self.assertEqual(record["status"],"mapped_linear")
            self.assertAlmostEqual(car["PerformanceIndex"],0.29592,places=6)
            self.assertEqual(car["ClassID"],3)

    def test_rejected_or_out_of_domain_model_keeps_raw_pi(self):
        with closing(bounds_db()) as db:
            car = {"PerformanceIndex":0.2,"ClassID":0}
            self.assertEqual(pi.apply(car,db,dict(MODEL,accepted=False))["status"],"model_not_accepted")
            self.assertEqual(car,{"PerformanceIndex":0.2,"ClassID":1})
            car = {"PerformanceIndex":0.2,"ClassID":1}
            self.assertEqual(pi.apply(car,db,dict(MODEL,domain=[0.3,0.9]))["status"],"outside_training_domain")

    def test_hinge_prediction_and_monotonicity(self):
        model = {"coef":[0.0,1.0,-0.5],"knots":[0.5]}
        self.assertAlmostEqual(pi.predict(model,0.8),0.65)
        self.assertTrue(pi.monotone(model))
        self.assertFalse(pi.monotone({"coef":[0.0,1.0,-1.5],"knots":[0.5]}))

    def test_out_of_bounds_rejected(self):
        with closing(bounds_db()) as db, self.assertRaises(c.MappingError):
            pi.apply({"PerformanceIndex":1.2,"ClassID":10},db)


@unittest.skipUnless(c.FM4_DEFAULT.exists() and c.FM3_DEFAULT.exists(),"local game databases unavailable")
class NativeInvariantTests(unittest.TestCase):
    def test_every_native_car_matches_its_class_bound(self):
        for path in (c.FM4_DEFAULT,c.FM3_DEFAULT):
            with closing(c.connect(path)) as db:
                bounds = pi.classes(db)
                for media,cls,value in db.execute("SELECT MediaName,ClassID,PerformanceIndex FROM Data_Car"):
                    self.assertEqual(pi.class_for(value,bounds),cls,(path.name,media))


if __name__=="__main__":
    unittest.main()
