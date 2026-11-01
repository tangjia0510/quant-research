#!/usr/bin/env python3
"""Run registered historical factors through all four modes on synthetic bars.

Requires the core runtime and models extra. Writes independent configured roots,
command transcripts and research evidence beneath a new --output directory.
The demonstration has no investment-validity claim.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

SKILL = Path(__file__).resolve().parents[1]


def write(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + '\n', encoding='utf-8')


class Commands:
    def __init__(self, output, python, configuration):
        self.output, self.python, self.configuration = output, python, configuration
        self.number = 0

    def __call__(self, *args, expect_ok=True):
        self.number += 1
        command = [str(self.python), str(SKILL / 'scripts/quant.py'), '--config', str(self.configuration), *map(str, args)]
        env = {key: value for key, value in os.environ.items() if key not in ('PYTHONPATH', 'PYTHONHOME')}
        env['PYTHONNOUSERSITE'] = '1'
        result = subprocess.run(command, capture_output=True, text=True, env=env, timeout=650)
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError:
            payload = None
        write(self.output / 'commands' / f'{self.number:03d}.json',
              {'command': command, 'returncode': result.returncode, 'stdout': result.stdout,
               'stderr': result.stderr, 'payload': payload, 'expected_success': expect_ok})
        if payload is None:
            raise AssertionError(f'CLI did not emit JSON: {args}: {result.stdout[-1000:]} {result.stderr[-1000:]}')
        if expect_ok:
            if result.returncode != 0 or not payload.get('ok'):
                raise AssertionError(f'Command failed: {args}: {payload}; stderr={result.stderr[-1500:]}')
            return payload['result']
        if result.returncode == 0 or payload.get('ok'):
            raise AssertionError(f'Expected rejection: {args}: {payload}')
        return payload


def run(output, python):
    output = Path(output).expanduser().resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError('Use a new empty output directory; prior smoke evidence is never overwritten.')
    output.mkdir(parents=True, exist_ok=True)
    configuration = output / 'library/quant-research.json'
    execute = Commands(output, python, configuration)
    evidence = {'status': 'RUNNING', 'synthetic': True,
                'purpose': 'Registered-factor software execution, not investment or factor-effectiveness validation',
                'python': str(python), 'configuration': str(configuration), 'modes': []}
    try:
        loader = importlib.util.spec_from_file_location('factor_smoke_make_demo', SKILL / 'assets/make_demo.py')
        module = importlib.util.module_from_spec(loader)
        loader.loader.exec_module(module)
        demo = module.create_demo(output / 'input')
        runtime = execute('doctor')
        if not runtime['core_ready'] or not runtime['custom_models_ready']:
            raise RuntimeError('Registered-factor smoke needs the full independent runtime including torch.')
        evidence['runtime'] = runtime
        roots = execute('config', 'init')
        assert Path(roots['research_root']).is_relative_to(output)
        assert Path(roots['factor_root']).is_relative_to(output)
        seeded = execute('factor', 'seed')
        assert seeded['count'] == 14
        assert len([entry for entry in seeded['factors'] if entry['definition']['status'] == 'accepted']) == 13
        validated = execute('factor', 'validate', '--id', 'deltab5', '--version', '1.0.0')
        assert validated['status'] in ('passed', 'passed_with_limitations')
        source_manifest = Path(roots['factor_root']) / 'deltab5/1.0.0/manifest.json'
        manifest_hash = hashlib.sha256(source_manifest.read_bytes()).hexdigest()
        metadata = output / 'input/dataset-metadata.json'
        write(metadata, {'region': 'cn', 'synthetic': True, 'price_basis': 'raw', 'volume_unit': 'shares',
                         'purpose': 'Synthetic registered-factor smoke'})
        execute('dataset', 'add', '--id', 'synthetic-daily', '--version', '1.0.0', '--source', demo['bars'],
                '--format', 'csv', '--metadata', metadata)
        for mode in ('factor', 'model', 'joint', 'report'):
            started = time.monotonic()
            registered = execute('study', 'new', '--slug', mode + '-registered-smoke',
                                 '--title', 'Synthetic registered-factor ' + mode + ' verification',
                                 '--protocol', demo['protocol'], '--dataset', 'synthetic-daily',
                                 '--version', '1.0.0', '--mode', mode)
            workspace = Path(registered['workspace'])
            assert workspace.parent == Path(roots['research_root'])
            execute('prepare', '--workspace', workspace)
            assert execute('prepare', '--workspace', workspace)['cached'] is True
            code_dir = workspace / 'input'
            code_dir.mkdir()
            candidate = {'id': mode + '_registered', 'kind': mode,
                         'hypothesis': 'Synthetic contract check: a pinned historical factor augments fixed baseline features.',
                         'features': ['return_5', 'volatility_20'],
                         'factor_refs': [{'id': 'deltab5', 'version': '1.0.0'}]}
            if mode in ('model', 'joint'):
                shutil.copy2(SKILL / 'assets/tiny_model.py', code_dir / 'model.py')
                candidate['model'] = {'kind': 'custom', 'file': 'input/model.py',
                                      'params': {'epochs': 4, 'patience': 2, 'batch_size': 128, 'lr': .01, 'seed': 42}}
            if mode == 'report':
                (code_dir / 'source.md').write_text(
                    '# Synthetic reproduction exercise\n\n'
                    'This is a supplied formula excerpt for interface verification, not an external research publication.\n\n'
                    'Define z20[t] = (close[t] - mean(close[t-19:t])) / std(close[t-19:t], ddof=0).\n'
                    'deltaB5[t] = (z20[t] - z20[t-5]) / 4. The finite lookback is 25 price observations.\n',
                    encoding='utf-8')
                assert execute('extract-report', '--input', code_dir / 'source.md',
                               '--output', code_dir / 'extracted.json')['pages'] == 1
                candidate['source'] = {'path': 'input/source.md',
                                       'locator': 'Page 1, formula paragraph, synthetic reproduction exercise',
                                       'formula': 'deltaB5[t] = (z20[t] - z20[t-5]) / 4; population std, 25 prices'}
            candidate_path = workspace / 'candidate-input.json'
            write(candidate_path, candidate)
            execute('check', '--workspace', workspace, '--candidate', candidate_path)
            snapshot_path = workspace / 'candidates' / candidate['id'] / 'candidate.json'
            snapshot_before = snapshot_path.read_bytes()
            snapshot = json.loads(snapshot_before)
            assert snapshot['registered_factors'][0]['manifest_hash'] == manifest_hash
            assert snapshot['registered_factors'][0]['output_columns'] == ['deltaB5']
            assert snapshot['registered_factors'][0]['validation_receipt']
            assert 'factor_file' not in snapshot
            result = execute('evaluate', '--workspace', workspace, '--candidate', candidate_path)
            assert execute('evaluate', '--workspace', workspace, '--candidate', candidate_path)['cached'] is True
            execute('freeze', '--workspace', workspace, '--candidates', candidate['id'])
            execute('finalize', '--workspace', workspace)
            finalized_again = execute('finalize', '--workspace', workspace)
            assert finalized_again[candidate['id']]['cached'] is True
            report = execute('report', '--workspace', workspace)
            state = execute('status', '--workspace', workspace)
            assert state['study']['final_exposed'] is True
            assert len(state['runs']) == 2 and all(run['status'] == 'complete' for run in state['runs'])
            baseline_expected = ['return_5', 'volatility_20'] + (['deltaB5'] if mode == 'model' else [])
            phases = []
            for phase in ('discovery', 'final'):
                folder = workspace / 'runs' / phase / candidate['id']
                recorded = json.loads((folder / 'run.json').read_text())
                measured = json.loads((folder / 'result.json').read_text())
                assert recorded['attempt'] == 1
                assert any(name.endswith('predictions.parquet') for name in recorded['artifacts'])
                assert any(name.endswith('portfolio.csv') for name in recorded['artifacts'])
                assert measured['baseline']['features'] == baseline_expected
                assert all(fold['feature_names'] == ['return_5', 'volatility_20', 'deltaB5'] for fold in measured['folds'])
                assert measured['simulator'] == 'qlib.SimulatorExecutor'
                assert measured['prediction_rows'] > 0
                phases.append({'phase': phase, 'prediction_rows': measured['prediction_rows'],
                               'candidate_features': measured['folds'][0]['feature_names'],
                               'baseline_features': measured['baseline']['features']})
            assert Path(report['markdown']).is_file() and Path(report['html']).is_file()
            assert 'deltab5' in Path(report['markdown']).read_text()
            altered_path = workspace / 'altered-candidate.json'
            write(altered_path, {**candidate, 'hypothesis': 'A different hypothesis cannot replace the same candidate ID.'})
            rejected = execute('evaluate', '--workspace', workspace, '--candidate', altered_path, expect_ok=False)
            assert snapshot_path.read_bytes() == snapshot_before
            evidence['modes'].append({'mode': mode, 'workspace': str(workspace), 'status': 'passed',
                                      'seconds': round(time.monotonic() - started, 2), 'candidate': candidate['id'],
                                      'candidate_model': candidate.get('model', {'kind': 'ridge'}),
                                      'factor': 'deltab5@1.0.0', 'manifest_hash': manifest_hash,
                                      'repeated_evaluation_cached': True, 'repeated_finalization_cached': True,
                                      'altered_candidate_rejected': rejected['ok'] is False,
                                      'phases': phases, 'report': report, 'discovery_result': result})
            write(output / 'smoke-results.json', evidence)
            print(json.dumps({'mode': mode, 'status': 'passed', 'workspace': str(workspace)}), flush=True)
        index = execute('index', 'refresh')
        evidence['catalog'] = index
        evidence['status'] = 'PASS'
        write(output / 'smoke-results.json', evidence)
        return evidence
    except BaseException as error:
        evidence.update(status='FAIL', error={'type': type(error).__name__, 'message': str(error)})
        write(output / 'smoke-results.json', evidence)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    parser.add_argument('--python', default=sys.executable)
    args = parser.parse_args()
    evidence = run(args.output, args.python)
    print(json.dumps({'status': evidence['status'], 'evidence': str(Path(args.output).resolve() / 'smoke-results.json')}))


if __name__ == '__main__':
    main()
