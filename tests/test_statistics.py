"""ICIR contract: real per-date correlations, undefined cases and raw factor scope."""
import json
import unittest

import numpy as np
import pandas as pd
from quantlib.statistics import signal_metrics, factor_signal_metrics


def panel(scores):
    index = pd.MultiIndex.from_product([pd.date_range('2024-01-01', periods=len(scores)),
                                        ['a', 'b', 'c', 'd']], names=['datetime', 'instrument'])
    return pd.DataFrame({'prediction': np.asarray(scores).reshape(-1),
                         'label': np.tile([1., 2., 3., 4.], len(scores))}, index=index)


class SignalMetricsTests(unittest.TestCase):
    def test_distinct_pearson_and_rank_sample_ratios(self):
        frame = panel([[1, 2, 3, 30], [4, 3, 2, 1], [1, 3, 2, 4]])
        result, daily = signal_metrics(frame, frequency='daily', label_horizon_sessions=5)
        for key, ratio in [('ic', 'icir'), ('rank_ic', 'rank_icir')]:
            expected = daily[key].mean() / daily[key].std(ddof=1)
            self.assertAlmostEqual(result[ratio], expected)
            self.assertEqual(result[key + '_n'], 3)
            self.assertAlmostEqual(result[key + '_std'], daily[key].std(ddof=1))
        self.assertNotEqual(result['icir'], result['rank_icir'])
        self.assertFalse(result['icir_annualized'])
        self.assertEqual(result['ic_std_ddof'], 1)
        self.assertEqual(result['label_horizon_sessions'], 5)
        self.assertEqual(result['ic_frequency'], 'daily')
        json.dumps(result, allow_nan=False)

    def test_empty_singleton_constant_and_negative(self):
        for frame, reason in [(panel([]), 'insufficient_dates'),
                              (panel([[1, 2, 3, 4]]), 'insufficient_dates'),
                              (panel([[1, 2, 3, 4]] * 3), 'zero_variance')]:
            result, _ = signal_metrics(frame)
            for ratio in ['icir', 'rank_icir']:
                self.assertIsNone(result[ratio])
                self.assertEqual(result[ratio + '_undefined_reason'], reason)
            json.dumps(result, allow_nan=False)
        result, _ = signal_metrics(panel([[4, 3, 2, 1], [4, 2, 3, 1]]))
        self.assertLess(result['icir'], 0)

    def test_finite_pairs_coverage_ties_and_constant_cross_sections(self):
        frame = panel([[1, 1, 2, 3], [1, 2, 3, np.inf], [np.nan, np.inf, 2, 3], [2, 2, 2, 2]])
        result, daily = signal_metrics(frame)
        self.assertEqual(daily.n.tolist(), [4, 3])
        self.assertEqual(result['ic_n'], 2)
        self.assertEqual(result['ic_excluded_dates'], 2)
        self.assertAlmostEqual(daily.iloc[0].rank_ic, frame.iloc[:4].prediction.corr(frame.iloc[:4].label, method='spearman'))
        self.assertEqual(result['ic_frequency'], 'unspecified')

    def test_duplicate_observations_rejected(self):
        frame = panel([[1, 2, 3, 4]])
        with self.assertRaises(ValueError):
            signal_metrics(pd.concat([frame, frame]))

    def test_raw_factors_are_separate_and_use_purged_labels(self):
        predictions = panel([[1, 2, 3, 4], [4, 2, 3, 1], [1, 3, 2, 4]])
        features = pd.DataFrame({'positive': predictions.prediction,
                                 'inverse': -predictions.prediction,
                                 'missing': np.nan}, index=predictions.index)
        predictions.loc[predictions.index[-4:], 'label'] = np.nan
        summaries, daily = factor_signal_metrics(features, predictions, frequency='daily', label_horizon_sessions=20)
        self.assertEqual(set(summaries), set(features))
        self.assertAlmostEqual(summaries['positive']['icir'], -summaries['inverse']['icir'])
        self.assertEqual(summaries['positive']['ic_n'], 2)
        self.assertEqual(summaries['positive']['label_horizon_sessions'], 20)
        self.assertIsNone(summaries['missing']['icir'])
        self.assertEqual(set(daily.factor), {'positive', 'inverse'})
        json.dumps(summaries, allow_nan=False)


if __name__ == '__main__':
    unittest.main()
