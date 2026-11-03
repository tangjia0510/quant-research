#!/usr/bin/env python3
"""Real two-study Qlib scheduler smoke; synthetic execution evidence, not alpha evidence."""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import importlib.util
import json
import os
import signal
from pathlib import Path
import shutil
import subprocess
import sys
import time

SKILL = Path(__file__).resolve().parents[1]


def cli(python, script, arguments, log_prefix):
    env = {k: v for k, v in os.environ.items()
           if k not in {'PYTHONPATH', 'PYTHONHOME', 'QUANT_BATCH_START_GATE', 'QUANT_BATCH_PROCESS_GROUP'}}
    env['PYTHONNOUSERSITE'] = '1'
    command = [str(python), str(SKILL / 'scripts' / script), *map(str, arguments)]
    result = subprocess.run(command, capture_output=True, text=True, env=env, timeout=900)
    log_prefix.with_suffix('.stdout.json').write_text(result.stdout)
    log_prefix.with_suffix('.stderr.log').write_text(result.stderr)
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise AssertionError(f'Invalid JSON from {command}: {result.stdout[-1500:]}') from error
    if result.returncode or not value.get('ok'):
        raise AssertionError(f'CLI failed ({result.returncode}): {command}: {value}; {result.stderr[-1500:]}')
    return value


def stamp(value):
    return datetime.fromisoformat(value).timestamp()


def overlap(left, right):
    return max(0., min(left['end'], right['end']) - max(left['start'], right['start']))


def run(output, python):
    output = Path(output).resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError('Use a fresh empty output directory; smoke evidence is never overwritten.')
    output.mkdir(parents=True, exist_ok=True)
    spec = importlib.util.spec_from_file_location('make_demo', SKILL / 'assets/make_demo.py')
    demo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(demo)
    inputs = demo.create_demo(output / 'input', sessions=400, instruments=4)
    protocol_path = Path(inputs['protocol'])
    protocol = json.loads(protocol_path.read_text())
    protocol['robustness'] = {'enabled': False}
    protocol_path.write_text(json.dumps(protocol, indent=2) + '\n')
    tasks = []
    for tag in ('a', 'b'):
        workspace = output / f'study-{tag}'
        cli(python, 'quant.py', ['init', '--workspace', workspace, '--protocol', protocol_path], output / f'init-{tag}')
        (workspace / 'input').mkdir()
        shutil.copy2(SKILL / 'assets/example_factor.py', workspace / 'input/factor.py')
        candidate = {'id': f'factor-{tag}', 'kind': 'factor',
                     'hypothesis': 'Synthetic batch execution parity; not an investment claim.',
                     'features': ['return_5', 'volatility_20'], 'factor_file': 'input/factor.py',
                     'factor_params': {'return_window': 5, 'volatility_window': 20}, 'max_lookback': 21}
        candidate_path = workspace / 'candidate-input.json'
        candidate_path.write_text(json.dumps(candidate, indent=2) + '\n')
        tasks.extend([
            {'id': f'{tag}-prepare', 'command': 'prepare', 'workspace': str(workspace), 'depends_on': []},
            {'id': f'{tag}-check', 'command': 'check', 'workspace': str(workspace),
             'candidate': str(candidate_path), 'depends_on': [f'{tag}-prepare']},
            {'id': f'{tag}-evaluate', 'command': 'evaluate', 'workspace': str(workspace),
             'candidate': str(candidate_path), 'depends_on': [f'{tag}-check']},
        ])
    # Make both prepares ready before compute to expose real cross-study overlap.
    priority = {'prepare': 0, 'check': 1, 'evaluate': 2}
    tasks.sort(key=lambda task: (priority[task['command']], task['id']))
    plan = {'schema_version': 1, 'max_workers': 2, 'worker_threads': 1,
            'global_candidate_budget': 2, 'max_attempts': 2, 'timeout_seconds': 600,
            'cpu_budget': 2, 'memory_budget_mb': 4096, 'worker_memory_mb': 1024,
            'prepare_memory_mb': 4096, 'tasks': tasks}
    plan_path = output / 'plan.json'
    plan_path.write_text(json.dumps(plan, indent=2) + '\n')
    began = time.monotonic()
    cli(python, 'batch.py', ['--plan', plan_path, '--output', output / 'batch'], output / 'first-run')
    elapsed = time.monotonic() - began
    state_path = output / 'batch/state.json'
    state = json.loads(state_path.read_text())
    assert all(entry['status'] == 'success' for entry in state['tasks'].values())
    intervals = []
    for task in tasks:
        entry = state['tasks'][task['id']]
        assert len(entry['attempts']) == 1, entry
        attempt = entry['attempts'][0]
        assert attempt['status'] == 'success' and attempt['returncode'] == 0, attempt
        intervals.append({'id': task['id'], 'command': task['command'], 'workspace': task['workspace'],
                          'start': stamp(attempt['started_at']), 'end': stamp(attempt['ended_at']),
                          'started_at': attempt['started_at'], 'ended_at': attempt['ended_at']})
    parallel = []
    for number, left in enumerate(intervals):
        for right in intervals[number + 1:]:
            seconds = overlap(left, right)
            if left['workspace'] == right['workspace'] or 'prepare' in (left['command'], right['command']):
                assert seconds == 0, (left, right, seconds)
            elif seconds > 0:
                parallel.append({'left': left['id'], 'right': right['id'], 'overlap_seconds': seconds})
    assert parallel, 'No actual independent-study compute overlap observed'
    native_hashes = {}
    native_intervals = []
    for tag in ('a', 'b'):
        native = output / f'study-{tag}/runs/discovery/factor-{tag}/run.json'
        native_hashes[str(native)] = hashlib.sha256(native.read_bytes()).hexdigest()
        run_state = json.loads(native.read_text())
        assert run_state['status'] == 'complete' and run_state['attempt'] == 1
        native_intervals.append({'id': tag, 'start': stamp(run_state['started_at']),
                                 'end': stamp(run_state['completed_at'])})
    attempts_before = {key: value['attempts'] for key, value in state['tasks'].items()}
    cli(python, 'batch.py', ['--plan', plan_path, '--output', output / 'batch', '--resume'], output / 'resume-run')
    resumed = json.loads(state_path.read_text())
    assert {key: value['attempts'] for key, value in resumed['tasks'].items()} == attempts_before
    for name, expected in native_hashes.items():
        assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == expected
    summary = {'synthetic': True, 'purpose': 'Real Qlib execution/concurrency only; no investment evidence.',
               'elapsed_seconds': round(elapsed, 3), 'actual_cross_study_overlaps': parallel,
               'native_evaluate_overlap_seconds': overlap(*native_intervals),
               'same_study_overlap': False, 'prepare_overlap': False,
               'resume_no_new_attempts': True, 'native_run_artifacts_unchanged_on_resume': True,
               'intervals': intervals, 'plan': str(plan_path), 'state': str(state_path)}
    (output / 'smoke-summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    return summary


def group_members(group_id):
    """Read only this known test process group's Linux process identities."""
    members = []
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():
            continue
        try:
            text = (proc / 'stat').read_text()
            fields = text[text.rfind(')') + 2:].split()
            if int(fields[2]) != group_id:
                continue
            members.append({'pid': int(proc.name), 'state': fields[0], 'start_ticks': fields[19],
                            'command': (proc / 'cmdline').read_bytes().replace(b'\x00', b' ').decode(errors='replace')})
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            continue
    return members


def cancellation_smoke(output, python, protocol_path):
    if os.name != 'posix' or not Path('/proc').is_dir():
        return {'skipped': 'Process-group cancellation proof requires Linux /proc.'}
    output = Path(output)
    output.mkdir()
    workspace = output / 'study'
    cli(python, 'quant.py', ['init', '--workspace', workspace, '--protocol', protocol_path], output / 'init')
    cli(python, 'quant.py', ['prepare', '--workspace', workspace], output / 'prepare')
    (workspace / 'input').mkdir()
    (workspace / 'input/factor.py').write_text(
        'import pandas as pd\n'
        'def compute(frame, params):\n'
        "    values = frame['close'].copy()\n"
        '    for _ in range(200000):\n'
        '        values = values + 0.0\n'
        "    return pd.DataFrame({'slow_close': values}, index=frame.index)\n")
    candidate = {'id': 'cancel-factor', 'kind': 'factor',
                 'hypothesis': 'Deliberately slow legal synthetic computation to verify process cleanup.',
                 'features': ['return_5', 'volatility_20'], 'factor_file': 'input/factor.py', 'max_lookback': 1}
    candidate_path = workspace / 'candidate.json'
    candidate_path.write_text(json.dumps(candidate))
    plan = {'schema_version': 1, 'max_workers': 1, 'worker_threads': 1, 'global_candidate_budget': 1,
            'max_attempts': 1, 'timeout_seconds': 120, 'cpu_budget': 1,
            'memory_budget_mb': 4096, 'worker_memory_mb': 1024,
            'tasks': [{'id': 'cancel-check', 'command': 'check', 'workspace': str(workspace),
                       'candidate': str(candidate_path), 'depends_on': []}]}
    plan_path = output / 'plan.json'
    plan_path.write_text(json.dumps(plan, indent=2))
    command = [str(python), str(SKILL / 'scripts/batch.py'), '--plan', str(plan_path), '--output', str(output / 'batch')]
    observed = []
    group_id = None
    with (output / 'cancel.stdout.json').open('w') as stdout, (output / 'cancel.stderr.log').open('w') as stderr:
        process = subprocess.Popen(command, stdout=stdout, stderr=stderr, start_new_session=True)
        try:
            deadline = time.monotonic() + 90
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise AssertionError('Coordinator exited before live check/factor descendants were observed')
                state_path = output / 'batch/state.json'
                if state_path.exists():
                    state = json.loads(state_path.read_text())
                    entry = state['tasks']['cancel-check']
                    if entry['status'] == 'running':
                        group_id = entry['attempts'][-1]['pid']
                        observed = group_members(group_id)
                        if any('check_worker.py' in x['command'] for x in observed) and any('factor_worker.py' in x['command'] for x in observed):
                            break
                time.sleep(.025)
            else:
                raise AssertionError('Live same-group check/factor descendants not observed before deadline')
            process.send_signal(signal.SIGTERM)
            code = process.wait(timeout=30)
            assert code == 130, code
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline and any(x['state'] != 'Z' for x in group_members(group_id)):
                time.sleep(.05)
            live = [x for x in group_members(group_id) if x['state'] != 'Z']
            assert not live, ('Cancellation left live descendants; emergency test cleanup follows', live)
        finally:
            if process.poll() is None:
                process.send_signal(signal.SIGTERM)
                try:
                    process.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait()
            if group_id is not None and any(x['state'] != 'Z' for x in group_members(group_id)):
                # Only this test's recorded private group may be cleaned up.
                os.killpg(group_id, signal.SIGKILL)
    state_path = output / 'batch/state.json'
    state = json.loads(state_path.read_text())
    assert state['tasks']['cancel-check']['status'] == 'cancelled', state
    resumed = subprocess.run(command + ['--resume'], capture_output=True, text=True, timeout=120)
    (output / 'resume.stdout.json').write_text(resumed.stdout)
    (output / 'resume.stderr.log').write_text(resumed.stderr)
    assert resumed.returncode == 1, resumed.stdout
    after = json.loads(state_path.read_text())
    entry = after['tasks']['cancel-check']
    assert len(entry['attempts']) == 1 and entry['status'] == 'failed' and 'budget exhausted' in entry['error'], entry
    summary = {'coordinator_exit': code, 'private_process_group': group_id,
               'live_descendants_observed_before_cancel': observed, 'live_descendants_after_cancel': live,
               'cancelled_state_saved': True, 'resume_preserved_attempt_limit': True,
               'synthetic': True}
    (output / 'cancel-summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    parser.add_argument('--python', default=sys.executable)
    args = parser.parse_args()
    result = run(args.output, args.python)
    result['cancellation'] = cancellation_smoke(Path(args.output).resolve() / 'cancellation', args.python,
                                                 Path(args.output).resolve() / 'input/protocol.json')
    (Path(args.output) / 'smoke-summary.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
