"""Test coordinate compensation, policy isolation, and original instruction oracle."""
import copy
from pathlib import Path
import random
import unittest

from fm4_converter.fm3 import converter as c
from fm4_converter.fm3 import code_semantics as s


@unittest.skipUnless(c.FM3_DEFAULT.exists() and c.FM4_DEFAULT.exists(),"Local source DBs required")
class CodeSemanticsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src,cls.dst=c.connect(c.FM3_DEFAULT),c.connect(c.FM4_DEFAULT)
        cls.source=c.extract_stock(cls.src,c.MEDIA)

    @classmethod
    def tearDownClass(cls):
        cls.src.close()
        cls.dst.close()

    def test_toyota_preserves_traced_center_without_native_answer(self):
        result=c.convert(self.src,self.dst,self.source)
        baseline=s.effective_center(result["candidate"],"fm4")
        self.assertAlmostEqual(baseline["main_mass_block_center_y"],.1008)
        s.apply(result,self.source)
        self.assertAlmostEqual(s.row(result["candidate"],s.WEIGHT)["CMHeight"],.4070)
        self.assertAlmostEqual(s.effective_center(result["candidate"],"fm4")["main_mass_block_center_y"],.2539)
        self.assertNotEqual(s.row(result["candidate"],s.WEIGHT)["CMHeight"],.4421)
        with self.assertRaises(c.MappingError):
            s.apply(result,self.source)

    def test_unequal_axle_heights_use_source_maximum_reference(self):
        source=copy.deepcopy(self.source)
        s.row(source,"spring.front")["MaxRideHeight"]=.2
        s.row(source,"spring.rear")["MaxRideHeight"]=.4
        result=c.convert(self.src,self.dst,source)
        s.apply(result,source)
        car=s.row(result["candidate"],"car")
        self.assertEqual((car["FrontStockRideHeight"],car["RearStockRideHeight"]),(.2,.4))
        self.assertAlmostEqual(s.row(result["candidate"],s.WEIGHT)["CMHeight"],.5519)
        self.assertAlmostEqual(s.effective_center(result["candidate"],"fm4")["main_mass_block_center_y"],.2539)

    def test_unsupported_inputs_fail_before_mutation(self):
        for role,col,value in (
            (s.WEIGHT,"CMBackFront",1.2),
            ("List_UpgradeEngine","WeightDistDiff",.01),
            ("body",s.ORIGIN,.4),
            (s.WEIGHT,"CMHeight",.45),
            ("spring.front","DefSpringRate",123.0),
            (s.WEIGHT,"Mass",123.0),
        ):
            result=c.convert(self.src,self.dst,self.source)
            s.row(result["candidate"],role)[col]=value
            saved=copy.deepcopy(result)
            with self.assertRaises(c.MappingError):
                s.apply(result,self.source)
            self.assertEqual(result,saved)

    def test_nonstock_and_missing_mapping_rejected_atomically(self):
        for mutate in ("part","mapping","role","assumptions"):
            result=c.convert(self.src,self.dst,self.source)
            if mutate=="part":
                s.row(result["candidate"],"List_UpgradeEngine")["IsStock"]=0
            elif mutate=="mapping":
                result["mapping"]=[m for m in result["mapping"] if not (
                    m["role"]==s.WEIGHT and m["target_column"]=="CMHeight")]
            elif mutate=="role":
                del result["candidate"]["nodes"]["List_UpgradeEngine"]
            else:
                del result["assumptions"]
            saved=copy.deepcopy(result)
            with self.assertRaises(c.MappingError):
                s.apply(result,self.source)
            self.assertEqual(result,saved)

    @unittest.skipUnless(Path("work/fm4/loaded-image.bin").exists(),"Private executable image required")
    def test_original_instruction_slice_matches_compensated_inputs(self):
        image=Path("work/fm4/loaded-image.bin").read_bytes()
        rng=random.Random(30304)
        for _ in range(250):
            height,dist,front,rear=rng.uniform(.05,.9),rng.uniform(.05,.95),rng.uniform(.03,.5),rng.uniform(.03,.5)
            encoded=height+rear+(front-rear)*dist
            actual=s.run_cg_instruction_slice(image,0x82000000,height=encoded,
                                              distribution=dist,front=front,rear=rear)
            self.assertAlmostEqual(actual["config_cmheight"],height,delta=2e-7)
            self.assertEqual(len(actual["instruction_addresses"]),11)
        damaged=bytearray(image)
        damaged[0x8A77A0:0x8A77A4]=b"\0\0\0\0"
        with self.assertRaises(c.MappingError):
            s.run_cg_instruction_slice(damaged,0x82000000,height=.4,distribution=.5,front=.1,rear=.1)


if __name__=="__main__":
    unittest.main()
