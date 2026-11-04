"""FM2 -> FM4 physics: CMHeight and PI models, CV folds, groups and aspiration layouts."""
import unittest

from fm4_converter.fm2 import physics as p


def car(pi, **sim):
    return {'PerformanceIndex': pi, 'Year': 2000, **{f: sim.get(f, 1.0) for f in p.PI_SIM}}


class PerformanceIndexTests(unittest.TestCase):
    def items(self):
        # FM4 PI = 0.1 + 0.8 x below FM2's B/A bound, steeper above it.
        out = []
        for i in range(40):
            x = 0.1 + 0.02 * i
            y = 0.1 + 0.8 * x + 0.5 * max(0.0, x - 0.4596)
            out.append({'car': car(x), 'y': y, 'engine': i, 'split': 'training'})
        return out

    def test_hinge_fits_a_kinked_mapping_and_is_monotone(self):
        model = p.pi_fit(self.items(), 'hinge', ())
        self.assertTrue(p.pi_monotone(model))
        self.assertAlmostEqual(p.pi_predict(model, car(0.3))[0], 0.34, places=4)
        self.assertAlmostEqual(p.pi_predict(model, car(0.7))[0], 0.1 + 0.56 + 0.5 * (0.7 - 0.4596), places=4)

    def test_only_knots_inside_the_training_range_are_used(self):
        model = p.pi_fit(self.items()[:10], 'hinge', ())
        self.assertEqual(model['knots'], [0.265])

    def test_no_prediction_outside_the_training_domain(self):
        model = p.pi_fit(self.items(), 'hinge', ('Year',))
        self.assertEqual(p.pi_predict(model, {**car(0.3), 'Year': 2007}), (None, 'Year'))
        self.assertEqual(p.pi_predict(model, car(0.95))[1], 'PerformanceIndex')

    def test_a_falling_segment_is_not_monotone(self):
        self.assertFalse(p.pi_monotone({'coef': [0.0, 0.5, -0.7], 'knots': [0.4]}))
        self.assertTrue(p.pi_monotone({'coef': [0.0, 0.5, -0.4], 'knots': [0.4]}))


class CMHeightTests(unittest.TestCase):
    def test_outside_the_domain_falls_back_to_the_coordinate_formula(self):
        model = {'kind': 'linear', 'features': ['cm_height', 'stock_height'], 'coef': [0.0, 2.0, 2.0],
                 'domain': {'cm_height': [0.0, 1.0], 'stock_height': [0.0, 0.5]}}
        inside = {'cm_height': 0.2, 'stock_height': 0.1}
        self.assertEqual(p.cm_predict(model, inside), (0.6, None))
        self.assertEqual(p.cm_predict(model, {'cm_height': 0.2, 'stock_height': 0.9}), (1.1, 'stock_height'))

    def test_stock_height_is_weighted_by_cm_back_front(self):
        nodes = {'car': {'FrontStockRideHeight': 0.2, 'RearStockRideHeight': 0.1},
                 p.WEIGHT: {'CMHeight': 0.3, 'CMBackFront': 0.25, 'BlockDimY': 0.6}}
        features = p.cm_features(nodes, (-0.1, 1.2))
        self.assertAlmostEqual(features['stock_height'], 0.125)
        self.assertAlmostEqual(features['bbox_height'], 1.3)


class FoldTests(unittest.TestCase):
    def test_folds_partition_training_by_engine(self):
        items = [{'engine': e % 13, 'i': i} for i, e in enumerate(range(60))]
        folds = p.engine_folds(items)
        self.assertEqual(len(folds), 5)
        held = [i['i'] for _, out in folds for i in out]
        self.assertEqual(sorted(held), list(range(60)))
        for fit, out in folds:
            self.assertFalse({i['engine'] for i in fit} & {i['engine'] for i in out})
        self.assertEqual(p.engine_folds(items), folds)


class GroupTests(unittest.TestCase):
    def test_coupled_columns_share_a_group(self):
        self.assertEqual(p.group('car', 'CurbWeight'), p.group(p.WEIGHT, 'Mass'))
        self.assertEqual(p.group('spring.front', 'DefSpringRate'), p.group('spring.rear', 'MaxSpringRate'))
        self.assertEqual(p.group('car', 'GameTorqueScale'), p.group('torque.full', 'TorqueScale'))
        self.assertEqual(p.group('car', 'PerformanceIndex'), 'car.PerformanceIndex')

    def test_differential_conventions_are_per_drive_type(self):
        conventions = {'2:CenterAccel': {'value': 0.0}, 'List_UpgradeEngineIntercooler:Price': {'value': 0}}
        self.assertEqual(p.convention(conventions, 2, 'List_UpgradeDrivetrainDifferential', 'CenterAccel'),
                         {'value': 0.0})
        self.assertIsNone(p.convention(conventions, 1, 'List_UpgradeDrivetrainDifferential', 'CenterAccel'))
        self.assertEqual(p.convention(conventions, 1, 'List_UpgradeEngineIntercooler', 'Price'), {'value': 0})


class AspirationTests(unittest.TestCase):
    def test_every_boosted_layout_has_one_boost_part_and_an_intercooler(self):
        self.assertEqual(p.ASPIRATION_PARTS[1], ())
        for kind, parts in p.ASPIRATION_PARTS.items():
            if kind != 1:
                self.assertEqual(len(parts), 2)
                self.assertIn('List_UpgradeEngineIntercooler', parts)
                self.assertTrue(set(parts) <= set(p.ASPIRATION))
        self.assertNotIn(4, p.ASPIRATION_PARTS)   # no stock quad turbo in FM4
        self.assertNotIn(7, p.ASPIRATION_PARTS)   # no stock turbo + supercharger in FM4


if __name__ == '__main__':
    unittest.main()
