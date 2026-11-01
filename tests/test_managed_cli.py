"""Managed CLI integration: identity, lookup and independent index failures."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import quant
from quantlib import catalog, library, workspace as W


@pytest.fixture
def managed(tmp_path, monkeypatch):
    monkeypatch.delenv('QUANT_RESEARCH_CONFIG', raising=False)
    monkeypatch.setenv('QUANT_RESEARCH_HOME', str(tmp_path / 'library'))
    config = library.config_init()
    source = tmp_path / 'source.csv'
    source.write_text('datetime,instrument,open,high,low,close,volume\n2020-01-01,A,1,1,1,1,100\n')
    dataset = library.dataset_add(config, 'market', 'v1', source, 'csv',
                                  metadata={'price_basis': 'raw', 'volume_unit': 'shares'})
    protocol = tmp_path / 'protocol-input.json'
    W.write(protocol, {'mode': 'factor', 'objective': 'Test portable identities',
                      'data': {'path': str(source), 'format': 'csv'},
                      'splits': {'train': ['2020-01-01', '2020-03-31'],
                                 'valid': ['2020-04-01', '2020-05-31'],
                                 'discovery': ['2020-06-01', '2020-08-31'],
                                 'final': ['2020-09-01', '2020-12-31']}})
    return config, dataset, protocol


def create(managed):
    config, _, protocol = managed
    args = quant.parser().parse_args(['--config', config['config_path'], 'study', 'new',
                                     '--slug', 'momentum', '--title', '动量研究',
                                     '--protocol', str(protocol), '--dataset', 'market', '--version', 'v1'])
    result = quant.dispatch(args)
    return Path(result['workspace']), args


def test_new_study_pins_portable_identity_and_updates_index(managed):
    config, dataset, _ = managed
    root, args = create(managed)
    spec = W.load(root)['data']
    assert not {'path', 'calendar', 'universe'} & spec.keys()
    assert spec['manifest_hash'] == dataset['manifest_hash']
    assert spec['price_basis'] == 'raw'
    resolved = quant.resolve_data(W.load(root), config['config_path'])
    assert resolved['data']['path'] == dataset['path']
    assert 'path' not in W.load(root)['data']
    assert args.library_index['count'] == 1
    entry = W.read(Path(config['research_root']) / 'index.json')['studies'][0]
    assert entry['workspace'] == root.name
    assert entry['status'] == 'initialized'
    assert entry['dataset'] == {'id': 'market', 'version': 'v1'}


def test_metadata_conflict_does_not_allocate_study(managed):
    config, _, protocol = managed
    content = W.read(protocol)
    content['data']['price_basis'] = 'adjusted'
    W.write(protocol, content)
    with pytest.raises(ValueError, match='conflicts'):
        create(managed)
    assert not list(Path(config['research_root']).glob('*/study.json'))


def test_unregistered_membership_is_rejected(managed):
    _, _, protocol = managed
    content = W.read(protocol)
    content['data']['universe'] = 'elsewhere.csv'
    W.write(protocol, content)
    with pytest.raises(ValueError, match='Register universe'):
        create(managed)


def test_prepare_rejects_modified_warehouse_before_writing_snapshot(managed):
    config, dataset, _ = managed
    root, _ = create(managed)
    before = (root / 'protocol.json').read_bytes()
    Path(dataset['path']).write_text('changed data')
    args = quant.parser().parse_args(['--config', config['config_path'], 'prepare', '--workspace', str(root)])
    with pytest.raises(ValueError, match='snapshot changed'):
        quant.dispatch(args)
    assert (root / 'protocol.json').read_bytes() == before
    assert not (root / 'prepared.json').exists()
    assert args.library_index['count'] == 1


def test_index_error_does_not_replace_original_command_failure(managed, monkeypatch):
    config, _, _ = managed
    root, _ = create(managed)
    monkeypatch.setattr(catalog, 'refresh', lambda _: (_ for _ in ()).throw(RuntimeError('index unavailable')))
    args = quant.parser().parse_args(['--config', config['config_path'], 'evaluate',
                                     '--workspace', str(root), '--candidate', str(root / 'absent.json')])
    with pytest.raises(FileNotFoundError, match='prepared.json'):
        quant.dispatch(args)
    assert 'index unavailable' in args.library_index['error']


def test_index_error_does_not_turn_success_into_failed_research(managed, monkeypatch):
    config, _, _ = managed
    root, _ = create(managed)
    monkeypatch.setattr(catalog, 'refresh', lambda _: (_ for _ in ()).throw(RuntimeError('index unavailable')))
    args = quant.parser().parse_args(['--config', config['config_path'], 'status', '--workspace', str(root)])
    assert quant.dispatch(args)['study']['mode'] == 'factor'
    assert 'index unavailable' in args.library_index['error']


def test_managed_protocol_rejects_unpinned_or_absolute_source(managed):
    root, _ = create(managed)
    content = W.load(root)
    content['data'].pop('manifest_hash')
    with pytest.raises(ValueError, match='requires'):
        W.validate(content)
    content = W.load(root)
    content['data']['path'] = '/another/machine.csv'
    with pytest.raises(ValueError, match='registered paths'):
        W.validate(content)


def test_bootstrap_defaults_to_configured_runtime_root(managed, monkeypatch):
    config, _, _ = managed
    monkeypatch.setattr(quant.shutil, 'which', lambda _: '/test/uv')
    calls = []

    def sync(command, **kwargs):
        calls.append((command, kwargs))
        Path(kwargs['env']['UV_PROJECT_ENVIRONMENT']).mkdir(parents=True)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(quant.subprocess, 'run', sync)
    args = quant.parser().parse_args(['--config', config['config_path'], 'bootstrap'])
    result = quant.dispatch(args)
    assert result['venv'] == str(Path(config['runtime_root']) / 'py311')
    assert '--locked' in calls[0][0]
    assert (Path(result['venv']) / '.quant-research-runtime').is_file()


def test_historical_import_status_and_report_do_not_rewrite_old_protocol(managed):
    config, _, protocol = managed
    original = protocol.parent / 'legacy'
    original.mkdir()
    (original / 'protocol.json').write_text('{"legacy": "different historical schema"}')
    (original / 'report.html').write_text('<h1>Original result</h1>')
    args = quant.parser().parse_args(['--config', config['config_path'], 'study', 'import',
                                     '--source', str(original), '--slug', 'legacy-study', '--title', '历史研究',
                                     '--mode', 'factor', '--historical-status', 'completed_with_rejections',
                                     '--report', 'report.html'])
    result = quant.dispatch(args)
    root = Path(result['workspace'])
    assert not (root / 'protocol.json').exists()
    assert (root / 'original/protocol.json').read_bytes() == (original / 'protocol.json').read_bytes()
    assert args.library_index['count'] == 1
    before = (root / 'original/report.html').read_bytes()
    for command in ('status', 'report'):
        value = quant.dispatch(quant.parser().parse_args([command, '--workspace', str(root)]))
        assert value['status'] == 'archived'
    assert (root / 'original/report.html').read_bytes() == before
    verified = quant.dispatch(quant.parser().parse_args(['study', 'verify', '--workspace', str(root)]))
    assert verified['verified']
    with pytest.raises(ValueError, match='read-only'):
        quant.dispatch(quant.parser().parse_args(['finalize', '--workspace', str(root)]))
