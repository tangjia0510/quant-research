import json
from pathlib import Path
import shutil

import pytest

from quantlib import catalog, history, library, workspace as W


@pytest.fixture
def fixture(tmp_path):
    config = library.config_init(tmp_path / 'library/quant-research.json')
    source = tmp_path / 'legacy'
    (source / 'results').mkdir(parents=True)
    (source / 'results/failed.json').write_text('{"status":"failed","reason":"rejected candidate"}')
    (source / 'report.html').write_text('<html>Original historical report</html>')
    (source / 'protocol.json').write_text('{"old": "schema"}')
    return config, source


def archive(fixture, **kwargs):
    config, source = fixture
    return history.import_history(config, source, 'old-study', '历史研究',
                                  mode='joint', historical_status='completed-with-rejections',
                                  report='report.html', **kwargs)


def test_original_files_and_failed_evidence_preserved(fixture):
    _, source = fixture
    original = {p.relative_to(source).as_posix(): (p.read_bytes(), p.stat().st_mtime_ns)
                for p in source.rglob('*') if p.is_file()}
    result = archive(fixture)
    root = Path(result['workspace'])
    assert not result['cached']
    assert history.verify_history(root)['verified']
    assert not (root / 'study.json').exists()
    assert not (root / 'protocol.json').exists()
    for relative, (content, mtime) in original.items():
        assert (source / relative).read_bytes() == content
        assert (root / 'original' / relative).read_bytes() == content
        assert (root / 'original' / relative).stat().st_mtime_ns == mtime
    assert archive(fixture)['workspace'] == str(root)
    assert archive(fixture)['cached']


def test_tamper_detected_and_retry_does_not_silently_recapture(fixture):
    root = Path(archive(fixture)['workspace'])
    (root / 'original/report.html').write_text('changed')
    with pytest.raises(ValueError, match='payload changed'):
        history.verify_history(root)
    with pytest.raises(ValueError, match='payload changed'):
        archive(fixture)


def test_unexpected_file_detected(fixture):
    root = Path(archive(fixture)['workspace'])
    (root / 'original/new.txt').write_text('extra')
    with pytest.raises(ValueError, match='payload changed'):
        history.verify_history(root)


def test_exclusions_keep_original_but_do_not_copy_credentials_or_runtime(fixture):
    _, source = fixture
    for relative in ['.env', '.env.local', '.venv/lib/foo.py', 'results/.artifact-signing-key',
                     '.git/config', 'scripts/__pycache__/x.pyc', 'data/cn/quote.bin']:
        p = source / relative
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text('private or redundant content')
    root = Path(archive(fixture, exclusions={'data/cn': 'Registered immutable warehouse version'})['workspace'])
    receipt = W.read(root / 'archive.json')
    assert 'data/cn' in receipt['excluded_paths']
    assert '.env' in receipt['excluded_paths']
    assert 'results/.artifact-signing-key' in receipt['excluded_paths']
    assert not (root / 'original/.env').exists()
    assert not (root / 'original/data/cn').exists()
    assert (source / 'results/.artifact-signing-key').is_file()


def test_internal_file_links_materialized_and_external_links_only_recorded(fixture, tmp_path):
    _, source = fixture
    (source / 'data').mkdir()
    data = source / 'data/prices.h5'
    data.write_bytes(b'not executed or parsed')
    (source / 'results/input.h5').symlink_to(data)
    external = tmp_path / 'external-secret'
    external.write_text('do not follow')
    (source / 'results/external').symlink_to(external)
    (source / 'data-link').symlink_to(source / 'data', target_is_directory=True)
    root = Path(archive(fixture)['workspace'])
    receipt = W.read(root / 'archive.json')
    assert not (root / 'original/results/input.h5').is_symlink()
    assert (root / 'original/results/input.h5').read_bytes() == data.read_bytes()
    assert receipt['links']['results/input.h5']['action'] == 'materialized'
    assert receipt['links']['results/external']['action'] == 'recorded_only'
    assert not (root / 'original/results/external').exists()
    assert receipt['links']['data-link']['action'] == 'recorded_only'
    assert history.verify_history(root)['verified']


def test_excluded_link_target_is_not_materialized(fixture):
    _, source = fixture
    (source / '.env').write_text('not copied')
    (source / 'results/env-link').symlink_to(source / '.env')
    root = Path(archive(fixture)['workspace'])
    assert not (root / 'original/results/env-link').exists()
    assert W.read(root / 'archive.json')['links']['results/env-link']['action'] == 'recorded_only'


def test_copy_tree_and_index_survive_source_removal(fixture, tmp_path):
    config, source = fixture
    prices = tmp_path / 'prices.csv'
    prices.write_text('datetime,instrument,close\n2026-10-29,A,1\n')
    registered = library.dataset_add(config, 'cn-daily', '2026-10-29', prices, 'csv')
    initial = archive(fixture, datasets=[{'id': 'cn-daily', 'version': '2026-10-29',
                                         'manifest_hash': registered['manifest_hash']}])
    source.rename(tmp_path / 'retired-source')
    copied = tmp_path / 'moved-library'
    shutil.copytree(Path(config['config_path']).parent, copied)
    moved_config = library.load_config(copied / 'quant-research.json')
    root = Path(moved_config['research_root']) / Path(initial['workspace']).name
    assert history.verify_history(root)['verified']
    result = catalog.refresh(moved_config)
    assert result['count'] == 1 and result['errors'] == 0
    entry = result['entries'][0]
    assert entry['status'] == 'archived'
    assert entry['historical_status'] == 'completed-with-rejections'
    assert entry['dataset'] == {'id': 'cn-daily', 'version': '2026-10-29'}
    assert entry['report_html'] == root.name + '/original/report.html'
    assert entry['artifact_integrity'] == 'not_checked'
    assert 'final_complete' not in Path(result['index_markdown']).read_text()


def test_malformed_archive_is_visible_in_catalog(fixture):
    config, _ = fixture
    root = Path(archive(fixture)['workspace'])
    (root / 'archive.json').write_text('{broken')
    result = catalog.refresh(config)
    assert result['count'] == 1 and result['errors'] == 1
    assert result['entries'][0]['status'] == 'error'


def test_archive_metadata_tamper_detected(fixture):
    root = Path(archive(fixture)['workspace'])
    value = W.read(root / 'archive.json')
    value['historical_status'] = 'different conclusion'
    W.write(root / 'archive.json', value)
    with pytest.raises(ValueError, match='manifest changed'):
        history.verify_history(root)


@pytest.mark.parametrize('path', ['../outside', '/absolute', 'data/../../outside', '.'])
def test_exclusion_paths_cannot_escape(fixture, path):
    with pytest.raises(ValueError, match='paths'):
        archive(fixture, exclusions={path: 'not allowed'})


def test_missing_report_does_not_publish_archive(fixture):
    config, source = fixture
    with pytest.raises(ValueError, match='report must'):
        history.import_history(config, source, 'bad', 'bad', report='missing.html')
    assert list(Path(config['research_root']).glob('*/archive.json')) == []


def test_changed_source_during_copy_does_not_publish(fixture, monkeypatch):
    config, source = fixture
    copy = history.shutil.copy2

    def mutate(src, destination):
        result = copy(src, destination)
        if Path(src).name == 'report.html':
            Path(src).write_text('changed while copying')
        return result

    monkeypatch.setattr(history.shutil, 'copy2', mutate)
    with pytest.raises(ValueError, match='source changed'):
        archive(fixture)
    assert list(Path(config['research_root']).glob('*/archive.json')) == []


def test_payload_symlink_tamper_rejected(fixture, tmp_path):
    root = Path(archive(fixture)['workspace'])
    path = root / 'original/report.html'
    path.unlink()
    path.symlink_to(tmp_path / 'elsewhere')
    with pytest.raises(ValueError):
        history.verify_history(root)


def test_dataset_reference_must_exist_and_match_pinned_manifest(fixture):
    with pytest.raises(ValueError, match='manifest is missing'):
        archive(fixture, datasets=[{'id': 'nonexistent', 'version': 'v1', 'manifest_hash': 'a' * 64}])


def test_unrelated_damaged_archive_does_not_block_import(fixture):
    config, _ = fixture
    bad = Path(config['research_root']) / 'damaged-history'
    bad.mkdir()
    (bad / 'archive.json').write_text('{broken')
    assert archive(fixture)['verified']
    result = catalog.refresh(config)
    assert result['count'] == 2 and result['errors'] == 1


def test_staging_archive_is_not_indexed(fixture):
    config, _ = fixture
    root = Path(archive(fixture)['workspace'])
    stage = root.parent / '.history-import-unpublished'
    shutil.copytree(root, stage)
    assert catalog.refresh(config)['count'] == 1
