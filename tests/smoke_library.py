#!/usr/bin/env python3
"""Exercise managed research, immutable data and whole-library relocation via the CLI."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

SKILL = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def runtime_hashes():
    return {path.relative_to(SKILL).as_posix(): digest(path)
            for path in sorted((SKILL / 'scripts').rglob('*.py'))}


class Runner:
    def __init__(self, python, output):
        self.python, self.output = str(python), output
        self.receipts = []
        (output / 'logs').mkdir()

    def execute(self, label, *args, config=None, expect_ok=True):
        sequence = len(self.receipts) + 1
        prefix = f'{sequence:02d}-{label}'
        command = [self.python, str(SKILL / 'scripts/quant.py')]
        if config is not None:
            command += ['--config', str(config)]
        command += list(map(str, args))
        env = {key: value for key, value in os.environ.items() if key not in ('PYTHONPATH', 'PYTHONHOME')}
        env['PYTHONNOUSERSITE'] = '1'
        started = time.monotonic()
        result = subprocess.run(command, capture_output=True, text=True, env=env, timeout=650)
        (self.output / 'logs' / (prefix + '.stdout')).write_text(result.stdout)
        (self.output / 'logs' / (prefix + '.stderr')).write_text(result.stderr)
        receipt = {'label': label, 'command': command, 'exit_code': result.returncode,
                   'elapsed_seconds': round(time.monotonic() - started, 3), 'expected_success': expect_ok,
                   'stdout': 'logs/' + prefix + '.stdout', 'stderr': 'logs/' + prefix + '.stderr'}
        self.receipts.append(receipt)
        write(self.output / 'command-receipts.json', self.receipts)
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as error:
            raise AssertionError(f'{label}: command did not emit JSON: {result.stdout[-1000:]} {result.stderr[-1000:]}') from error
        if expect_ok:
            assert result.returncode == 0 and payload.get('ok'), f'{label}: {payload}'
            return payload['result']
        assert result.returncode != 0 and not payload.get('ok'), f'{label}: expected a recorded failure'
        return payload


def run(output, python):
    output = Path(output).resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError('Use a new empty output directory; previous evidence is never overwritten.')
    output.mkdir(parents=True, exist_ok=True)
    runner = Runner(python, output)
    before = runtime_hashes()
    write(output / 'runtime-before.json', before)
    try:
        runtime = runner.execute('doctor', 'doctor')
        assert runtime['core_ready'], 'Independent runtime requires the locked core dependencies'
        loader = importlib.util.spec_from_file_location('library_demo', SKILL / 'assets/make_demo.py')
        demo_module = importlib.util.module_from_spec(loader)
        loader.loader.exec_module(demo_module)
        demo = demo_module.create_demo(output / 'source-input')
        original_source = Path(demo['bars'])
        original_source_hash = digest(original_source)
        metadata = output / 'dataset-metadata.json'
        write(metadata, {'synthetic': True, 'price_basis': 'raw', 'volume_unit': 'shares', 'region': 'cn'})

        first_library = output / 'original-library'
        config = first_library / 'quant-research.json'
        configured = runner.execute('config-init', 'config', 'init', '--warehouse-root', 'datasets/warehouse',
                                    '--research-root', 'research/studies', '--runtime-root', 'execution/runtime', config=config)
        assert all(not Path(value).is_absolute() for value in read(config).values() if isinstance(value, str))
        assert configured['research_root'] == str(first_library / 'research/studies')
        registered = runner.execute('dataset-add', 'dataset', 'add', '--id', 'synthetic-daily', '--version', 'v1',
                                    '--source', original_source, '--format', 'csv', '--metadata', metadata, config=config)
        manifest_relative = Path(registered['manifest_path']).relative_to(first_library)
        payload_relative = Path(registered['path']).relative_to(first_library)
        manifest_before = Path(registered['manifest_path']).read_bytes()
        assert digest(original_source) == original_source_hash
        assert digest(registered['path']) == original_source_hash
        runner.execute('immutable-version-rejected', 'dataset', 'add', '--id', 'synthetic-daily', '--version', 'v1',
                       '--source', original_source, '--format', 'csv', config=config, expect_ok=False)
        inventory = runner.execute('dataset-list', 'dataset', 'list', config=config)['datasets']
        assert len(inventory) == 1 and inventory[0]['payload_verified'] is False
        assert inventory[0]['manifest_hash'] == registered['manifest_hash']

        primary = runner.execute('primary-new', 'study', 'new', '--slug', 'portable-factor', '--title', 'Synthetic relocation acceptance',
                                 '--protocol', demo['protocol'], '--dataset', 'synthetic-daily', '--version', 'v1', config=config)
        secondary = runner.execute('secondary-new', 'study', 'new', '--slug', 'unprepared-factor',
                                   '--protocol', demo['protocol'], '--dataset', 'synthetic-daily', '--version', 'v1', config=config)
        study, pending = Path(primary['workspace']), Path(secondary['workspace'])
        assert re.fullmatch(r'\d{8}-\d{6}Z-factor-portable-factor-[a-f0-9]{6}', study.name)
        assert study.parent == Path(configured['research_root']) and pending != study
        protocol_before = {path.name: (path / 'protocol.json').read_bytes() for path in (study, pending)}
        for content in protocol_before.values():
            spec = json.loads(content)['data']
            assert 'path' not in spec and spec['dataset_id'] == 'synthetic-daily'
            assert spec['manifest_hash'] == registered['manifest_hash']
        prepared = runner.execute('primary-prepare', 'prepare', '--workspace', study, config=config)
        assert not (pending / 'prepared.json').exists()
        code_dir = study / 'input'
        code_dir.mkdir()
        shutil.copy2(SKILL / 'assets/example_factor.py', code_dir / 'factor.py')
        candidate = {'id': 'portable_factor', 'kind': 'factor', 'hypothesis': 'Synthetic migration engineering check only.',
                     'factor_file': 'input/factor.py', 'factor_params': {'return_window': 5, 'volatility_window': 20},
                     'features': ['return_5', 'volatility_20'], 'max_lookback': 21}
        candidate_path = study / 'candidate-input.json'
        write(candidate_path, candidate)
        runner.execute('primary-check', 'check', '--workspace', study, '--candidate', candidate_path, config=config)
        discovery = runner.execute('primary-evaluate', 'evaluate', '--workspace', study, '--candidate', candidate_path, config=config)
        assert discovery['cached'] is False
        runner.execute('primary-freeze', 'freeze', '--workspace', study, '--candidates', candidate['id'], config=config)
        print(json.dumps({'stage': 'original_library_frozen', 'study': str(study)}), flush=True)

        relocated = output / 'relocated-library'
        shutil.copytree(first_library, relocated)
        first_library.rename(output / 'original-library-retired')
        Path(demo['protocol']).parent.rename(output / 'source-input-retired')
        assert not first_library.exists() and not original_source.exists()
        config = relocated / 'quant-research.json'
        study = relocated / study.relative_to(first_library)
        pending = relocated / pending.relative_to(first_library)
        candidate_path = study / 'candidate-input.json'
        index = runner.execute('relocated-index', 'index', 'refresh', config=config)
        assert index['count'] == 2 and index['errors'] == 0
        entries = {row['id']: row for row in index['entries']}
        assert entries[primary['id']]['status'] == 'frozen'
        assert entries[secondary['id']]['status'] == 'initialized'
        assert all(not Path(row['workspace']).is_absolute() for row in entries.values())
        assert (relocated / manifest_relative).read_bytes() == manifest_before
        assert digest(relocated / payload_relative) == original_source_hash
        for path in (study, pending):
            assert (path / 'protocol.json').read_bytes() == protocol_before[path.name]

        final = runner.execute('relocated-finalize', 'finalize', '--workspace', study, config=config)
        assert final[candidate['id']]['cached'] is False
        report = runner.execute('relocated-report', 'report', '--workspace', study, config=config)
        assert Path(report['html']).is_file() and Path(report['markdown']).is_file()
        repeated = runner.execute('relocated-finalize-cached', 'finalize', '--workspace', study, config=config)
        assert repeated[candidate['id']]['cached'] is True
        cached_discovery = runner.execute('relocated-discovery-cached', 'evaluate', '--workspace', study,
                                          '--candidate', candidate_path, config=config)
        assert cached_discovery['cached'] is True
        for phase in ('discovery', 'final'):
            run_dir = study / 'runs' / phase / candidate['id']
            assert read(run_dir / 'run.json')['attempt'] == 1
            assert len(list(run_dir.glob('attempt-*'))) == 1

        second_prepared = runner.execute('relocated-secondary-prepare', 'prepare', '--workspace', pending, config=config)
        assert second_prepared['dataset_id'] == prepared['dataset_id']
        assert second_prepared['warehouse_dataset'] == prepared['warehouse_dataset']
        assert second_prepared['bars_sha256'] == prepared['bars_sha256']
        bad_factor = pending / 'bad-factor.py'
        marker = 'intentional-library-smoke-failure'
        bad_factor.write_text('def compute(frame, params):\n    raise RuntimeError(' + repr(marker) + ')\n')
        bad_candidate = pending / 'bad-candidate.json'
        write(bad_candidate, {'id': 'expected_failure', 'kind': 'factor', 'factor_file': 'bad-factor.py',
                              'hypothesis': 'Intentional failure to verify retained logs and automatic catalog refresh.',
                              'features': ['return_5', 'volatility_20'], 'max_lookback': 1})
        failure = runner.execute('relocated-secondary-failure', 'evaluate', '--workspace', pending,
                                 '--candidate', bad_candidate, config=config, expect_ok=False)
        failed_dir = pending / 'runs/discovery/expected_failure'
        failed_run = read(failed_dir / 'run.json')
        assert failed_run['status'] == 'failed' and failed_run['attempt'] == 1
        failure_log = failed_dir / 'attempt-1/execution.log'
        assert marker in failure_log.read_text()
        assert failure.get('library_index', {}).get('count') == 2
        # Read immediately: the failed command must refresh the index itself.
        on_disk = read(study.parent / 'index.json')
        final_entries = {row['id']: row for row in on_disk['studies']}
        assert final_entries[secondary['id']]['status'] == 'failed'
        assert final_entries[primary['id']]['status'] == 'final_complete'
        report_relative = final_entries[primary['id']]['report_html']
        assert not Path(report_relative).is_absolute() and (study.parent / report_relative).is_file()
        assert all(not Path(row['workspace']).is_absolute() for row in final_entries.values())
        for path in (study, pending):
            assert (path / 'protocol.json').read_bytes() == protocol_before[path.name]
        assert (relocated / manifest_relative).read_bytes() == manifest_before
        assert digest(relocated / payload_relative) == original_source_hash
        source_after = runtime_hashes()
        write(output / 'runtime-after.json', source_after)
        assert before == source_after, 'Runtime source changed during the experiment'
        result = {'status': 'PASS', 'synthetic': True, 'purpose': 'Managed library and relocation engineering validation only',
                  'runtime_source_unchanged': True, 'runtime': runtime,
                  'commands': len(runner.receipts), 'expected_rejections': 2,
                  'config': str(config), 'dataset_manifest_hash': registered['manifest_hash'],
                  'dataset_snapshot_identity': prepared['dataset_id'], 'dataset_payload_unchanged': True,
                  'original_library_and_source_paths_unavailable': True,
                  'protocol_bytes_unchanged': True, 'manifest_bytes_unchanged': True,
                  'relative_index_entries': True, 'index_count': 2,
                  'primary': {'id': primary['id'], 'workspace': str(study), 'status': 'final_complete',
                              'discovery_cached_after_move': True, 'final_cached_on_repeat': True,
                              'discovery_attempts': 1, 'final_attempts': 1, 'report': report['html']},
                  'secondary': {'id': secondary['id'], 'workspace': str(pending), 'status': 'failed',
                                'prepared_after_move': True, 'same_dataset_identity': True,
                                'failure_log': str(failure_log), 'automatic_index_refresh_verified': True},
                  'index': str(study.parent / 'index.json'), 'receipts': str(output / 'command-receipts.json')}
        write(output / 'smoke-results.json', result)
        print(json.dumps({'stage': 'relocation_verified', 'status': 'PASS', 'evidence': str(output / 'smoke-results.json')}), flush=True)
        return result
    except Exception as error:
        write(output / 'failure.json', {'type': type(error).__name__, 'message': str(error), 'commands': len(runner.receipts)})
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    parser.add_argument('--python', default=sys.executable)
    args = parser.parse_args()
    run(args.output, args.python)


if __name__ == '__main__':
    main()
