"""End-to-end report contract using real synthetic Qlib computation, never investment evidence."""
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
from smoke_modes import execute


class SignalReportTests(unittest.TestCase):
    def test_raw_factor_and_combined_prediction_ratios_reach_both_reports(self):
        spec = importlib.util.spec_from_file_location('icir_demo', ROOT / 'assets/make_demo.py')
        demo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(demo)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            inputs = demo.create_demo(root / 'input', sessions=400, instruments=4)
            workspace = root / 'study'
            execute(sys.executable, 'init', '--workspace', workspace, '--protocol', inputs['protocol'], '--mode', 'factor')
            execute(sys.executable, 'prepare', '--workspace', workspace)
            shutil.copy2(ROOT / 'assets/example_factor.py', workspace / 'factor.py')
            candidate = {'id': 'icir_report', 'kind': 'factor', 'hypothesis': 'Synthetic reporting test only',
                         'features': ['return_5', 'volatility_20'], 'factor_file': 'factor.py',
                         'factor_params': {'return_window': 5, 'volatility_window': 20}, 'max_lookback': 21}
            path = workspace / 'candidate-input.json'
            path.write_text(json.dumps(candidate))
            execute(sys.executable, 'check', '--workspace', workspace, '--candidate', path)
            execute(sys.executable, 'evaluate', '--workspace', workspace, '--candidate', path)
            execute(sys.executable, 'report', '--workspace', workspace)
            run = workspace / 'runs/discovery/icir_report'
            result = json.loads((run / 'result.json').read_text())
            self.assertGreater(len(result['factor_signal']), 2)
            for name in ['report.md', 'report.html']:
                text = (workspace / name).read_text()
                for field in ['icir', 'rank_icir', 'ic_std_ddof', 'label_horizon_sessions', 'baseline.signal']:
                    self.assertIn(field, text)
                for factor in result['factor_signal']:
                    self.assertIn('factor_signal.' + factor, text)
            receipt = json.loads((run / 'run.json').read_text())
            self.assertTrue(any(x.endswith('factor-daily-ic.csv') for x in receipt['artifacts']))


if __name__ == '__main__':
    unittest.main()
