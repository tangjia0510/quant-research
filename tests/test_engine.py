"""Behavioral checks for temporal boundaries, preprocessing and actual Qlib runs."""
import importlib.util
import json
from pathlib import Path
import pickle
import sys
import tempfile
import unittest

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from quantlib.engine import labels_for, split_masks, scale_train_only, evaluate, folds_for, _fit_fold
from quantlib.models import check_model, fit_predict
from quantlib.statistics import portfolio_metrics, paired_increment
from quantlib import data, factors


class EngineTests(unittest.TestCase):
    @staticmethod
    def early_stopping_fixture():
        rng = np.random.default_rng(318)
        train = rng.normal(size=(240, 3)).astype(np.float32)
        valid = rng.normal(size=(96, 3)).astype(np.float32)
        evaluation = rng.normal(size=(32, 3)).astype(np.float32)
        target = lambda x: 2 * x[:, 0] + .5 * x[:, 1] + (x[:, 2] > 0)
        # Deliberately conflicting validation targets make later boosting rounds
        # worse, so an adapter accidentally predicting all trees is detectable.
        return train, target(train), valid, -target(valid), evaluation

    def test_lightgbm_best_iteration_and_saved_reload(self):
        import lightgbm as lgb
        inputs = self.early_stopping_fixture()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            prediction, details = fit_predict(*inputs, {
                'kind': 'lightgbm', 'params': {'n_estimators': 80, 'patience': 4,
                    'learning_rate': .15, 'num_leaves': 7, 'min_child_samples': 8}
            }, root, root)
            saved = pickle.loads((root / 'model.pkl').read_bytes())
            losses = saved.evals_result_['valid_0']['l2']
            best_iteration = int(np.argmin(losses)) + 1
            self.assertEqual(details['best_iteration'], best_iteration)
            self.assertGreater(len(losses), best_iteration)
            self.assertLess(len(losses), 80)
            self.assertTrue(details['reload_predictions_match'])
            self.assertGreater(float(np.std(prediction)), .01)
            np.testing.assert_allclose(prediction, saved.predict(inputs[-1], num_iteration=best_iteration))
            # Also load the fitted trees through LightGBM's native text format.
            saved.booster_.save_model(str(root / 'trees.txt'))
            native = lgb.Booster(model_file=str(root / 'trees.txt'))
            np.testing.assert_allclose(prediction, native.predict(inputs[-1]), rtol=1e-7, atol=1e-9)

    def test_xgboost_best_iteration_and_native_saved_reload(self):
        import xgboost as xgb
        inputs = self.early_stopping_fixture()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            prediction, details = fit_predict(*inputs, {
                'kind': 'xgboost', 'params': {'num_boost_round': 80,
                    'early_stopping_rounds': 4, 'learning_rate': .15, 'max_depth': 2}
            }, root, root)
            native = xgb.Booster()
            native.load_model(root / 'model.ubj')
            saved = pickle.loads((root / 'model.pkl').read_bytes())
            best = native.best_iteration
            self.assertEqual(details['best_iteration'], best)
            self.assertTrue(details['reload_predictions_match'])
            self.assertGreater(native.num_boosted_rounds(), best + 1)
            self.assertLess(native.num_boosted_rounds(), 80)
            matrix = xgb.DMatrix(inputs[-1])
            np.testing.assert_allclose(prediction, native.predict(matrix, iteration_range=(0, best + 1)), rtol=1e-7, atol=1e-9)
            np.testing.assert_allclose(prediction, saved.predict(matrix, iteration_range=(0, best + 1)), rtol=1e-7, atol=1e-9)
            self.assertGreater(float(np.max(np.abs(prediction - native.predict(matrix)))), .01)
            valid_matrix = xgb.DMatrix(inputs[2])
            losses = [float(np.sqrt(np.mean((native.predict(valid_matrix, iteration_range=(0, end)) - inputs[3]) ** 2)))
                      for end in range(1, native.num_boosted_rounds() + 1)]
            self.assertEqual(best, int(np.argmin(losses)))
            self.assertAlmostEqual(native.best_score, losses[best], places=5)

    def test_fold_cannot_relabel_discovery_dates_as_final(self):
        config = {'splits': {'discovery': ['2020-01-01', '2020-03-31'],
                             'final': ['2020-04-01', '2020-06-30']},
                  'folds': [{'final': ['2020-02-01', '2020-03-31']}]}
        with self.assertRaisesRegex(ValueError, 'inside the protocol phase'):
            folds_for(config, 'final')
        config['folds'] = [{'final': ['2020-04-01', '2020-07-01']}]
        with self.assertRaises(ValueError):
            folds_for(config, 'final')
        config['folds'] = [{'final': ['2020-04-01', '2020-05-01']}]
        self.assertEqual(len(folds_for(config, 'final')), 1)

    def test_labels_use_global_calendar_not_next_observed_row(self):
        dates = pd.bdate_range('2020-01-01', periods=12)
        index = pd.MultiIndex.from_product([dates, ['A', 'B']], names=['datetime', 'instrument'])
        bars = pd.DataFrame({'open': np.arange(24) + 10.}, index=index)
        bars.loc[(dates[1], 'A'), 'open'] = np.nan
        labels, ends, _ = labels_for(bars, {'price': 'open', 'entry_lag': 1, 'horizon': 2})
        self.assertTrue(np.isnan(labels.loc[(dates[0], 'A')]))
        self.assertEqual(ends.loc[(dates[0], 'A')], dates[3])
        self.assertAlmostEqual(labels.loc[(dates[0], 'B')], bars.loc[(dates[3], 'B'), 'open'] / bars.loc[(dates[1], 'B'), 'open'] - 1)

    def test_purge_uses_label_end(self):
        dates = pd.bdate_range('2020-01-01', periods=30)
        index = pd.MultiIndex.from_product([dates, ['A']], names=['datetime', 'instrument'])
        bars = pd.DataFrame({'open': np.arange(30) + 10.}, index=index)
        _, ends, _ = labels_for(bars, {'price': 'open', 'entry_lag': 1, 'horizon': 5})
        splits = {'train': [str(dates[0].date()), str(dates[9].date())],
                  'valid': [str(dates[10].date()), str(dates[19].date())],
                  'discovery': [str(dates[20].date()), str(dates[-1].date())]}
        masks = split_masks(index, ends, splits, 'discovery')
        self.assertEqual(int(masks['train'].sum()), 4)
        self.assertTrue((ends[masks['train']] < dates[10]).all())
        self.assertTrue((ends[masks['valid']] < dates[20]).all())

    def test_future_data_cannot_change_scaler(self):
        frame = pd.DataFrame({'a': [1., 2., 3., 4., 100., 200.]})
        mask = frame.index < 4
        _, median, scale = scale_train_only(frame, mask)
        frame.loc[~mask] = -1e12
        _, median2, scale2 = scale_train_only(frame, mask)
        pd.testing.assert_series_equal(median, median2)
        pd.testing.assert_series_equal(scale, scale2)

    def test_fixed_split_keeps_validation_scaler_and_model_across_phases(self):
        module_spec = importlib.util.spec_from_file_location('fixed_demo', ROOT / 'assets/make_demo.py')
        demo = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(demo)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            demo.create_demo(root / 'input', sessions=400, instruments=4)
            config = json.loads((root / 'input/protocol.json').read_text())
            config['model'] = {'kind': 'lightgbm', 'params': {
                'n_estimators': 20, 'patience': 4, 'num_leaves': 7}}
            workspace = root / 'study'
            workspace.mkdir()
            (workspace / 'protocol.json').write_text(json.dumps(config))
            data.prepare(workspace, config)
            candidate = {'features': ['return_5', 'volatility_20']}
            full_bars = data.load_bars(workspace)
            checks = {}
            for phase in ('discovery', 'final'):
                bars = full_bars.loc[full_bars.index.get_level_values('datetime') <= pd.Timestamp(config['splits'][phase][1])]
                features, _ = factors.compute(workspace, candidate, bars, stage=phase)
                _, checks[phase] = _fit_fold(workspace, config, candidate, bars, features,
                                            phase, config['splits'], workspace / phase)
            for name in ('train', 'valid'):
                self.assertEqual(checks['discovery']['rows'][name], checks['final']['rows'][name])
            self.assertEqual(checks['final']['validation_label_boundary'], config['splits']['discovery'][0])
            pd.testing.assert_frame_equal(pd.read_csv(workspace / 'discovery/scaler.csv'),
                                          pd.read_csv(workspace / 'final/scaler.csv'))
            models = [pickle.loads((workspace / phase / 'model.pkl').read_bytes()) for phase in ('discovery', 'final')]
            self.assertEqual(models[0].best_iteration_, models[1].best_iteration_)
            self.assertEqual(models[0].booster_.model_to_string(), models[1].booster_.model_to_string())

    def test_drawdown_includes_initial_capital(self):
        report = pd.DataFrame({'return': [-.1, 0.], 'cost': [0., 0.], 'bench': [0., 0.]})
        self.assertAlmostEqual(portfolio_metrics(report)['max_drawdown'], -.1)

    def test_custom_model_rejects_invalid_shape(self):
        try:
            import torch
        except ImportError:
            self.skipTest('optional torch is not installed')
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'wrong.py').write_text('import torch\ndef build_model(num_features):\n    return torch.nn.Linear(num_features, 2)\n')
            with self.assertRaises(ValueError):
                check_model({'kind': 'custom', 'file': 'wrong.py'}, root, 3)

    def test_torch_candidate_lightgbm_baseline_real_simulator(self):
        try:
            import torch
        except ImportError:
            self.skipTest('optional torch is not installed')
        module_spec = importlib.util.spec_from_file_location('mixed_demo', ROOT / 'assets/make_demo.py')
        demo = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(demo)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            demo.create_demo(root / 'input', sessions=400, instruments=4)
            config = json.loads((root / 'input/protocol.json').read_text())
            config['robustness'] = {'enabled': False}
            config['model'] = {'kind': 'lightgbm', 'params': {
                'n_estimators': 12, 'patience': 3, 'num_leaves': 7}}
            workspace = root / 'study'
            workspace.mkdir()
            (workspace / 'protocol.json').write_text(json.dumps(config))
            (workspace / 'model.py').write_text(
                'import torch\ndef build_model(num_features):\n'
                '    return torch.nn.Linear(num_features, 1)\n')
            data.prepare(workspace, config)
            candidate = {'id': 'mixed', 'kind': 'model',
                         'features': ['return_5', 'volatility_20'],
                         'model': {'kind': 'custom', 'file': 'model.py',
                                   'params': {'epochs': 2, 'patience': 1}},
                         'hypothesis': 'Native runtime compatibility regression'}
            result = evaluate(workspace, config, candidate, 'discovery', workspace / 'result')
            self.assertEqual(result['simulator'], 'qlib.SimulatorExecutor')
            self.assertEqual(result['folds'][0]['model']['kind'], 'custom')
            self.assertTrue(result['folds'][0]['model']['reload_predictions_match'])
            self.assertTrue((workspace / 'result/fold-0/model.pt').is_file())
            baseline = pickle.loads((workspace / 'result/baseline/fold-0/model.pkl').read_bytes())
            self.assertEqual(type(baseline).__name__, 'LGBMRegressor')
            self.assertGreater(baseline.best_iteration_, 0)
            self.assertGreater(result['portfolio']['days'], 20)
            self.assertTrue(np.isfinite(result['increment']['annualized_net_return_difference']))

    def test_same_candidate_baseline_zero_increment_real_simulator(self):
        module_spec = importlib.util.spec_from_file_location('make_demo', ROOT / 'assets/make_demo.py')
        demo = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(demo)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            demo.create_demo(root / 'input', sessions=400, instruments=4)
            config = json.loads((root / 'input/protocol.json').read_text())
            config['robustness'] = {'enabled': False}
            config['preprocessing'] = {'clip': 3, 'label_transform': 'cross_sectional_rank'}
            workspace = root / 'study'
            workspace.mkdir()
            (workspace / 'protocol.json').write_text(json.dumps(config))
            data.prepare(workspace, config)
            candidate = {'id': 'same', 'kind': 'factor', 'features': ['return_5', 'volatility_20'], 'hypothesis': 'baseline parity'}
            result = evaluate(workspace, config, candidate, 'discovery', workspace / 'result')
            self.assertEqual(result['simulator'], 'qlib.SimulatorExecutor')
            self.assertEqual(result['increment']['mean_rank_ic_increment'], 0.)
            self.assertTrue(result['folds'][0]['model']['reload_predictions_match'])
            self.assertGreater(result['portfolio']['days'], 20)
            self.assertGreater(result['portfolio']['mean_daily_cost'], 0)
            orders = pd.read_csv(workspace / 'result/portfolio-orders.csv')
            self.assertTrue((pd.to_datetime(orders.signal_date) < pd.to_datetime(orders.trade_date)).all())
            portfolio = pd.read_csv(workspace / 'result/portfolio.csv', index_col=0)
            self.assertEqual(orders.trade_date.iloc[0], portfolio.index[0])
            self.assertEqual(orders.signal_date.iloc[0], config['splits']['discovery'][0])
            self.assertGreater(portfolio['value'].iloc[0], 0)
            for name in ('equal-weight.csv', 'baseline/portfolio.csv'):
                self.assertGreater(pd.read_csv(workspace / 'result' / name)['value'].iloc[0], 0)
            self.assertEqual(result['prediction_rows'], 320)
            # Independent old-protocol reference: NumPy median/IQR + actual Qlib
            # CSRankNorm + a fresh sklearn Ridge, without engine preprocessing.
            from sklearn.linear_model import Ridge
            from qlib.data.dataset.processor import CSRankNorm
            from quantlib import factors
            bars = data.load_bars(workspace)
            bars = bars.loc[bars.index.get_level_values('datetime') <= pd.Timestamp(config['splits']['discovery'][1])]
            features, _ = factors.compute(workspace, candidate, bars, stage='discovery')
            target, ends, _ = labels_for(bars, config['label'])
            masks = split_masks(features.index, ends, config['splits'], 'discovery')
            train_mask = masks['train'] & target.notna()
            raw = features.to_numpy()
            training = raw[train_mask]
            median = np.nanmedian(training, axis=0)
            q25, q75 = np.nanpercentile(training, [25, 75], axis=0)
            iqr = np.where((q75 - q25) == 0, 1., q75 - q25)
            independent = np.nan_to_num(np.clip((raw - median) / iqr, -3, 3), nan=0).astype(np.float32)
            norm_input = pd.concat({'label': target.to_frame()}, axis=1)
            ranked = CSRankNorm(fields_group='label')(norm_input)['label']['label']
            reference = Ridge(alpha=1.).fit(independent[train_mask], ranked.loc[train_mask])
            saved = pd.read_parquet(workspace / 'result/predictions.parquet')
            # Different pandas/NumPy memory layouts lead to float32 BLAS rounding.
            np.testing.assert_allclose(reference.predict(independent[masks['test']]), saved.prediction, atol=1e-6, rtol=1e-5)
            saved_scaler = pd.read_csv(workspace / 'result/fold-0/scaler.csv', index_col=0)
            np.testing.assert_allclose(saved_scaler['median'], median, atol=1e-10)
            np.testing.assert_allclose(saved_scaler['iqr'], iqr, atol=1e-10)


if __name__ == '__main__':
    unittest.main()
