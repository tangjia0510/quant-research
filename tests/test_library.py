"""Portable library imports preserve version identity and original source files."""
import json
from pathlib import Path
import shutil

import pytest

from quantlib import library as L
from quantlib import workspace as W


@pytest.fixture
def library(tmp_path):
    return L.config_init(tmp_path / 'library/quant-research.json')


@pytest.fixture
def source(tmp_path):
    path = tmp_path / 'daily.csv'
    path.write_text('datetime,instrument,open,high,low,close,volume\n2026-01-02,TEST,10,11,9,10,100\n')
    return path


def test_config_precedence_and_read_only_resolution(tmp_path, monkeypatch):
    monkeypatch.setenv('QUANT_RESEARCH_HOME', str(tmp_path / 'home'))
    assert L.config_path() == tmp_path / 'home/quant-research.json'
    monkeypatch.setenv('QUANT_RESEARCH_CONFIG', str(tmp_path / 'environment.json'))
    assert L.config_path() == tmp_path / 'environment.json'
    explicit = tmp_path / 'explicit.json'
    assert L.config_path(explicit) == explicit
    with pytest.raises(ValueError, match='config init'):
        L.load_config(explicit)
    assert not explicit.exists()
    assert not (tmp_path / 'home').exists()


def test_relative_roots_relocate_with_library(library, tmp_path):
    config_file = Path(library['config_path'])
    contents = W.read(config_file)
    assert contents['warehouse_root'] == 'warehouse'
    relocated = tmp_path / 'other-machine'
    shutil.copytree(config_file.parent, relocated)
    restored = L.load_config(relocated / config_file.name)
    assert restored['warehouse_root'] == str(relocated / 'warehouse')
    assert restored['research_root'] == str(relocated / 'studies')
    assert restored['runtime_root'] == str(relocated / 'runtime')


def test_explicit_roots_and_existing_config_are_preserved(tmp_path):
    path = tmp_path / 'config/settings.json'
    warehouse = tmp_path / 'external/datasets'
    result = L.config_init(path, warehouse_root=warehouse, research_root='../research', runtime_root='../envs')
    assert result['warehouse_root'] == str(warehouse)
    assert result['research_root'] == str(tmp_path / 'research')
    before = path.read_bytes()
    with pytest.raises(ValueError, match='already exists'):
        L.config_init(path)
    assert path.read_bytes() == before


@pytest.mark.parametrize('roots', [
    {'warehouse_root': 'same', 'research_root': 'same'},
    {'warehouse_root': 'warehouse', 'research_root': 'warehouse/research'},
    {'warehouse_root': str(W.SKILL / 'temporary-data')},
    {'warehouse_root': str(W.SKILL.parent)},
    {'research_root': '.'},
])
def test_config_rejects_overlapping_roots_before_writes(tmp_path, roots):
    path = tmp_path / 'new/settings.json'
    with pytest.raises(ValueError):
        L.config_init(path, **roots)
    assert not path.parent.exists()


def test_import_is_independent_immutable_and_pinned(library, source):
    original = source.read_bytes()
    imported = L.dataset_add(library, 'cn-daily', '2026-01-02', source, 'csv', metadata={'price_basis': 'raw'})
    assert source.read_bytes() == original
    assert Path(imported['path']).read_bytes() == original
    assert imported['metadata']['price_basis'] == 'raw'
    assert L.dataset_resolve(library, 'cn-daily', '2026-01-02', imported['manifest_hash']) == imported
    source.write_text('new source content')
    assert Path(imported['path']).read_bytes() == original
    with pytest.raises(ValueError, match='already exists'):
        L.dataset_add(library, 'cn-daily', '2026-01-02', source, 'csv')
    entries = L.dataset_list(library)
    assert [(x['dataset_id'], x['version']) for x in entries] == [('cn-daily', '2026-01-02')]
    assert entries[0]['manifest_hash'] == imported['manifest_hash']
    assert entries[0]['payload_verified'] is False


def test_dataset_and_sidecars_survive_move_without_origin(library, source, tmp_path):
    universe = tmp_path / 'members.csv'
    universe.write_text('instrument,start,end\nTEST,2020-01-01,2026-01-02\n')
    calendar = tmp_path / 'trading.txt'
    calendar.write_text('2026-01-02\n')
    first = L.dataset_add(library, 'cn-daily', 'v1.0', source, 'csv', universe=universe, calendar=calendar)
    copied = tmp_path / 'another-host'
    shutil.copytree(Path(library['config_path']).parent, copied)
    source.unlink()
    universe.unlink()
    calendar.unlink()
    restored = L.dataset_resolve(L.load_config(copied / 'quant-research.json'), 'cn-daily', 'v1.0', first['manifest_hash'])
    assert restored['manifest_hash'] == first['manifest_hash']
    assert str(copied) in restored['path']
    assert Path(restored['universe']).is_file()
    assert Path(restored['calendar']).is_file()


@pytest.mark.parametrize('tamper', ['modified', 'missing', 'extra', 'manifest', 'symlink'])
def test_snapshot_tampering_is_rejected(library, source, tmp_path, tamper):
    imported = L.dataset_add(library, 'daily', 'v1', source, 'csv')
    payload = Path(imported['path'])
    if tamper == 'modified':
        payload.write_text('altered')
    elif tamper == 'missing':
        payload.unlink()
    elif tamper == 'extra':
        (payload.parent / 'hidden.csv').write_text('extra')
    elif tamper == 'manifest':
        manifest = W.read(imported['manifest_path'])
        manifest['metadata'] = {'altered': True}
        W.write(imported['manifest_path'], manifest)
    else:
        payload.unlink()
        payload.symlink_to(source)
    with pytest.raises(ValueError):
        L.dataset_resolve(library, 'daily', 'v1', imported['manifest_hash'])


@pytest.mark.parametrize('name', ['../escape', '.', '..', 'UPPER', 'with space', 'con', 'nul.csv', 'trailing.', 'x' * 65])
def test_dataset_names_are_portable_and_cannot_escape(library, source, name):
    with pytest.raises(ValueError):
        L.dataset_add(library, name, 'v1', source, 'csv')
    with pytest.raises(ValueError):
        L.dataset_add(library, 'valid', name, source, 'csv')


def test_qlib_tree_and_symlink_rejection(library, tmp_path):
    provider = tmp_path / 'source-qlib'
    (provider / 'calendars').mkdir(parents=True)
    (provider / 'calendars/day.txt').write_text('2026-01-02\n')
    (provider / 'instruments').mkdir()
    (provider / 'instruments/all.txt').write_text('TEST\t2026-01-02\t2026-01-02\n')
    imported = L.dataset_add(library, 'qlib-cn', 'v1', provider, 'qlib')
    assert Path(imported['path']).is_dir()
    assert (Path(imported['path']) / 'calendars/day.txt').read_text() == '2026-01-02\n'
    (provider / 'linked.txt').symlink_to(provider / 'calendars/day.txt')
    with pytest.raises(ValueError, match='symlink'):
        L.dataset_add(library, 'qlib-cn', 'v2', provider, 'qlib')
    warehouse = Path(library['warehouse_root'])
    assert not (warehouse / 'qlib-cn/v2').exists()
    assert not list((warehouse / 'qlib-cn').glob('.import-*'))


def test_source_cannot_contain_warehouse(library):
    source = Path(library['config_path']).parent
    with pytest.raises(ValueError, match='cannot contain'):
        L.dataset_add(library, 'recursive', 'v1', source, 'qlib')


def test_bad_import_leaves_no_published_version(library, source, tmp_path):
    with pytest.raises(ValueError):
        L.dataset_add(library, 'bad', 'v1', source, 'csv', calendar=tmp_path / 'missing.txt')
    parent = Path(library['warehouse_root']) / 'bad'
    assert not (parent / 'v1').exists()
    assert not list(parent.glob('.import-*'))


def test_dataset_path_symlink_cannot_redirect_import(library, source, tmp_path):
    outside = tmp_path / 'outside'
    outside.mkdir()
    (Path(library['warehouse_root']) / 'daily').symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match='symlink'):
        L.dataset_add(library, 'daily', 'v1', source, 'csv')
    assert not list(outside.iterdir())


def test_inventory_reads_metadata_only_and_surfaces_broken_manifests(library, source, monkeypatch):
    first = L.dataset_add(library, 'daily', 'v1', source, 'csv')
    second = L.dataset_add(library, 'daily', 'v2', source, 'csv')
    Path(second['manifest_path']).write_text('{incomplete json')
    original_digest = W.digest

    def manifest_only(path):
        assert Path(path).name == 'manifest.json', 'inventory must not hash the entire warehouse'
        return original_digest(path)

    monkeypatch.setattr(W, 'digest', manifest_only)
    inventory = L.dataset_list(library)
    assert inventory[0]['manifest_hash'] == first['manifest_hash']
    assert inventory[0]['payload_verified'] is False
    assert inventory[1]['version'] == 'v2'
    assert inventory[1]['error']['type'] == 'JSONDecodeError'


def test_source_change_during_copy_is_not_published(library, source, monkeypatch):
    original_copy = shutil.copy2

    def copy_then_mutate(origin, target):
        result = original_copy(origin, target)
        Path(origin).write_text('changed after copy')
        return result

    monkeypatch.setattr(shutil, 'copy2', copy_then_mutate)
    with pytest.raises(ValueError, match='changed during'):
        L.dataset_add(library, 'unstable', 'v1', source, 'csv')
    assert not (Path(library['warehouse_root']) / 'unstable/v1').exists()
