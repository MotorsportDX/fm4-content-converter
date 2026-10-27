"""Behavioral and negative tests, using local read-only databases when present."""
import copy
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest

import converter as m


@unittest.skipUnless(m.FM3_DEFAULT.exists() and m.FM4_DEFAULT.exists(), "Local FM3/FM4 source databases unavailable")
class ConverterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = m.connect(m.FM3_DEFAULT)
        cls.target = m.connect(m.FM4_DEFAULT)
        cls.graph = m.extract_stock(cls.source,m.MEDIA)
        cls.result = m.convert(cls.source,cls.target,cls.graph)
        cls.reference = m.extract_stock(cls.target,m.MEDIA)

    @classmethod
    def tearDownClass(cls):
        cls.source.close()
        cls.target.close()

    def clone(self, db):
        clone = sqlite3.connect(":memory:")
        clone.row_factory = sqlite3.Row
        db.backup(clone)
        return clone

    def test_source_connections_cannot_write(self):
        for db in (self.source,self.target):
            with self.assertRaises(sqlite3.OperationalError):
                db.execute("UPDATE Data_Car SET BaseCost=0 WHERE Id=247")

    def test_stock_selection_keeps_nonzero_level_components(self):
        for table in ("List_UpgradeDrivetrainDifferential","List_UpgradeEngineFuelSystem","List_UpgradeEngineManifold"):
            row = self.graph["nodes"][table]["row"]
            self.assertEqual(row["IsStock"],1)
            self.assertEqual(row["Level"],1)

    def test_roundtrip_schema_and_edges_and_no_global_tire_patch(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/"candidate.slt"
            patch = m.write_patch(path,self.target,self.result["candidate"])
            check = m.validate(self.result["candidate"],self.target,path)
            self.assertTrue(check["passed"],check["issues"])
            self.assertGreater(patch["rows"],40)
            with closing(m.connect(path)) as db:
                tables = set(m.schema(db))
                self.assertFalse(tables & {"List_TireCompound","List_TireFrictionCurve","List_TireFrictionMultiCurve","List_TireAffectCurve"})

    def test_preserves_source_calibration_instead_of_target_answers(self):
        got = self.result["candidate"]["nodes"]
        native = self.reference["nodes"]
        for role,col in [("car","SteerMaxAngle"),("spring.front","DefSpringRate"),
                         ("engine","GasTankSize"),("List_UpgradeCarBodyWeight","CMHeight")]:
            self.assertEqual(got[role]["row"][col],self.graph["nodes"][role]["row"][col])
            self.assertNotEqual(got[role]["row"][col],native[role]["row"][col])
        self.assertEqual(got["List_UpgradeTireCompound"]["row"]["TireCompoundID"],5)
        self.assertEqual(native["List_UpgradeTireCompound"]["row"]["TireCompoundID"],2)

    def test_native_reference_calibration_cannot_leak_into_converter(self):
        # Alter every numeric non-identity value of the held-out native car and
        # its selected components. Global registries remain valid target inputs.
        with closing(self.clone(self.target)) as changed:
            for node in self.reference["nodes"].values():
                cols = [c for c,v in node["row"].items() if isinstance(v,(int,float))
                        and c != node["pk"] and c.lower() not in {"ordinal","carbodyid","engineid","drivetrainid"}]
                if cols:
                    changed.execute("UPDATE "+m.qi(node["table"])+" SET "+",".join(m.qi(c)+"=777.125" for c in cols)+
                                    " WHERE "+m.qi(node["pk"])+"=?",(node["row"][node["pk"]],))
            result = m.convert(self.source,changed,self.graph)
        self.assertEqual(result,self.result)

    def test_conversion_does_not_read_native_target_car_values(self):
        # SQLite authorizer proves Data_Car reads are limited to occupied IDs.
        reads = []
        def authorize(action, table, column, database, trigger):
            if action == sqlite3.SQLITE_READ and table == "Data_Car":
                reads.append(column)
                if column not in ("Id",""):
                    return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK
        with closing(m.connect(m.FM4_DEFAULT)) as guarded:
            guarded.set_authorizer(authorize)
            result = m.convert(self.source,guarded,self.graph)
        self.assertTrue(reads)
        self.assertEqual(result["candidate"],self.result["candidate"])

    def test_torque_preserves_active_samples_and_retains_loss_warning(self):
        old = self.graph["nodes"]["torque.full"]["row"]
        new = self.result["candidate"]["nodes"]["torque.full"]["row"]
        self.assertEqual(new["NumTorqueValues"],86)
        self.assertEqual(new["ZeroThrottleTorqueScale"],self.graph["nodes"]["torque.zero"]["row"]["TorqueScale"])
        for i in range(86):
            self.assertEqual(old[f"v{i}"],new[f"v{i}"])
        self.assertTrue(all(new[f"v{i}"] == 0 for i in range(151,186)))
        self.assertNotIn("torque.zero",self.result["candidate"]["nodes"])
        self.assertTrue(any("SHAPE" in a.get("limitation","") for a in self.result["assumptions"]))

    def test_tire_dependency_closure_uses_target_values(self):
        deps = self.result["native_tire_dependencies"]
        self.assertEqual(len(deps),19)
        for dep in deps:
            native = m.one(m.rows(self.target,dep["table"],m.qi(dep["pk"])+"=?",(dep["id"],)),"native tire")
            self.assertEqual(dep["row"],native)
        curve = next(d for d in deps if d["table"]=="List_TireFrictionMultiCurve")
        old = m.one(m.rows(self.source,curve["table"],m.qi(curve["pk"])+"=?",(curve["id"],)),"old tire")
        self.assertNotEqual(curve["row"]["LoadClamp"],old["LoadClamp"])

    def test_collision_allocator_skips_existing_ids(self):
        result = m.convert(self.source,self.target,self.graph,id_base=247000)
        for item in result["id_map"]:
            primary = m.pk(m.schema(self.target)[item["table"]])
            existing = self.target.execute("SELECT 1 FROM "+m.qi(item["table"])+" WHERE "+m.qi(primary)+"=?",(item["target_id"],)).fetchone()
            self.assertIsNone(existing)
        self.assertNotEqual(result["candidate"]["nodes"]["body"]["row"]["Id"],247000)

    def test_unknown_target_field_fails_closed(self):
        with closing(self.clone(self.target)) as changed:
            changed.execute("ALTER TABLE Data_Car ADD COLUMN UnknownNewPhysicsParameter REAL")
            with self.assertRaisesRegex(m.MappingError,"Unmapped target column"):
                m.convert(self.source,changed,self.graph)

    def test_unknown_removed_source_field_fails_closed(self):
        graph = copy.deepcopy(self.graph)
        graph["nodes"]["engine"]["row"]["UnreviewedFuelSetting"] = 2
        with self.assertRaisesRegex(m.MappingError,"Unreviewed removed source field"):
            m.convert(self.source,self.target,graph)

    def test_missing_dependency_fails_instead_of_guessing(self):
        with closing(self.clone(self.source)) as changed:
            changed.execute("DELETE FROM List_SpringDamperPhysics WHERE SpringDamperPhysicsID=247100")
            with self.assertRaisesRegex(m.MappingError,"spring.rear.*got 0"):
                m.extract_stock(changed,m.MEDIA)

    def test_ambiguous_stock_selection_fails(self):
        with closing(self.clone(self.source)) as changed:
            changed.execute("UPDATE List_UpgradeEngine SET IsStock=1 WHERE Ordinal=247")
            with self.assertRaisesRegex(m.MappingError,"List_UpgradeEngine.*expected exactly one"):
                m.extract_stock(changed,m.MEDIA)

    def test_malformed_curve_fails(self):
        for count in (0,152):
            graph = copy.deepcopy(self.graph)
            graph["nodes"]["torque.full"]["row"]["NumTorqueValues"] = count
            with self.assertRaises(m.MappingError):
                m.convert(self.source,self.target,graph)
        graph = copy.deepcopy(self.graph)
        graph["nodes"]["torque.full"]["row"]["v12"] = float("nan")
        with self.assertRaisesRegex(m.MappingError,"Invalid active torque sample"):
            m.convert(self.source,self.target,graph)

    def test_compare_distinguishes_rounding_registry_ids_and_calibration(self):
        result = m.compare(self.result["candidate"],self.reference,self.target)
        self.assertGreater(result["counts"]["within_numeric_tolerance"],0)
        auto = next(x for x in result["fields"] if x.get("column")=="AutoSteerOverrideID")
        self.assertEqual(auto["status"],"equivalent_registry_payload")
        self.assertTrue(any(x.get("column")=="CMHeight" for x in result["differences"]))
        self.assertFalse(result["runtime_equivalence_claimed"])

    def test_existing_output_and_source_tree_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(m.MappingError,"Choose a new output directory"):
                m.run(m.FM3_DEFAULT,m.FM4_DEFAULT,temp)
            path = Path(temp)/"keep.slt"
            path.write_bytes(b"keep me")
            with self.assertRaisesRegex(m.MappingError,"already exists"):
                m.write_patch(path,self.target,self.result["candidate"])
            self.assertEqual(path.read_bytes(),b"keep me")
        with self.assertRaisesRegex(m.MappingError,"outside both source"):
            m.run(m.FM3_DEFAULT,m.FM4_DEFAULT,m.FM4_DEFAULT.parent/"candidate")


if __name__ == "__main__":
    unittest.main(verbosity=2)
