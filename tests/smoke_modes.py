#!/usr/bin/env python3
"""Execute all research modes against synthetic data; requires models/reports extras."""
from __future__ import annotations
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

SKILL = Path(__file__).resolve().parents[1]


def execute(python, *args, expect_ok=True):
    env = {k: v for k, v in os.environ.items() if k not in ('PYTHONPATH', 'PYTHONHOME')}
    env['PYTHONNOUSERSITE'] = '1'
    result = subprocess.run([str(python), str(SKILL / 'scripts/quant.py'), *map(str, args)],
                            capture_output=True, text=True, env=env, timeout=650)
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise AssertionError(f'CLI did not emit JSON: {args}: {result.stdout[-1000:]} {result.stderr[-1000:]}') from error
    if expect_ok:
        if result.returncode != 0 or not payload.get('ok'):
            raise AssertionError(f'Command failed: {args}: {payload}; stderr={result.stderr[-1500:]}')
        return payload['result']
    if result.returncode == 0 or payload.get('ok'):
        raise AssertionError(f'Expected rejection: {args}: {payload}')
    return payload


def run(output, python):
    output = Path(output).resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError('Use a new empty output directory; smoke evidence is never overwritten.')
    output.mkdir(parents=True, exist_ok=True)
    loader = importlib.util.spec_from_file_location('make_demo', SKILL / 'assets/make_demo.py')
    module = importlib.util.module_from_spec(loader)
    loader.loader.exec_module(module)
    demo = module.create_demo(output / 'input')
    checks = execute(python, 'doctor')
    if not checks['core_ready'] or not checks['custom_models_ready']:
        raise RuntimeError('Smoke needs the independent full runtime, including torch.')
    outcomes = []
    for mode in ('factor', 'model', 'joint', 'report'):
        started = time.monotonic()
        workspace = output / mode
        execute(python, 'init', '--workspace', workspace, '--protocol', demo['protocol'], '--mode', mode)
        execute(python, 'prepare', '--workspace', workspace)
        prepared_again = execute(python, 'prepare', '--workspace', workspace)
        assert prepared_again['cached'] is True
        code_dir = workspace / 'input'
        code_dir.mkdir()
        shutil.copy2(SKILL / 'assets/example_factor.py', code_dir / 'factor.py')
        shutil.copy2(SKILL / 'assets/tiny_model.py', code_dir / 'model.py')
        shutil.copy2(SKILL / 'assets/example_report.md', code_dir / 'source.md')
        candidate = {'id': f'{mode}_demo', 'kind': mode,
                     'hypothesis': 'Synthetic execution check: controlled comparison, no investment claim.',
                     'features': ['return_5', 'volatility_20'], 'max_lookback': 21}
        if mode in ('factor', 'joint', 'report'):
            candidate.update(factor_file='input/factor.py', factor_params={'return_window': 5, 'volatility_window': 20})
        if mode in ('model', 'joint'):
            candidate['model'] = {'kind': 'custom', 'file': 'input/model.py',
                                  'params': {'epochs': 4, 'patience': 2, 'batch_size': 128, 'lr': 0.01, 'seed': 42}}
        if mode == 'report':
            extraction = execute(python, 'extract-report', '--input', code_dir / 'source.md', '--output', code_dir / 'extracted.json')
            assert extraction['pages'] >= 1
            candidate['source'] = {'path': 'input/source.md', 'locator': 'Page 1 — hypothesis and formula',
                                   'formula': 'F = (close[t]/close[t-5]-1) / std(close[t-j]/close[t-j-1]-1,j=0..19,ddof=0)'}
        candidate_path = workspace / 'candidate-input.json'
        candidate_path.write_text(json.dumps(candidate, indent=2))
        execute(python, 'check', '--workspace', workspace, '--candidate', candidate_path)
        result = execute(python, 'evaluate', '--workspace', workspace, '--candidate', candidate_path)
        cached = execute(python, 'evaluate', '--workspace', workspace, '--candidate', candidate_path)
        assert cached['cached'] is True
        execute(python, 'freeze', '--workspace', workspace, '--candidates', candidate['id'])
        execute(python, 'finalize', '--workspace', workspace)
        execute(python, 'finalize', '--workspace', workspace)
        report = execute(python, 'report', '--workspace', workspace)
        state = execute(python, 'status', '--workspace', workspace)
        assert state['study']['final_exposed'] is True
        assert len(state['runs']) == 2 and all(r['status'] == 'complete' for r in state['runs'])
        for phase in ('discovery', 'final'):
            folder = workspace / 'runs' / phase / candidate['id']
            recorded = json.loads((folder / 'run.json').read_text())
            assert any(name.endswith('predictions.parquet') for name in recorded['artifacts'])
            assert any(name.endswith('portfolio.csv') for name in recorded['artifacts'])
            assert recorded['attempt'] == 1
        assert Path(report['markdown']).is_file() and Path(report['html']).is_file()
        altered = dict(candidate, hypothesis='Different candidate under same ID must be rejected')
        altered_path = workspace / 'altered.json'
        altered_path.write_text(json.dumps(altered))
        rejected = execute(python, 'evaluate', '--workspace', workspace, '--candidate', altered_path, expect_ok=False)
        outcomes.append({'mode': mode, 'workspace': str(workspace), 'status': 'passed',
                         'seconds': round(time.monotonic() - started, 2), 'candidate': candidate['id'],
                         'candidate_model': candidate.get('model', {'kind': 'ridge'}),
                         'repeated_evaluation_cached': True, 'altered_candidate_rejected': True,
                         'discovery_result': result})
        print(json.dumps({'mode': mode, 'status': 'passed', 'workspace': str(workspace)}), flush=True)
    evidence = {'status': 'PASS', 'synthetic': True, 'purpose': 'Functional execution, not strategy validation',
                'python': str(python), 'runtime': checks, 'modes': outcomes}
    (output / 'smoke-results.json').write_text(json.dumps(evidence, indent=2, allow_nan=False) + '\n')
    return evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    parser.add_argument('--python', default=sys.executable)
    args = parser.parse_args()
    evidence = run(args.output, args.python)
    print(json.dumps({'status': evidence['status'], 'evidence': str(Path(args.output).resolve() / 'smoke-results.json')}))


if __name__ == '__main__':
    main()
