"""Versioned factor inputs retain provenance, rejected decisions and validations."""
from pathlib import Path
import shutil

import pytest

from quantlib import factor_registry as R
from quantlib import factors
from quantlib import workspace as W


FACTOR = '''import pandas as pd

def compute(frame, params):
    value = frame.groupby(level="instrument", sort=False).close.transform(
        lambda s: s.pct_change(5, fill_method=None))
    return value.to_frame("return_5")
'''


@pytest.fixture
def config(tmp_path):
    return {'factor_root': str(tmp_path / 'library' / 'factors')}


def package(path, *, factor_id='example', version='1.0.0', rejected=False, limitations=None):
    path.mkdir(parents=True)
    definition = {'schema_version': 1, 'factor_id': factor_id, 'version': version,
                  'display_name': 'Example', 'aliases': ['EXAMPLE'], 'description': 'Five-session return',
                  'formula': 'close / lag(close, 5) - 1', 'max_lookback': 6, 'scale_invariant': True,
                  'status': 'rejected' if rejected else 'accepted', 'limitations': limitations or [],
                  'source': {'kind': 'study', 'study_id': 'example-study'},
                  'validation_context': {'research_effectiveness': 'not established'},
                  'parameters': {}, 'output_columns': ['return_5']}
    if rejected:
        definition['rejection'] = {'reason': 'Group rejected: sibling exceeds the frozen lookback cap',
                                   'scope': 'group; not a mathematical defect of this factor'}
    else:
        (path / 'factor.py').write_text(FACTOR)
    (path / 'provenance').mkdir()
    (path / 'provenance' / 'original.py').write_text('# Historical code retained unchanged\n')
    W.write(path / 'definition.json', definition)
    return path


def test_add_is_immutable_idempotent_and_indexed(config, tmp_path):
    source = package(tmp_path / 'source')
    before = {path.name: path.read_bytes() for path in source.iterdir() if path.is_file()}
    added = R.add(config, source)
    assert added['reused'] is False
    assert added['validation']['status'] == 'unvalidated'
    assert R.add(config, source)['reused'] is True
    assert before == {path.name: path.read_bytes() for path in source.iterdir() if path.is_file()}
    original_manifest = Path(added['manifest_path']).read_bytes()
    assert R.resolve(config, 'example', '1.0.0')['manifest_hash'] == added['manifest_hash']
    (source / 'factor.py').write_text(FACTOR + '\n# A different version\n')
    with pytest.raises(ValueError, match='new version'):
        R.add(config, source)
    assert Path(added['manifest_path']).read_bytes() == original_manifest
    assert Path(added['code_path']).read_text() == FACTOR
    index = W.read(Path(config['factor_root']) / 'index.json')
    assert index['totals'] == {'versions': 1, 'runnable': 1, 'rejected': 0, 'errors': 0}
    assert index['factors'][0]['source']['study_id'] == 'example-study'
    assert 'example/1.0.0/definition.json' in (Path(config['factor_root']) / 'index.md').read_text()


def test_registry_relocates_without_source(config, tmp_path):
    source = package(tmp_path / 'source')
    first = R.add(config, source)
    copied = tmp_path / 'other-machine' / 'factors'
    shutil.copytree(config['factor_root'], copied)
    shutil.rmtree(source)
    shutil.rmtree(Path(config['factor_root']).parent)
    restored = R.resolve({'factor_root': str(copied)}, 'example', '1.0.0')
    assert restored['manifest_hash'] == first['manifest_hash']
    assert restored['code_path'].startswith(str(copied))
    assert Path(restored['code_path']).read_text() == FACTOR
    assert (Path(restored['folder']) / 'provenance/original.py').is_file()


@pytest.mark.parametrize('tamper', ['modified', 'missing', 'extra', 'symlink', 'manifest'])
def test_tampering_is_visible_and_cannot_resolve(config, tmp_path, tamper):
    source = package(tmp_path / 'source')
    added = R.add(config, source)
    payload = Path(added['code_path'])
    if tamper == 'modified':
        payload.write_text(FACTOR + '\n# tamper\n')
    elif tamper == 'missing':
        payload.unlink()
    elif tamper == 'extra':
        (payload.parent / 'unexpected.py').write_text('# extra\n')
    elif tamper == 'symlink':
        payload.unlink()
        payload.symlink_to(source / 'factor.py')
    else:
        manifest = W.read(added['manifest_path'])
        manifest['files']['factor.py'] = '0' * 64
        W.write(added['manifest_path'], manifest)
    with pytest.raises(ValueError):
        R.resolve(config, 'example', '1.0.0')
    inventory = R.refresh(config)
    assert inventory['totals']['errors'] == 1
    assert 'error' in inventory['factors'][0]


def test_rejected_records_stay_visible_but_cannot_execute(config, tmp_path):
    source = package(tmp_path / 'source', factor_id='rejected_history', rejected=True)
    record = R.add(config, source)
    assert record['code_path'] is None
    assert record['validation']['status'] == 'rejected'
    assert R.resolve(config, 'rejected_history', '1.0.0', require_runnable=False)['definition']['rejection']
    with pytest.raises(ValueError, match='Rejected'):
        R.resolve(config, 'rejected_history', '1.0.0')
    with pytest.raises(ValueError, match='Rejected'):
        R.validate(config, 'rejected_history', '1.0.0')
    entry = R.list_factors(config)[0]
    assert entry['status'] == 'rejected'
    assert entry['runnable'] is False
    assert 'sibling' in entry['rejection']['reason']
    assert not (Path(config['factor_root']) / 'validations').exists()


def test_failure_then_actual_success_retains_both_receipts(config, tmp_path, monkeypatch):
    source = package(tmp_path / 'source', limitations=['Synthetic verification does not establish returns.'])
    record = R.add(config, source)
    manifest_before = Path(record['manifest_path']).read_bytes()
    original_compute = factors.compute

    def interrupted_validation(*args, **kwargs):
        raise RuntimeError('Recorded infrastructure interruption')

    monkeypatch.setattr(factors, 'compute', interrupted_validation)
    failed = R.validate(config, 'example', '1.0.0')
    assert failed['status'] == 'failed'
    assert failed['error']['message'] == 'Recorded infrastructure interruption'
    failed_bytes = Path(failed['receipt_path']).read_bytes()
    assert R.resolve(config, 'example', '1.0.0')['validation']['status'] == 'failed'

    monkeypatch.setattr(factors, 'compute', original_compute)
    succeeded = R.validate(config, 'example', '1.0.0')
    assert succeeded['status'] == 'passed_with_limitations'
    assert succeeded['checks']['future_perturbation'] is True
    assert succeeded['checks']['prefix_invariance'] is True
    assert succeeded['checks']['declared_lookback_verified'] == 6
    assert succeeded['checks']['scale_invariance_checked'] is True
    assert Path(failed['receipt_path']).read_bytes() == failed_bytes
    assert Path(record['manifest_path']).read_bytes() == manifest_before
    current = R.resolve(config, 'example', '1.0.0')['validation']
    assert current['status'] == 'passed_with_limitations'
    assert current['failed_receipt_count'] == 1
    assert current['receipt_count'] == 2
    assert current['validator_matches_current'] is True
    assert current['receipt'] == succeeded['receipt']
    assert current['receipt_sha256'] == W.digest(succeeded['receipt_path'])
    assert not Path(current['receipt']).is_absolute()


def test_validation_rejects_actual_future_leakage(config, tmp_path):
    source = package(tmp_path / 'source')
    (source / 'factor.py').write_text('''import pandas as pd
def compute(frame, params):
    return frame.groupby(level="instrument").close.shift(-1).to_frame("return_5")
''')
    R.add(config, source)
    receipt = R.validate(config, 'example', '1.0.0')
    assert receipt['status'] == 'failed'
    assert 'Future perturbation' in receipt['error']['message']
    assert R.list_factors(config)[0]['validation']['failed_receipt_count'] == 1


def test_corrupt_validation_receipt_does_not_claim_success(config, tmp_path, monkeypatch):
    source = package(tmp_path / 'source')
    R.add(config, source)
    def fail(*args, **kwargs):
        raise RuntimeError('test evidence')
    monkeypatch.setattr(factors, 'compute', fail)
    result = R.validate(config, 'example', '1.0.0')
    receipt = W.read(result['receipt_path'])
    receipt['status'] = 'passed'
    W.write(result['receipt_path'], receipt)
    summary = R.resolve(config, 'example', '1.0.0')['validation']
    assert summary['status'] == 'failed'
    assert summary['receipt_errors'][0]['message'] == 'Validation receipt hash mismatch'
    assert summary['receipt_count'] == 0


@pytest.mark.parametrize('factor_id,version', [('UPPER', '1.0.0'), ('../escape', '1.0.0'),
    ('validations', '1.0.0'), ('index.json', '1.0.0'), ('index.md', '1.0.0'),
    ('example', '../escape'), ('example', 'latest'), ('example', '01.0.0')])
def test_invalid_identity_rejected_before_publication(config, tmp_path, factor_id, version):
    source = package(tmp_path / 'source', factor_id=factor_id, version=version)
    with pytest.raises(ValueError):
        R.add(config, source)
    assert not Path(config['factor_root']).exists()


def test_source_and_target_symlinks_are_rejected(config, tmp_path):
    source = package(tmp_path / 'source')
    (source / 'linked').symlink_to(source / 'factor.py')
    with pytest.raises(ValueError, match='symlink'):
        R.add(config, source)
    (source / 'linked').unlink()
    root = Path(config['factor_root'])
    root.mkdir(parents=True)
    outside = tmp_path / 'outside'
    outside.mkdir()
    (root / 'example').symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match='symlink'):
        R.add(config, source)
    assert not list(outside.iterdir())
    assert R.list_factors(config)[0]['error']['message'] == 'Factor paths cannot be symlinks'


def test_partial_import_not_published_when_source_changes(config, tmp_path, monkeypatch):
    source = package(tmp_path / 'source')
    copy = shutil.copy2
    def changing_copy(origin, target):
        result = copy(origin, target)
        if Path(origin).name == 'factor.py':
            Path(origin).write_text(FACTOR + '\n# unstable\n')
        return result
    monkeypatch.setattr(shutil, 'copy2', changing_copy)
    with pytest.raises(ValueError, match='changed during'):
        R.add(config, source)
    assert not (Path(config['factor_root']) / 'example/1.0.0').exists()
    assert not list((Path(config['factor_root']) / 'example').glob('.import-*'))


def test_definition_change_before_hashing_does_not_publish_bad_identity(config, tmp_path, monkeypatch):
    source = package(tmp_path / 'source')
    read_definition = R._definition
    changed = False
    def read_then_change(folder):
        nonlocal changed
        result = read_definition(folder)
        if Path(folder) == source and not changed:
            changed = True
            W.write(source / 'definition.json', {**result, 'factor_id': 'different'})
        return result
    monkeypatch.setattr(R, '_definition', read_then_change)
    with pytest.raises(ValueError, match='definition changed'):
        R.add(config, source)
    assert not (Path(config['factor_root']) / 'example/1.0.0').exists()
    assert not (Path(config['factor_root']) / 'different/1.0.0').exists()


def test_accepted_factor_requires_declared_output_columns(config, tmp_path):
    source = package(tmp_path / 'source')
    definition = W.read(source / 'definition.json')
    del definition['output_columns']
    W.write(source / 'definition.json', definition)
    with pytest.raises(ValueError, match='output_columns'):
        R.add(config, source)
    assert not Path(config['factor_root']).exists()


def test_seed_reuses_versions_and_keeps_rejected_record(config, tmp_path, monkeypatch):
    seeds = tmp_path / 'seeds'
    package(seeds / 'example/1.0.0')
    package(seeds / 'rejected_history/1.0.0', factor_id='rejected_history', rejected=True)
    monkeypatch.setattr(R, 'SEED_ROOT', seeds)
    seeded = R.seed(config)
    assert seeded['count'] == 2
    assert all(not x['reused'] for x in seeded['factors'])
    assert all(x['reused'] for x in R.seed(config)['factors'])
    assert R.refresh(config)['totals'] == {'versions': 2, 'runnable': 1, 'rejected': 1, 'errors': 0}


def test_malformed_version_stays_in_index(config, tmp_path):
    root = Path(config['factor_root'])
    folder = root / 'example' / 'broken-version'
    folder.mkdir(parents=True)
    (folder / 'definition.json').write_text('{incomplete')
    entries = R.list_factors(config)
    assert entries[0]['version'] == 'broken-version'
    assert 'semantic version' in entries[0]['error']['message']
