"""Real worker interruption and bounded generated-model checks; no mocked results."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import quant
from quantlib import workspace as W


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='quant-recovery-')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        spec = importlib.util.spec_from_file_location('quant_recovery_demo', ROOT / 'assets/make_demo.py')
        demo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(demo)
        demo.create_demo(self.base / 'input', sessions=400, instruments=4)
        self.protocol = self.base / 'input/protocol.json'
        self.config = W.read(self.protocol)
        self.config['robustness'] = {'enabled': False}
        self.config['budget'] = {'max_trials': 2, 'max_repairs': 2, 'timeout_seconds': 90}

    def dispatch(self, command, **kwargs):
        return quant.dispatch(argparse.Namespace(command=command, workspace=str(self.study), **kwargs))

    def prepare(self, mode):
        W.write(self.protocol, self.config)
        self.study = self.base / mode
        self.dispatch('init', protocol=str(self.protocol), mode=mode)
        self.dispatch('prepare')

    def test_killed_worker_retries_same_candidate_retains_failed_attempt(self):
        self.prepare('factor')
        (self.study / 'factor.py').write_bytes((ROOT / 'assets/example_factor.py').read_bytes())
        candidate = {'id': 'recovery', 'kind': 'factor', 'hypothesis': 'Engineering recovery test',
                     'factor_file': 'factor.py', 'features': ['return_5', 'volatility_20'], 'max_lookback': 21}
        source = self.study / 'proposal.json'
        W.write(source, candidate)
        original_popen = subprocess.Popen
        processes, timers = [], []

        def start_then_kill(*args, **kwargs):
            process = original_popen(*args, **kwargs)
            command = args[0] if args else kwargs.get('args', [])
            if not any(str(part).endswith('evaluate_worker.py') for part in command):
                return process
            processes.append(process)
            def terminate_owned_worker():
                if process.poll() is None:
                    if os.name == 'nt':
                        process.kill()
                    else:
                        os.killpg(process.pid, signal.SIGKILL)
            timer = threading.Timer(.2, terminate_owned_worker)
            timers.append(timer)
            timer.start()
            return process

        with patch.object(quant.subprocess, 'Popen', side_effect=start_then_kill):
            with self.assertRaisesRegex(RuntimeError, 'Worker failed'):
                self.dispatch('evaluate', candidate=str(source))
        for timer in timers:
            timer.join()
        self.assertEqual(len(processes), 1)
        self.assertNotEqual(processes[0].returncode, 0)
        folder = self.study / 'runs/discovery/recovery'
        failed = W.read(folder / 'run.json')
        self.assertEqual(failed['status'], 'failed')
        self.assertEqual(failed['attempt'], 1)
        self.assertTrue((folder / 'attempt-1/execution.log').exists())
        frozen_candidate = W.verify_candidate(self.study, 'recovery')['candidate_hash']
        retry = self.dispatch('evaluate', candidate=str(source))
        self.assertFalse(retry['cached'])
        completed = W.read(folder / 'run.json')
        self.assertEqual(completed['status'], 'complete')
        self.assertEqual(completed['attempt'], 2)
        self.assertEqual(completed['input_hash'], failed['input_hash'])
        self.assertEqual(W.verify_candidate(self.study, 'recovery')['candidate_hash'], frozen_candidate)
        self.assertTrue((folder / 'attempt-1/execution.log').exists())
        self.assertTrue((folder / 'attempt-2/result.json').exists())
        events = [json.loads(line) for line in (self.study / 'events.jsonl').read_text().splitlines()]
        self.assertIn('evaluation_failed', [e['action'] for e in events])
        cached = self.dispatch('evaluate', candidate=str(source))
        self.assertTrue(cached['cached'])
        self.assertEqual(W.read(folder / 'run.json')['attempt'], 2)

    def test_hanging_custom_model_check_is_bounded(self):
        try:
            import torch
        except ImportError:
            self.skipTest('optional torch required')
        self.config['budget']['timeout_seconds'] = 8
        self.prepare('model')
        (self.study / 'hang.py').write_text(
            'from pathlib import Path\n'
            'def build_model(num_features):\n'
            '    Path(__file__).with_suffix(".entered").write_text("entered")\n'
            '    while True:\n'
            '        pass\n')
        proposal = self.study / 'proposal.json'
        W.write(proposal, {'id': 'hang', 'kind': 'model', 'hypothesis': 'Timeout contract test',
                           'model': {'kind': 'custom', 'file': 'hang.py'}})
        started = time.monotonic()
        with self.assertRaisesRegex(RuntimeError, 'timed out'):
            self.dispatch('check', candidate=str(proposal))
        self.assertLess(time.monotonic() - started, 20)
        self.assertTrue((self.study / 'candidates/hang/model.entered').exists(), 'Must reach the hanging model, not merely time out during imports')
        self.assertFalse((self.study / 'candidates/hang/checks.json').exists())


if __name__ == '__main__':
    unittest.main()
