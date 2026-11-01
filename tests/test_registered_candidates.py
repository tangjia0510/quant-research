"""Versioned feature references survive relocation and remain immutable."""
import shutil
from pathlib import Path

import pytest

from quantlib import library, workspace as W
from quantlib import factors


@pytest.fixture
def registered(tmp_path):
    from quantlib import factor_registry as F
    config = library.config_init(tmp_path / 'library/quant-research.json')
    package = tmp_path / 'package'
    package.mkdir()
    W.write(package / 'definition.json', {
        'schema_version': 1, 'factor_id': 'test-return', 'version': '1.0.0',
        'display_name': 'Test return', 'aliases': [], 'description': 'Past one-session return',
        'formula': 'close[t]/close[t-1]-1', 'max_lookback': 2,
        'scale_invariant': True, 'status': 'accepted', 'parameters': {},
        'output_columns': ['test_return'], 'limitations': ['Execution test only'],
        'source': {'kind': 'custom', 'study': 'test fixture'},
        'validation_context': {'research_effectiveness': 'not established'}})
    (package / 'factor.py').write_text(
        "def compute(frame, params):\n"
        "    return frame.groupby(level='instrument').close.pct_change(fill_method=None).rename('test_return')\n")
    F.add(config, package)
    protocol = tmp_path / 'protocol.json'
    W.write(protocol, {'mode': 'factor', 'data': {'format': 'csv', 'path': 'unused.csv'},
                       'splits': {'train': ['2020-01-01', '2020-03-31'],
                                  'valid': ['2020-04-01', '2020-05-31'],
                                  'discovery': ['2020-06-01', '2020-08-31'],
                                  'final': ['2020-09-01', '2020-12-31']}})
    root = Path(config['research_root']) / 'test-study'
    W.initialize(root, protocol)
    candidate = root / 'input.json'
    W.write(candidate, {'id': 'registered', 'kind': 'factor', 'hypothesis': 'Test portable feature binding',
                        'factor_refs': [{'id': 'test-return', 'version': '1.0.0'}]})
    return config, root, candidate


def test_old_library_config_defaults_factor_root_without_rewriting(tmp_path):
    config = tmp_path / 'old.json'
    W.write(config, {'schema_version': 1, 'warehouse_root': 'warehouse',
                     'research_root': 'studies', 'runtime_root': 'runtime'})
    before = config.read_bytes()
    assert library.load_config(config)['factor_root'] == str(tmp_path / 'factors')
    assert config.read_bytes() == before


def test_factor_root_cannot_overlap_existing_roots(tmp_path):
    with pytest.raises(ValueError, match='disjoint'):
        library.config_init(tmp_path / 'config.json', factor_root='studies/factors')


def test_candidate_snapshots_survive_removed_registry_and_move(registered, tmp_path):
    from quantlib import factor_registry as F
    config, root, candidate = registered
    F.validate(config, 'test-return', '1.0.0')
    saved = W.register(root, candidate, library_config_path=config['config_path'])
    assert saved['registered_factors'][0]['manifest_hash']
    assert 'factors/test-return/1.0.0/definition.json' in saved['files']
    assert 'factor-validations/test-return/1.0.0.json' in saved['files']
    moved = tmp_path / 'other-host'
    shutil.copytree(root, moved)
    shutil.rmtree(Path(config['config_path']).parent)
    loaded = W.register(moved, moved / 'input.json', library_config_path='/missing/config.json')
    assert loaded == saved
    assert W.verify_candidate(moved, 'registered') == saved
    from quantlib.factor_registry import validation_bars
    features, checks = factors.compute(moved, loaded, validation_bars())
    assert 'test_return' in features
    assert checks['registered_factors'][0]['checks']['future_perturbation']


def test_changed_ref_and_forged_snapshot_are_rejected(registered):
    config, root, path = registered
    W.register(root, path, library_config_path=config['config_path'])
    candidate = W.read(path)
    candidate['factor_refs'][0]['params'] = {'new_window': 5}
    W.write(path, candidate)
    with pytest.raises(ValueError, match='parameters|immutable'):
        W.register(root, path, library_config_path=config['config_path'])
    candidate['registered_factors'] = []
    W.write(path, candidate)
    with pytest.raises(ValueError, match='cannot be supplied'):
        W.register(root, path, library_config_path=config['config_path'])


def test_local_snapshot_tamper_is_detected(registered):
    config, root, path = registered
    candidate = W.register(root, path, library_config_path=config['config_path'])
    code = root / candidate['registered_factors'][0]['factor_file']
    code.write_text('tampered')
    with pytest.raises(ValueError, match='changed'):
        W.register(root, path, library_config_path=config['config_path'])


def test_duplicate_refs_are_not_silently_deduplicated(registered):
    config, root, path = registered
    candidate = W.read(path)
    candidate['factor_refs'] *= 2
    W.write(path, candidate)
    with pytest.raises(ValueError, match='repeat'):
        W.register(root, path, library_config_path=config['config_path'])


def test_pinned_receipt_does_not_overwrite_original_evidence(registered, tmp_path):
    from quantlib import factor_registry as F
    config, root, path = registered
    package = tmp_path / 'package'
    definition = W.read(package / 'definition.json')
    definition['version'] = '1.0.1'
    W.write(package / 'definition.json', definition)
    original = b'{"original": "evidence retained exactly"}\n'
    (package / 'library-validation.json').write_bytes(original)
    F.add(config, package)
    F.validate(config, 'test-return', '1.0.1')
    candidate = W.read(path)
    candidate['factor_refs'][0]['version'] = '1.0.1'
    W.write(path, candidate)
    saved = W.register(root, path, library_config_path=config['config_path'])
    folder = root / 'candidates/registered/factors/test-return/1.0.1'
    assert (folder / 'library-validation.json').read_bytes() == original
    manifest = W.read(folder / 'manifest.json')
    assert {key: W.digest(folder / key) for key in manifest['files']} == manifest['files']
    receipt = root / saved['registered_factors'][0]['validation_receipt']
    assert receipt.is_relative_to(root / 'candidates/registered/factor-validations')
    assert W.read(receipt)['status'] == 'passed_with_limitations'
    assert W.verify_candidate(root, 'registered') == saved
