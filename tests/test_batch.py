"""Scheduler contracts and real child-process scheduling, without model training."""
import json
import os
from pathlib import Path
import sys
import time
import subprocess

import unittest
import tempfile
from unittest.mock import patch
import batch


def studies(tmp_path):
    roots = []
    for name in ('a', 'b'):
        root = tmp_path / name
        root.mkdir()
        (root / 'study.json').write_text('{}')
        (root / 'prepared.json').write_text('{}')
        (root / 'candidate.json').write_text(json.dumps({'id': name}))
        (root / 'candidates' / name).mkdir(parents=True)
        (root / 'candidates' / name / 'candidate.json').write_text('{}')
        roots.append(root)
    return roots


def plan_for(studies):
    tasks = []
    for r in studies:
        tasks += [{'id': r.name + '-check', 'command': 'check', 'workspace': str(r), 'candidate': str(r / 'candidate.json')},
                  {'id': r.name + '-eval', 'command': 'evaluate', 'workspace': str(r), 'candidate': str(r / 'candidate.json'), 'depends_on': [r.name + '-check']}]
    return {'schema_version': 1, 'global_candidate_budget': 2, 'max_workers': 2, 'worker_threads': 1,
            'cpu_budget': 2, 'memory_budget_mb': 100, 'worker_memory_mb': 10, 'tasks': tasks}


def load(tmp_path, plan):
    path = tmp_path / 'plan.json'; path.write_text(json.dumps(plan))
    return batch.load_plan(path)


def test_allowlist(tmp_path, studies):
    for bad in ('shell', 'freeze', 'finalize', 'report'):
        p = plan_for(studies); p['tasks'][0]['command'] = bad
        with unittest.TestCase().assertRaisesRegex(ValueError, 'Only prepare'):
            load(tmp_path, p)


def test_dependency_and_budget(tmp_path, studies):
    p = plan_for(studies); p['global_candidate_budget'] = 1
    with unittest.TestCase().assertRaisesRegex(ValueError, 'Global candidate budget'):
        load(tmp_path, p)
    p['global_candidate_budget'] = 2; p['tasks'][1]['depends_on'] = []
    with unittest.TestCase().assertRaisesRegex(ValueError, 'check dependency'):
        load(tmp_path, p)
    p = plan_for(studies); p['tasks'][0]['depends_on'] = ['a-eval']
    with unittest.TestCase().assertRaisesRegex(ValueError, 'cycle'):
        load(tmp_path, p)


def test_frozen_and_sealed_rejected(tmp_path, studies):
    root = studies[0]
    for marker in ('freeze.json', 'supplementary/final-artifact-manifest.json'):
        path = root / marker; path.parent.mkdir(exist_ok=True); path.write_text('{}')
        with unittest.TestCase().assertRaisesRegex(ValueError, 'unfrozen'):
            load(tmp_path, plan_for(studies))
        path.unlink()


def test_resources_and_unknown_fields(tmp_path, studies):
    p = plan_for(studies); p['cpu_budget'] = 1
    with unittest.TestCase().assertRaisesRegex(ValueError, 'CPU budget'): load(tmp_path, p)
    p = plan_for(studies); p['worker_memory_mb'] = 101
    with unittest.TestCase().assertRaisesRegex(ValueError, 'memory budget'): load(tmp_path, p)
    p = plan_for(studies); p['tasks'][0]['shell'] = 'echo nope'
    with unittest.TestCase().assertRaisesRegex(ValueError, 'Unknown task'): load(tmp_path, p)


def isolated_runner(monkeypatch, failing=None):
    monkeypatch.setattr(batch, 'bind_inputs', lambda plan: {'runtime': {str(p.relative_to(batch.W.SKILL)): batch.W.digest(p) for p in sorted((batch.W.SKILL / 'scripts').rglob('*.py'))}})
    monkeypatch.setattr(batch, 'receipt', lambda task: {'id': task['id']})
    def command(plan, task):
        failure = task['id'] == failing
        return [sys.executable, '-c',
                "import sys,time,json; assert sys.stdin.readline().strip()=='GO'; time.sleep(.3); "
                + "print(json.dumps({'ok': %s})); sys.exit(%d)" % (not failure, int(failure))]
    monkeypatch.setattr(batch, 'command_for', command)


def test_real_process_overlap_serialization_resume_and_fail_closed(tmp_path, studies, monkeypatch):
    isolated_runner(monkeypatch)
    plan = load(tmp_path, plan_for(studies)); out = tmp_path / 'out'
    assert batch.run(plan, out) == 0
    state = json.loads((out / 'state.json').read_text())
    a = state['tasks']['a-check']['attempts'][0]; b = state['tasks']['b-check']['attempts'][0]
    assert max(a['started_at'], b['started_at']) < min(a['ended_at'], b['ended_at'])
    for name in ('a', 'b'):
        assert state['tasks'][name+'-check']['attempts'][0]['ended_at'] <= state['tasks'][name+'-eval']['attempts'][0]['started_at']
    assert batch.run(plan, out, resume=True) == 0
    assert all(len(x['attempts']) == 1 for x in json.loads((out/'state.json').read_text())['tasks'].values())
    monkeypatch.setattr(batch, 'receipt', lambda task: {'changed': True})
    with unittest.TestCase().assertRaisesRegex(ValueError, 'artifact changed'): batch.run(plan, out, resume=True)


def test_failure_blocks_and_attempt_budget(tmp_path, studies, monkeypatch):
    isolated_runner(monkeypatch, failing='a-check')
    plan = load(tmp_path, plan_for(studies)); plan['max_attempts'] = 1
    out = tmp_path / 'out'
    assert batch.run(plan, out) == 1
    state = json.loads((out/'state.json').read_text())
    assert state['tasks']['a-check']['status'] == 'failed'
    assert state['tasks']['a-eval']['status'] == 'blocked'
    assert not state['tasks']['a-eval']['attempts']
    assert batch.run(plan, out, resume=True) == 1
    assert len(json.loads((out/'state.json').read_text())['tasks']['a-check']['attempts']) == 1


def test_resume_binding_and_live_group_refusal(tmp_path, studies, monkeypatch):
    isolated_runner(monkeypatch)
    plan = load(tmp_path, plan_for(studies)); out = tmp_path / 'out'
    assert batch.run(plan, out) == 0
    plan['max_attempts'] += 1
    with unittest.TestCase().assertRaisesRegex(ValueError, 'Batch plan'): batch.run(plan, out, resume=True)
    plan['max_attempts'] -= 1
    state = json.loads((out/'state.json').read_text())
    state['tasks']['a-check']['status'] = 'running'
    live = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'], start_new_session=True)
    try:
        state['tasks']['a-check']['attempts'][-1]['pid'] = live.pid
        (out/'state.json').write_text(json.dumps(state))
        with unittest.TestCase().assertRaisesRegex(ValueError, 'still present'): batch.run(plan, out, resume=True)
    finally:
        batch.stop_process(live)


def test_prepare_is_exclusive(tmp_path, studies, monkeypatch):
    isolated_runner(monkeypatch)
    p = plan_for(studies)
    for r in studies:
        p['tasks'].insert(0, {'id': r.name+'-prepare', 'command': 'prepare', 'workspace': str(r)})
        next(x for x in p['tasks'] if x['id'] == r.name+'-check')['depends_on'] = [r.name+'-prepare']
    plan = load(tmp_path, p); out = tmp_path / 'out'
    assert batch.run(plan, out) == 0
    tasks = json.loads((out/'state.json').read_text())['tasks']
    for key, value in tasks.items():
        if not key.endswith('-prepare'): continue
        a = value['attempts'][0]
        for other, info in tasks.items():
            if key == other: continue
            b = info['attempts'][0]
            assert max(a['started_at'], b['started_at']) >= min(a['ended_at'], b['ended_at'])


def test_resolved_defaults_are_stable_on_resume(tmp_path, studies, monkeypatch):
    p = plan_for(studies); p.pop('memory_budget_mb'); p.pop('worker_memory_mb')
    monkeypatch.setattr(batch, 'memory_limit_mb', lambda: 4096)
    first = load(tmp_path, p)
    monkeypatch.setattr(batch, 'memory_limit_mb', lambda: 8192)
    path = tmp_path / 'plan.json'
    again = batch.load_plan(path, resolved_defaults=first)
    assert again == first


def test_spawn_failure_is_a_preserved_attempt(tmp_path, studies, monkeypatch):
    isolated_runner(monkeypatch)
    plan = load(tmp_path, plan_for(studies)); out = tmp_path / 'out'
    def failed_spawn(*args, **kwargs): raise OSError('synthetic process limit')
    monkeypatch.setattr(batch.subprocess, 'Popen', failed_spawn)
    assert batch.run(plan, out) == 1
    state = json.loads((out / 'state.json').read_text())
    assert state['tasks']['a-check']['status'] == 'failed'
    attempt = state['tasks']['a-check']['attempts'][0]
    assert 'synthetic process limit' in attempt['error']
    assert attempt['ended_at']


def test_exception_cleans_active_child_and_persists_interrupted(tmp_path, studies, monkeypatch):
    isolated_runner(monkeypatch)
    normal = batch.command_for
    def broken(plan, task):
        if task['id'] == 'b-check': raise ValueError('deliberate coordinator error')
        return normal(plan, task)
    monkeypatch.setattr(batch, 'command_for', broken)
    plan = load(tmp_path, plan_for(studies)); out = tmp_path / 'out'
    with unittest.TestCase().assertRaisesRegex(ValueError, 'deliberate coordinator'):
        batch.run(plan, out)
    state = json.loads((out / 'state.json').read_text())
    assert state['status'] == 'failed'
    assert state['tasks']['a-check']['status'] == 'interrupted'
    attempt = state['tasks']['a-check']['attempts'][-1]
    assert attempt['ended_at'] and attempt['returncode'] is not None
    assert state['error']['message'] == 'deliberate coordinator error'
    monkeypatch.setattr(batch, 'command_for', normal)
    assert batch.run(plan, out, resume=True) == 0


class MonkeyPatch:
    def __init__(self): self.patches = []
    def setattr(self, target, name, value):
        p = patch.object(target, name, value); p.start(); self.patches.append(p)
    def close(self):
        for p in reversed(self.patches): p.stop()


class BatchTests(unittest.TestCase):
    pass


def adapt(function):
    def method(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); roots = studies(root); monkey = MonkeyPatch()
            try:
                if 'monkeypatch' in function.__code__.co_varnames:
                    function(root, roots, monkey)
                else:
                    function(root, roots)
            finally: monkey.close()
    return method


for name, function in list(globals().items()):
    if name.startswith('test_') and callable(function):
        setattr(BatchTests, name, adapt(function))
        del globals()[name]

if __name__ == '__main__':
    unittest.main()
