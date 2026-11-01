"""Catalog behavior is derived from portable study files, never a second state machine."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import re
import shutil

import pytest

from quantlib import catalog
from quantlib import workspace as W


@pytest.fixture
def config(tmp_path):
    root = tmp_path / 'research'
    root.mkdir()
    return {'research_root': str(root)}


def make_study(config, tmp_path, slug='momentum', managed=True):
    protocol = tmp_path / (slug + '-protocol.json')
    W.write(protocol, {'schema_version': 1, 'mode': 'factor',
                       'data': {'format': 'csv', 'path': 'bars.csv'},
                       'splits': {'train': ['2020-01-01', '2020-03-31'],
                                  'valid': ['2020-04-01', '2020-05-31'],
                                  'discovery': ['2020-06-01', '2020-07-31'],
                                  'final': ['2020-08-01', '2020-12-31']}})
    if managed:
        root, metadata = catalog.allocate(config, slug, 'factor', title='动量研究')
    else:
        root = Path(config['research_root']) / slug
    W.initialize(root, protocol)
    if managed:
        catalog.finish_registration(root, metadata)
    return root


def freeze(root, candidates):
    W.write(root / 'freeze.json', {'candidates': {name: 'unused-for-index' for name in candidates}})
    study = W.read(root / 'study.json')
    study['freeze_hash'] = W.digest(root / 'freeze.json')
    W.write(root / 'study.json', study)


def run(root, phase, name, status):
    W.write(root / 'runs' / phase / name / 'run.json',
            {'candidate': name, 'phase': phase, 'status': status, 'started_at': W.now()})


def status(config):
    return catalog.refresh(config)['entries'][0]['status']


def test_unique_utc_names_preserve_collisions(config, monkeypatch):
    class FixedTime:
        @staticmethod
        def now(tz):
            return catalog.datetime.fromisoformat('2026-11-01T08:00:00+00:00')
    # Capture the original type before replacing the module binding.
    original_datetime = catalog.datetime
    FixedTime.now = staticmethod(lambda tz: original_datetime.fromisoformat('2026-11-01T08:00:00+00:00'))
    monkeypatch.setattr(catalog, 'datetime', FixedTime)
    suffixes = iter(['abcdef', 'abcdef', '000001'])
    monkeypatch.setattr(catalog.secrets, 'token_hex', lambda n: next(suffixes))
    first, metadata = catalog.allocate(config, 'price-momentum', 'factor')
    (first / 'preserve.txt').write_text('important')
    second, _ = catalog.allocate(config, 'price-momentum', 'factor')
    assert first != second
    assert re.fullmatch(r'20261101-080000Z-factor-price-momentum-[0-9a-f]{6}', second.name)
    assert metadata['created_at'] == '2026-11-01T08:00:00+00:00'
    assert (first / 'preserve.txt').read_text() == 'important'


@pytest.mark.parametrize('slug', ['../escape', '/absolute', 'Bad', '-leading', 'trailing-', 'two--parts', '', 'a' * 49])
def test_slug_rejects_traversal_and_unsafe_names(config, slug):
    with pytest.raises(ValueError):
        catalog.allocate(config, slug, 'factor')
    assert list(Path(config['research_root']).iterdir()) == []


def test_registration_after_init_and_immutable(config, tmp_path):
    root = make_study(config, tmp_path)
    metadata = W.read(root / 'registry.json')
    with pytest.raises(ValueError, match='already exists'):
        catalog.finish_registration(root, metadata)
    assert W.read(root / 'registry.json') == metadata
    assert status(config) == 'initialized'


def test_catalog_state_changes_and_final_selection_completion(config, tmp_path):
    root = make_study(config, tmp_path)
    assert status(config) == 'initialized'
    W.write(root / 'prepared.json', {'files': {}})
    assert status(config) == 'prepared'
    run(root, 'discovery', 'one', 'running')
    assert status(config) == 'running'
    run(root, 'discovery', 'one', 'failed')
    assert status(config) == 'failed'
    run(root, 'discovery', 'one', 'complete')
    assert status(config) == 'discovery_complete'
    freeze(root, ['one', 'two'])
    assert status(config) == 'frozen'
    study = W.read(root / 'study.json')
    study['final_exposed'] = True
    W.write(root / 'study.json', study)
    assert status(config) == 'final_pending'
    run(root, 'final', 'one', 'complete')
    assert status(config) == 'final_pending'
    run(root, 'final', 'two', 'failed')
    assert status(config) == 'final_failed'
    run(root, 'final', 'two', 'complete')
    assert status(config) == 'final_complete'


def test_relocation_keeps_relative_links_and_rebuilds_deleted_index(config, tmp_path):
    root = make_study(config, tmp_path)
    (root / 'report.html').write_text('<p>Evidence</p>')
    (root / 'report.md').write_text('Evidence')
    first = catalog.refresh(config)
    moved = tmp_path / 'different-machine' / 'studies'
    shutil.copytree(config['research_root'], moved)
    (moved / 'index.json').unlink()
    (moved / 'index.md').unlink()
    second = catalog.refresh({'research_root': moved})
    assert first['entries'] == second['entries']
    saved = (moved / 'index.json').read_text()
    assert str(tmp_path) not in saved
    row = second['entries'][0]
    assert row['workspace'] == root.name
    assert row['report_html'] == root.name + '/report.html'
    assert row['artifact_integrity'] == 'not_checked'


def test_legacy_study_included_unrelated_folder_ignored(config, tmp_path):
    root = make_study(config, tmp_path, managed=False)
    unused = Path(config['research_root']) / 'unrelated'
    unused.mkdir()
    (unused / 'notes.txt').write_text('Keep me')
    result = catalog.refresh(config)
    assert result['count'] == 1
    assert result['entries'][0]['id'] == root.name
    assert (unused / 'notes.txt').read_text() == 'Keep me'


@pytest.mark.parametrize('damage', ['protocol_hash', 'bad_json', 'wrong_type', 'partial'])
def test_malformed_recognized_studies_remain_visible(config, tmp_path, damage):
    root = make_study(config, tmp_path)
    if damage == 'protocol_hash':
        protocol = W.read(root / 'protocol.json')
        protocol['seed'] = 1024
        W.write(root / 'protocol.json', protocol)
    elif damage == 'bad_json':
        (root / 'study.json').write_text('{invalid')
    elif damage == 'wrong_type':
        W.write(root / 'protocol.json', [])
        state = W.read(root / 'study.json')
        state['protocol_hash'] = W.digest(root / 'protocol.json')
        W.write(root / 'study.json', state)
    else:
        (root / 'study.json').unlink()
    result = catalog.refresh(config)
    assert result['count'] == result['errors'] == 1
    assert result['entries'][0]['errors']
    assert result['entries'][0]['status'] == 'error'


def test_symlinks_never_traversed(config, tmp_path):
    external = tmp_path / 'external'
    external.mkdir()
    sentinel = external / 'study.json'
    sentinel.write_text('{not valid json}')
    linked = Path(config['research_root']) / 'outside'
    linked.symlink_to(external, target_is_directory=True)
    assert catalog.refresh(config)['skipped_symlinks'] == ['outside']
    root = make_study(config, tmp_path)
    (root / 'runs').symlink_to(external, target_is_directory=True)
    result = catalog.refresh(config)
    assert result['errors'] == 1
    assert 'symlinks' in result['entries'][0]['errors'][0]
    assert sentinel.read_text() == '{not valid json}'


def test_duplicate_registered_identity_cannot_overwrite_rows(config, tmp_path):
    root = make_study(config, tmp_path)
    shutil.copytree(root, root.parent / 'copied-study')
    result = catalog.refresh(config)
    assert result['count'] == result['errors'] == 2
    assert all('Duplicate' in row['errors'][-1] for row in result['entries'])


def test_concurrent_rebuilds_write_valid_complete_index(config, tmp_path):
    for name in ('one', 'two', 'three'):
        make_study(config, tmp_path, name)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: catalog.refresh(config), range(8)))
    assert all(result['count'] == 3 and result['errors'] == 0 for result in results)
    index = W.read(Path(config['research_root']) / 'index.json')
    assert len(index['studies']) == 3
    assert index['generated_at'] in (Path(config['research_root']) / 'index.md').read_text()


def test_index_output_symlink_is_rejected(config, tmp_path):
    target = tmp_path / 'preserve.json'
    target.write_text('untouched')
    (Path(config['research_root']) / 'index.json').symlink_to(target)
    with pytest.raises(ValueError, match='symlink'):
        catalog.refresh(config)
    assert target.read_text() == 'untouched'


def test_library_cannot_write_inside_the_skill(config, monkeypatch):
    monkeypatch.setattr(W, 'SKILL', Path(config['research_root']))
    with pytest.raises(ValueError, match='outside the skill'):
        catalog.allocate(config, 'test', 'factor')
    with pytest.raises(ValueError, match='outside the skill'):
        catalog.refresh(config)
    assert list(Path(config['research_root']).iterdir()) == []


def test_managed_dataset_and_title_are_portable(config, tmp_path):
    root = make_study(config, tmp_path)
    protocol = W.read(root / 'protocol.json')
    protocol['data']['dataset'] = {'id': 'daily-cn', 'version': '2026-10-31', 'manifest_hash': 'preserved'}
    W.write(root / 'protocol.json', protocol)
    study = W.read(root / 'study.json')
    study['protocol_hash'] = W.digest(root / 'protocol.json')
    W.write(root / 'study.json', study)
    row = catalog.refresh(config)['entries'][0]
    assert row['dataset'] == {'id': 'daily-cn', 'version': '2026-10-31'}
    assert row['title'] == '动量研究'
