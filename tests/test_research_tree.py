"""Tree contracts and real scheduler subprocesses; no simulated investment claims."""
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
import tempfile
from unittest.mock import patch

import batch
import research_tree as T
from quantlib import workspace as W


class ResearchTreeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = self.base / 'study'
        self.tree = self.base / 'tree'
        self.protocol = self.base / 'protocol.json'
        W.write(self.protocol, {'schema_version': 1, 'mode': 'factor',
            'data': {'path': 'input.csv', 'format': 'csv'},
            'splits': {'train': ['2020-01-01', '2020-03-31'], 'valid': ['2020-04-01', '2020-04-30'],
                       'discovery': ['2020-05-01', '2020-05-31'], 'final': ['2020-06-01', '2020-06-30']},
            'budget': {'max_trials': 8, 'max_repairs': 2, 'timeout_seconds': 60}})
        W.initialize(self.root, self.protocol)
        (self.root / 'factor.py').write_text('def compute(frame, params):\n    return frame[["close"]]\n')
        self.spec = {'schema_version': 1, 'workspace': str(self.root),
                     'objective': 'Test volume increment', 'evaluation_rule': 'Paired discovery evidence, no final feedback',
                     'max_nodes': 6, 'max_debug_depth': 2,
                     'execution': {'memory_budget_mb': 128, 'worker_memory_mb': 32, 'timeout_seconds': 30}}
        self.state = T.initialize(self.tree, self.spec)

    def proposal(self, name='a', parent=None, action='draft', window=5):
        path = self.root / (name + '-input.json')
        W.write(path, {'id': name, 'kind': 'factor', 'hypothesis': 'Hypothesis ' + name,
                      'factor_file': 'factor.py', 'factor_params': {'window': window}, 'max_lookback': 21})
        return {'id': name, 'parent': parent, 'action': action, 'question': 'Is there increment?',
                'change': 'Window ' + str(window), 'expected_evidence': 'Matched-date comparison',
                'decision_rule': 'Follow fixed study criteria', 'candidate': str(path)}

    def propose(self, **kwargs):
        return T.propose(self.tree, self.state, self.proposal(**kwargs))

    def runner(self, failing=None):
        # Keep batch.run real; replace only computational native worker and its receipt.
        self.enterContext(patch.object(batch, 'bind_inputs', lambda plan: {'runtime': {
            str(p.relative_to(W.SKILL)): W.digest(p) for p in sorted((W.SKILL / 'scripts').rglob('*.py'))}}))
        self.enterContext(patch.object(batch, 'receipt', lambda task: {'fixture': task['command']}))
        def command(plan, task):
            metrics = self.root / 'runs/discovery' / W.read(task['candidate'])['id'] / 'result.json' if task.get('candidate') else self.root / 'fixture.json'
            code = ('import sys,json,pathlib; assert sys.stdin.readline().strip()=="GO"; '
                    f'p=pathlib.Path({str(metrics)!r}); p.parent.mkdir(parents=True,exist_ok=True); '
                    'p.write_text(json.dumps({"fixture_only":True})); '
                    f'print(json.dumps({{"ok":{task["id"] != failing!r}}})); sys.exit({int(task["id"] == failing)})')
            return [sys.executable, '-c', code]
        self.enterContext(patch.object(batch, 'command_for', command))

    def review(self, name='a', decision='expand', outcome='supported'):
        return {'decision': decision, 'outcome': outcome, 'reason': 'Fixture test of evidence binding only',
                'evidence': [str(self.root / 'runs/discovery' / name / 'result.json')],
                'next_step': 'Test another controlled variation'}

    def test_native_snapshot_and_semantic_metadata_dedup(self):
        first = self.propose()
        duplicate = self.proposal(name='renamed')
        (self.root / 'same.py').write_bytes((self.root / 'factor.py').read_bytes())
        c = W.read(duplicate['candidate']); c['factor_file'] = 'same.py'; W.write(duplicate['candidate'], c)
        with self.assertRaisesRegex(ValueError, 'Duplicate computation'):
            T.propose(self.tree, self.state, duplicate)
        self.assertFalse((self.root / 'candidates/renamed').exists())
        (self.root / 'factor.py').write_text('changed original source')
        T.verify_input(self.state, first)
        self.assertEqual(W.read(first['candidate'])['factor_file'], 'candidates/a/factor.py')

    def test_parent_review_and_branch_pruning(self):
        self.propose()
        with self.assertRaisesRegex(ValueError, 'reviewed'):
            self.propose(name='b', parent='a', action='improve', window=10)
        self.runner()
        T.run_node(self.tree, self.state, 'a')
        T.decide(self.tree, self.state, 'a', self.review())
        self.propose(name='b', parent='a', action='ablate', window=10)
        T.decide(self.tree, self.state, 'a', self.review(decision='prune', outcome='inconclusive'))
        with self.assertRaisesRegex(ValueError, 'Branch blocked'):
            T.run_node(self.tree, self.state, 'b')
        status = T.status(self.tree)
        self.assertTrue(status['nodes'][1]['blocked_by_branch'])
        self.assertEqual(len(self.state['nodes']['a']['reviews']), 2)

    def test_resume_skips_finished_tasks_and_retains_attempts(self):
        self.propose()
        self.runner()
        self.assertEqual(T.run_node(self.tree, self.state, 'a')['exit_code'], 0)
        with self.assertRaisesRegex(ValueError, '--resume'):
            T.run_node(self.tree, self.state, 'a')
        # Simulate outer process death after batch finished, before tree was reconciled.
        self.state['nodes']['a']['execution_status'] = 'running'
        T.save(self.tree, self.state, 'fixture_crash')
        recovered = T.load(self.tree)
        self.assertEqual(T.run_node(self.tree, recovered, 'a', resume=True)['exit_code'], 0)
        native = W.read(self.tree / 'executions/a/state.json')
        self.assertTrue(all(len(task['attempts']) == 1 for task in native['tasks'].values()))

    def test_failed_execution_is_not_refutation_and_debug_depth_bounded(self):
        self.propose()
        self.runner(failing='evaluate')
        self.assertEqual(T.run_node(self.tree, self.state, 'a')['exit_code'], 1)
        with self.assertRaisesRegex(ValueError, 'scientific outcomes'):
            T.decide(self.tree, self.state, 'a', self.review(decision='prune', outcome='refuted'))
        self.propose(name='b', parent='a', action='debug', window=6)
        self.state['nodes']['b']['execution_status'] = 'failed'
        self.propose(name='c', parent='b', action='debug', window=7)
        self.state['nodes']['c']['execution_status'] = 'failed'
        with self.assertRaisesRegex(ValueError, 'Debug depth'):
            self.propose(name='d', parent='c', action='debug', window=8)
        self.assertEqual(self.state['nodes']['c']['debug_depth'], 2)

    def test_budget_pause_and_no_second_owner(self):
        self.state['max_nodes'] = 1
        self.propose()
        with self.assertRaisesRegex(ValueError, 'budget exhausted'):
            self.propose(name='b', window=10)
        self.state['status'] = 'paused'
        with self.assertRaisesRegex(ValueError, 'paused'):
            self.propose(name='c', window=11)
        with self.assertRaisesRegex(ValueError, 'another tree'):
            T.initialize(self.base / 'another-tree', self.spec)

    def test_input_runtime_and_protocol_mutations_fail_closed(self):
        node = self.propose()
        W.write(node['candidate'], {'id': 'changed'})
        with self.assertRaisesRegex(ValueError, 'input changed'):
            T.verify_input(self.state, node)
        with patch.object(T, 'runtime_hash', return_value='changed'):
            with self.assertRaisesRegex(ValueError, 'runtime changed'):
                T.load(self.tree)
        protocol = W.read(self.root / 'protocol.json'); protocol['seed'] = 123
        W.write(self.root / 'protocol.json', protocol)
        with self.assertRaisesRegex(ValueError, 'protocol changed'):
            T.load(self.tree)

    def test_final_evidence_and_tampered_metrics_rejected(self):
        self.propose(); self.runner(); T.run_node(self.tree, self.state, 'a')
        final = self.root / 'runs/final/a/result.json'; W.write(final, {})
        review = self.review(); review['evidence'] = [str(final)]
        with self.assertRaisesRegex(ValueError, 'discovery/check/batch'):
            T.decide(self.tree, self.state, 'a', review)
        W.write(self.state['nodes']['a']['metrics'], {'tampered': True})
        with self.assertRaisesRegex(ValueError, 'evidence changed'):
            T.decide(self.tree, self.state, 'a', self.review())

    def test_sealed_study_and_path_escape_rejected(self):
        p = self.proposal(); p['candidate'] = str(self.base / 'escape.json')
        with self.assertRaisesRegex(ValueError, 'inside'):
            T.propose(self.tree, self.state, p)
        W.write(self.root / 'freeze.json', {})
        with self.assertRaisesRegex(ValueError, 'closed'):
            T.load(self.tree)
        self.assertEqual(T.status(self.tree)['remaining_nodes'], 6)

    def test_cli_lock_and_pause_resume_reopen(self):
        self.propose()
        def cli(*args):
            result = subprocess.run([sys.executable, str(W.SKILL / 'scripts/research_tree.py'),
                '--tree', str(self.tree), *args], capture_output=True, text=True)
            return result.returncode, json.loads(result.stdout)
        with T.FileLock(str(self.tree / '.tree.lock'), timeout=0):
            self.assertEqual(cli('pause', '--reason', 'test lock')[0], 1)
            self.assertEqual(cli('status')[0], 0)
        self.assertEqual(cli('pause', '--reason', 'user pause')[0], 0)
        self.assertEqual(cli('resume', '--reason', 'user continue')[0], 0)
        self.state['nodes']['a']['decision'] = 'freeze'
        T.save(self.tree, self.state, 'fixture_freeze')
        self.assertEqual(cli('reopen', '--node', 'a', '--reason', 'new evidence')[0], 0)
        self.assertEqual(T.load(self.tree)['nodes']['a']['decision'], 'pending')

    def test_plan_tampering_and_interrupted_review_rejected(self):
        self.propose(); self.runner(); T.run_node(self.tree, self.state, 'a')
        path = self.tree / 'plans/a.json'
        plan = W.read(path); plan['timeout_seconds'] += 10; W.write(path, plan)
        with self.assertRaisesRegex(ValueError, 'plan changed'):
            T.run_node(self.tree, self.state, 'a', resume=True)
        self.state['nodes']['a']['execution_status'] = 'interrupted'
        with self.assertRaisesRegex(ValueError, 'Reconcile'):
            T.decide(self.tree, self.state, 'a', self.review())


if __name__ == '__main__':
    unittest.main()
