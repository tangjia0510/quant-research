"""Portable library configuration and immutable, versioned dataset snapshots."""
from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import tempfile

from . import workspace as W

ROOTS = {'warehouse_root': 'warehouse', 'research_root': 'studies', 'runtime_root': 'runtime',
         'factor_root': 'factors', 'sources_root': 'sources'}
_RESERVED = {'con', 'prn', 'aux', 'nul', *(f'com{i}' for i in range(1, 10)), *(f'lpt{i}' for i in range(1, 10))}


def config_path(path=None):
    """Resolve the selected config filename without creating files or directories."""
    selected = path or os.environ.get('QUANT_RESEARCH_CONFIG')
    if not selected:
        home = os.environ.get('QUANT_RESEARCH_HOME') or str(Path.home() / 'quant-research')
        selected = Path(home).expanduser() / 'quant-research.json'
    return Path(selected).expanduser().resolve()


def _configuration(path, value):
    if not isinstance(value, dict) or value.get('schema_version') != 1:
        raise ValueError('Library config requires schema_version 1')
    resolved = {}
    for name in ROOTS:
        # Existing schema-1 libraries predate factor and acquisition storage.
        raw = value.get(name, ROOTS[name] if name in {'factor_root', 'sources_root'} else None)
        if not isinstance(raw, str) or not raw.strip():
            raise ValueError('Library config requires a nonempty ' + name)
        target = (path.parent / Path(raw).expanduser()).resolve()
        if target.is_relative_to(W.SKILL) or W.SKILL.is_relative_to(target):
            raise ValueError('Library roots must not overlap the skill directory')
        if target.exists() and not target.is_dir():
            raise ValueError('Library root must be a directory: ' + str(target))
        resolved[name] = target
    for left, first in resolved.items():
        for right, second in resolved.items():
            if left != right and first.is_relative_to(second):
                raise ValueError('Library roots must be disjoint: ' + left + ', ' + right)
    if any(path.is_relative_to(root) for root in resolved.values()):
        raise ValueError('Config file must stay outside all library root directories')
    return {'schema_version': 1, 'config_path': str(path),
            **{key: str(value) for key, value in resolved.items()},
            'configured_roots': {name: value.get(name, ROOTS[name]) for name in ROOTS}}


def load_config(path=None):
    selected = config_path(path)
    if not selected.is_file():
        raise ValueError('Library config does not exist; run config init: ' + str(selected))
    return _configuration(selected, W.read(selected))


def config_init(path=None, warehouse_root=None, research_root=None, runtime_root=None, factor_root=None,
                sources_root=None):
    from filelock import FileLock

    selected = config_path(path)
    if selected.is_relative_to(W.SKILL):
        raise ValueError('Library config must stay outside the skill directory')
    settings = dict(warehouse_root=warehouse_root, research_root=research_root, runtime_root=runtime_root,
                    factor_root=factor_root, sources_root=sources_root)
    value = {'schema_version': 1, **{key: str(settings[key]) if settings[key] is not None else default
                                    for key, default in ROOTS.items()}}
    result = _configuration(selected, value)
    selected.parent.mkdir(parents=True, exist_ok=True)
    with FileLock(str(selected) + '.lock', timeout=0):
        if selected.exists() or selected.is_symlink():
            raise ValueError('Library config already exists; existing configuration is preserved')
        for key in ROOTS:
            Path(result[key]).mkdir(parents=True, exist_ok=True)
        W.write(selected, value)
    return result


def safe_name(value, label='Dataset id'):
    if (not isinstance(value, str) or not re.fullmatch(r'[a-z0-9][a-z0-9._-]{0,63}', value)
            or value.endswith('.') or value.split('.')[0] in _RESERVED):
        raise ValueError(label + ' must be a portable lowercase name (letters, digits, dot, underscore or hyphen; max 64)')
    return value


def _files(root):
    """Reject links and special files, preserving a fully local immutable snapshot."""
    root = Path(root)
    if root.is_symlink():
        raise ValueError('Dataset sources and snapshots cannot contain symlinks: ' + str(root))
    if root.is_file():
        return {root.name: root}
    if not root.is_dir():
        raise ValueError('Dataset source must be a regular file or directory: ' + str(root))
    result = {}
    for path in sorted(root.rglob('*')):
        if path.is_symlink():
            raise ValueError('Dataset sources and snapshots cannot contain symlinks: ' + str(path))
        if path.is_file():
            result[path.relative_to(root).as_posix()] = path
        elif not path.is_dir():
            raise ValueError('Dataset contains a non-regular file: ' + str(path))
    if not result:
        raise ValueError('Dataset source directory is empty')
    return result


def _hashes(root):
    return {relative: W.digest(path) for relative, path in _files(root).items()}


def _copy_source(source, target, directory=False):
    source = Path(source).expanduser().absolute()
    if source.is_symlink():
        raise ValueError('Dataset source cannot be a symlink')
    if directory != source.is_dir():
        raise ValueError('qlib sources must be directories; csv/parquet/sidecars must be regular files')
    before = _hashes(source)
    if directory:
        target.mkdir()
        for relative, path in _files(source).items():
            destination = target / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
        copied = _hashes(target)
    else:
        shutil.copy2(source, target)
        copied = {source.name: W.digest(target)}
    if before != _hashes(source) or before != copied:
        raise ValueError('Dataset source changed during snapshot import; retry with stable source files')


def _dataset_folder(config, dataset_id, version):
    warehouse = Path(config['warehouse_root']).resolve()
    safe_name(dataset_id)
    safe_name(version, 'Dataset version')
    folder = warehouse / dataset_id / version
    if (warehouse / dataset_id).is_symlink() or folder.is_symlink():
        raise ValueError('Dataset paths cannot be symlinks')
    return W.inside(warehouse, Path(dataset_id) / version)


def dataset_add(config, dataset_id, version, source, format, universe=None, calendar=None, metadata=None,
                evidence=None):
    from filelock import FileLock

    if format not in {'csv', 'parquet', 'qlib'}:
        raise ValueError('Dataset format must be csv, parquet or qlib')
    if metadata is not None and not isinstance(metadata, dict):
        raise ValueError('Dataset metadata must be a JSON object')
    if evidence is not None and not isinstance(evidence, dict):
        raise ValueError('Dataset evidence must map relative filenames to source files')
    reserved = {'manifest.json', 'data.csv', 'data.parquet', 'data', 'universe.csv', 'calendar.txt'}
    for relative in evidence or {}:
        path = Path(relative)
        if (not isinstance(relative, str) or path.is_absolute() or not path.parts
                or '\\' in relative or any(part in {'.', '..'} or part.startswith('.') for part in path.parts)
                or path.parts[0] in reserved):
            raise ValueError('Evidence filenames must be relative and cannot replace dataset payload or manifest')
        for part in path.parts:
            safe_name(part, 'Evidence filename')
    folder = _dataset_folder(config, dataset_id, version)
    warehouse = Path(config['warehouse_root']).resolve()
    source = Path(source).expanduser().absolute()
    if source.is_dir() and warehouse.is_relative_to(source.resolve()):
        raise ValueError('Dataset source cannot contain the warehouse directory')
    if not warehouse.is_dir():
        raise ValueError('Configured warehouse directory is missing; restore it or run config init for a new library')
    with FileLock(str(warehouse / '.warehouse.lock'), timeout=0):
        if folder.exists() or folder.is_symlink():
            raise ValueError('Dataset version already exists; use a new version instead of overwriting')
        folder.parent.mkdir(parents=True, exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix='.import-', dir=folder.parent))
        try:
            payload = 'data' if format == 'qlib' else 'data.' + format
            _copy_source(source, temporary / payload, directory=format == 'qlib')
            sidecars = {}
            for key, supplied, name in [('universe', universe, 'universe.csv'), ('calendar', calendar, 'calendar.txt')]:
                if supplied is not None:
                    _copy_source(supplied, temporary / name)
                    sidecars[key] = name
            for relative, supplied in (evidence or {}).items():
                destination = temporary / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                _copy_source(supplied, destination)
            manifest = {'schema_version': 1, 'dataset_id': dataset_id, 'version': version,
                        'format': format, 'created_at': W.now(), 'source_origin': str(source),
                        'metadata': metadata or {}, 'payload': payload, **sidecars,
                        'files': _hashes(temporary)}
            if evidence:
                manifest['evidence'] = sorted(evidence)
            W.write(temporary / 'manifest.json', manifest)
            temporary.rename(folder)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
    return dataset_resolve(config, dataset_id, version)


def dataset_resolve(config, dataset_id, version, expected_hash=None):
    folder = _dataset_folder(config, dataset_id, version)
    manifest_path = folder / 'manifest.json'
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise ValueError('Dataset manifest is missing or is a symlink: ' + str(manifest_path))
    digest = W.digest(manifest_path)
    if expected_hash is not None and digest != expected_hash:
        raise ValueError('Dataset manifest changed from the pinned identity')
    manifest = W.read(manifest_path)
    if (manifest.get('schema_version') != 1 or manifest.get('dataset_id') != dataset_id
            or manifest.get('version') != version or manifest.get('format') not in {'csv', 'parquet', 'qlib'}):
        raise ValueError('Dataset manifest identity is invalid')
    expected_payload = 'data' if manifest['format'] == 'qlib' else 'data.' + manifest['format']
    if manifest.get('payload') != expected_payload or not isinstance(manifest.get('files'), dict):
        raise ValueError('Dataset manifest payload is invalid')
    actual = _hashes(folder)
    actual.pop('manifest.json', None)
    if actual != manifest['files']:
        raise ValueError('Dataset snapshot changed: unexpected, missing or modified files')
    payload = folder / expected_payload
    if (manifest['format'] == 'qlib') != payload.is_dir() or not payload.exists():
        raise ValueError('Dataset payload type does not match its format')
    result = {'dataset_id': dataset_id, 'version': version, 'format': manifest['format'],
              'path': str(payload), 'manifest_hash': digest, 'metadata': manifest.get('metadata', {}),
              'manifest_path': str(manifest_path)}
    for key, filename in [('universe', 'universe.csv'), ('calendar', 'calendar.txt')]:
        if key in manifest:
            if manifest[key] != filename or filename not in actual:
                raise ValueError('Invalid dataset ' + key + ' sidecar')
            result[key] = str(folder / filename)
    return result


def dataset_list(config):
    """Read inventory metadata cheaply; resolve verifies the full snapshot on use."""
    warehouse = Path(config['warehouse_root'])
    if not warehouse.is_dir():
        raise ValueError('Configured warehouse directory is missing')
    entries = []
    for manifest_path in sorted(warehouse.glob('*/*/manifest.json')):
        dataset_id, version = manifest_path.parent.parent.name, manifest_path.parent.name
        if dataset_id.startswith('.') or version.startswith('.'):
            continue
        entry = {'dataset_id': dataset_id, 'version': version, 'payload_verified': False}
        try:
            folder = _dataset_folder(config, dataset_id, version)
            if manifest_path.is_symlink() or manifest_path.parent.resolve() != folder:
                raise ValueError('Dataset manifest path cannot be a symlink')
            manifest = W.read(manifest_path)
            if (manifest.get('schema_version') != 1 or manifest.get('dataset_id') != dataset_id
                    or manifest.get('version') != version or manifest.get('format') not in {'csv', 'parquet', 'qlib'}
                    or not isinstance(manifest.get('metadata'), dict) or not isinstance(manifest.get('files'), dict)):
                raise ValueError('Dataset manifest identity or schema is invalid')
            entry.update(format=manifest['format'], manifest_hash=W.digest(manifest_path), metadata=manifest['metadata'])
        except Exception as error:
            entry['error'] = {'type': type(error).__name__, 'message': str(error)}
        entries.append(entry)
    return entries
