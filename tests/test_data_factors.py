import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from quantlib import data, factors


def prices(n=100):
    dates = pd.bdate_range('2020-01-01', periods=n)
    rows = []
    for i, date in enumerate(dates):
        for j, symbol in enumerate(['A', 'B']):
            price = 100 + i * .2 + j * 10 + np.sin(i / 4)
            rows.append([date, symbol, price, price + 2, price - 2, price + .1, 10000 + i])
    return pd.DataFrame(rows, columns=['datetime', 'instrument', 'open', 'high', 'low', 'close', 'volume'])


class DataFactorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.frame = prices()
        self.frame.to_csv(self.root / 'prices.csv', index=False)
        days = sorted(self.frame.datetime.unique())
        self.config = {'data': {'path': 'prices.csv', 'format': 'csv', 'volume_unit': 'shares', 'price_basis': 'adjusted'},
                       'splits': {'train': [str(days[0]), str(days[49])], 'valid': [str(days[50]), str(days[64])],
                                  'discovery': [str(days[65]), str(days[84])], 'final': [str(days[85]), str(days[99])]}}
        (self.root / 'protocol.json').write_text(json.dumps(self.config))

    def tearDown(self):
        self.temp.cleanup()

    def test_provider_and_snapshot_integrity(self):
        manifest = data.prepare(self.root, self.config)
        self.assertEqual(manifest['rows'], 200)
        self.assertEqual(manifest['benchmark'], 'QRBENCH')
        self.assertNotIn('QRBENCH', (self.root / 'data/provider/instruments/all.txt').read_text())
        values = np.fromfile(self.root / 'data/provider/features/a/close.day.bin', dtype='<f4')
        self.assertEqual(values[0], 0)
        np.testing.assert_allclose(values[1:], self.frame.loc[self.frame.instrument == 'A', 'close'], rtol=1e-6)
        self.assertTrue(data.verify(self.root)['snapshot_verified'])
        with (self.root / 'data/provider/features/a/close.day.bin').open('ab') as stream:
            stream.write(b'x')
        with self.assertRaisesRegex(ValueError, 'provider changed'):
            data.verify(self.root)

    def test_invalid_bars_rejected(self):
        broken = self.frame.copy()
        broken.loc[0, 'high'] = 1
        with self.assertRaisesRegex(ValueError, 'OHLC'):
            data.normalize(broken)
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            data.normalize(pd.concat([self.frame, self.frame.iloc[:1]]))

    def test_membership_does_not_erase_warmup(self):
        pd.DataFrame([{'instrument': 'A', 'start': '2020-03-01', 'end': '2020-04-30'}]).to_csv(self.root / 'universe.csv', index=False)
        self.config['data']['universe'] = 'universe.csv'
        result = data.prepare(self.root, self.config)
        self.assertEqual(result['rows'], 200)
        self.assertLess(result['eligible_rows'], 100)
        self.assertFalse(pd.read_parquet(self.root / 'data/eligibility.parquet').iloc[0].eligible)

    def test_calendar_gap_keeps_missing_session(self):
        calendar = sorted(self.frame.datetime.unique())
        missing = calendar[40]
        self.frame.loc[self.frame.datetime != missing].to_csv(self.root / 'prices.csv', index=False)
        (self.root / 'calendar.txt').write_text('\n'.join(pd.Timestamp(x).strftime('%Y-%m-%d') for x in calendar))
        self.config['data']['calendar'] = 'calendar.txt'
        manifest = data.prepare(self.root, self.config)
        self.assertEqual(manifest['calendar_gap_rows'], 2)
        bars = data.load_bars(self.root)
        self.assertTrue(bars.loc[pd.Timestamp(missing)].isna().all().all())

    def test_qlib_membership_preserves_prior_history(self):
        import copy
        data.prepare(self.root, self.config)
        provider = self.root / 'data/provider'
        text = (provider / 'instruments/all.txt').read_text()
        (provider / 'instruments/all.txt').write_text(text.replace('A\t2020-01-01', 'A\t2020-03-01'))
        target = self.root / 'imported'
        target.mkdir()
        config = copy.deepcopy(self.config)
        config['data'] = {'path': str(provider), 'format': 'qlib', 'instruments': 'all'}
        manifest = data.prepare(target, config)
        bars = data.load_bars(target)
        eligibility = pd.read_parquet(target / 'data/eligibility.parquet')
        self.assertIn((pd.Timestamp('2020-01-01'), 'A'), bars.index)
        self.assertFalse(eligibility.loc[(pd.Timestamp('2020-01-01'), 'A'), 'eligible'])
        self.assertEqual(manifest['rows'], 200)

    def candidate(self, code, lookback=6):
        (self.root / 'factor.py').write_text(code)
        return {'id': 'test', 'features': ['return_5'], 'factor_file': 'factor.py', 'max_lookback': lookback}

    def test_generated_factor_matches_formula_and_stops_at_discovery(self):
        bars = data.normalize(self.frame)
        candidate = self.candidate("def compute(frame, params):\n    return frame.groupby(level='instrument').close.transform(lambda x: x.pct_change(5, fill_method=None)).rename('generated')\n")
        observed, checks = factors.compute(self.root, candidate, bars)
        np.testing.assert_allclose(observed.return_5, observed.generated, equal_nan=True)
        self.assertLess(len(observed), len(bars))
        self.assertTrue(checks['future_perturbation'])
        self.assertEqual(checks['declared_lookback_verified'], 6)

    def test_cross_sectional_factor_with_unequal_lifetimes(self):
        frame = self.frame.loc[~((self.frame.instrument == 'A') & (self.frame.datetime >= sorted(self.frame.datetime.unique())[70]))]
        bars = data.normalize(frame)
        candidate = self.candidate("def compute(frame, params):\n    return frame.groupby(level='datetime').close.rank(pct=True).rename('rank')\n", lookback=1)
        observed, checks = factors.compute(self.root, candidate, bars)
        self.assertTrue(checks['future_perturbation'])
        self.assertTrue(observed['rank'].between(0, 1).all())

    def test_future_leak_is_rejected(self):
        bars = data.normalize(self.frame)
        candidate = self.candidate("def compute(frame, params):\n    return frame.groupby(level='instrument').close.transform(lambda x: x.shift(-1)).rename('leak')\n")
        with self.assertRaisesRegex(ValueError, 'Future perturbation'):
            factors.compute(self.root, candidate, bars)

    def test_output_row_filter_is_rejected(self):
        bars = data.normalize(self.frame)
        candidate = self.candidate("def compute(frame, params):\n    return frame.close.iloc[1:].rename('filtered')\n")
        with self.assertRaisesRegex(ValueError, 'preserve every input row'):
            factors.compute(self.root, candidate, bars)

    def test_lookback_must_cover_dependency(self):
        bars = data.normalize(self.frame)
        candidate = self.candidate("def compute(frame, params):\n    return frame.groupby(level='instrument').close.transform(lambda x: x.rolling(8, min_periods=1).mean()).rename('mean')\n", lookback=6)
        with self.assertRaisesRegex(ValueError, 'max_lookback'):
            factors.compute(self.root, candidate, bars)


if __name__ == '__main__':
    unittest.main()
