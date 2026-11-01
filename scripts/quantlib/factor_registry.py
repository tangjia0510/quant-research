"""Portable immutable factor definitions and append-only validation evidence.

A registered implementation is a reusable research input, not an endorsement of
its predictive power. Original implementations, restrictions and rejections are
part of the hashed package; new validation never edits that historical evidence.
"""
from __future__ import annotations

from datetime import datetime, timezone
import importlib.metadata
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile
import uuid

from . import workspace as W
from .library import safe_name

SEED_ROOT = W.SKILL / 'assets' / 'factor-library'
_SEMVER = re.compile(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)')
_SHA256 = re.compile(r'[0-9a-f]{64}')
_RESERVED = {'validations', 'index.json', 'index.md'}
_RESULTS = {'passed', 'passed_with_limitations', 'failed'}
_SCOPE = 'Synthetic implementation, output-contract and causality checks; not evidence of investment performance.'


def _root(config, *, create=False):
    root = Path(config['factor_root']).expanduser()
    if root.is_symlink():
        raise ValueError('Factor root cannot be a symlink')
    root = root.resolve()
    if root.is_relative_to(W.SKILL) or W.SKILL.is_relative_to(root):
        raise ValueError('Factor root must not overlap the skill directory')
    if create:
        root.mkdir(parents=True, exist_ok=True)
    if root.exists() and not root.is_dir():
        raise ValueError('Factor root must be a directory')
    return root


def _identity(factor_id, version):
    safe_name(factor_id, 'Factor id')
    if factor_id in _RESERVED:
        raise ValueError('Reserved factor id: ' + factor_id)
    if not isinstance(version, str) or not _SEMVER.fullmatch(version):
        raise ValueError('Factor version must be semantic version MAJOR.MINOR.PATCH')


def _folder(root, factor_id, version):
    _identity(factor_id, version)
    if (root / factor_id).is_symlink() or (root / factor_id / version).is_symlink():
        raise ValueError('Factor paths cannot be symlinks')
    return W.inside(root, Path(factor_id) / version)


def _files(folder, *, manifest=False):
    folder = Path(folder)
    if folder.is_symlink() or not folder.is_dir():
        raise ValueError('Factor package must be a regular directory, without symlinks')
    result = {}
    for path in sorted(folder.rglob('*')):
        if path.is_symlink():
            raise ValueError('Factor packages cannot contain symlinks: ' + str(path))
        if path.is_file():
            relative = path.relative_to(folder).as_posix()
            if relative == 'manifest.json' and not manifest:
                continue
            result[relative] = path
        elif not path.is_dir():
            raise ValueError('Factor packages cannot contain special files: ' + str(path))
    return result


def _hashes(folder):
    return {relative: W.digest(path) for relative, path in _files(folder).items()}


def _definition(folder):
    definition = W.read(Path(folder) / 'definition.json')
    if not isinstance(definition, dict) or definition.get('schema_version') != 1:
        raise ValueError('Factor definition requires schema_version 1')
    _identity(definition.get('factor_id'), definition.get('version'))
    for field in ('display_name', 'description', 'formula'):
        if not isinstance(definition.get(field), str) or not definition[field].strip():
            raise ValueError('Factor definition requires nonempty ' + field)
    for field in ('aliases', 'limitations'):
        if not isinstance(definition.get(field), list) or any(not isinstance(x, str) or not x for x in definition[field]):
            raise ValueError('Factor ' + field + ' must be a list of nonempty strings')
    source = definition.get('source')
    if not isinstance(source, dict) or not isinstance(source.get('kind'), str) or not source['kind']:
        raise ValueError('Factor source requires a nonempty kind and provenance metadata')
    if not isinstance(definition.get('validation_context'), dict):
        raise ValueError('Factor validation_context must preserve historical versus current evidence')
    if definition.get('status') not in {'accepted', 'rejected'}:
        raise ValueError('Factor status must be accepted or rejected')
    if not isinstance(definition.get('parameters', {}), dict):
        raise ValueError('Factor parameters must be a JSON object')
    if 'output_columns' in definition:
        columns = definition['output_columns']
        if (not isinstance(columns, list) or not 1 <= len(columns) <= 32
                or any(not isinstance(x, str) or not x or x.startswith('__') for x in columns)
                or len(columns) != len(set(columns))):
            raise ValueError('Factor output_columns must be 1 to 32 unique names')
    if definition['status'] == 'accepted':
        if 'output_columns' not in definition:
            raise ValueError('Runnable factor requires output_columns for its public interface')
        if type(definition.get('max_lookback')) is not int or not 1 <= definition['max_lookback'] <= 10000:
            raise ValueError('Runnable factor requires finite positive max_lookback observation count')
        if type(definition.get('scale_invariant')) is not bool:
            raise ValueError('Runnable factor requires explicit scale_invariant boolean')
        if not (Path(folder) / 'factor.py').is_file():
            raise ValueError('Runnable factor requires factor.py')
    else:
        if not isinstance(definition.get('rejection'), dict) or not definition['rejection']:
            raise ValueError('Rejected factor requires its rejection record')
        if (Path(folder) / 'factor.py').exists():
            raise ValueError('Rejected factors preserve code under provenance, without runnable factor.py')
    return definition


def _validator_signature():
    packages = {}
    for name in ('numpy', 'pandas', 'pyarrow'):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    runtime = {'python': sys.version.split()[0], 'packages': packages,
               'scripts': {name: W.digest(Path(__file__).with_name(name))
                           for name in ('factor_registry.py', 'factors.py', 'factor_worker.py')}}
    return {'hash': W.identity(runtime), 'runtime': runtime}


def _receipts(root, factor_id, version, manifest_hash):
    folder = root / 'validations' / factor_id / version
    entries, errors = [], []
    for parent in (root / 'validations', root / 'validations' / factor_id, folder):
        if parent.is_symlink():
            return [], [{'path': str(parent.relative_to(root)), 'message': 'Validation paths cannot be symlinks'}]
    for path in sorted(folder.glob('*.json')):
        relative = path.relative_to(root).as_posix()
        try:
            if path.is_symlink() or not path.is_file():
                raise ValueError('Validation receipt must be a regular file')
            value = W.read(path)
            if not isinstance(value, dict):
                raise ValueError('Invalid validation receipt')
            supplied_hash = value.get('receipt_hash')
            if supplied_hash != W.identity({k: v for k, v in value.items() if k != 'receipt_hash'}):
                raise ValueError('Validation receipt hash mismatch')
            if (value.get('schema_version') != 1 or value.get('factor_id') != factor_id
                    or value.get('version') != version or value.get('status') not in _RESULTS):
                raise ValueError('Invalid validation receipt identity or status')
            if value.get('manifest_hash') != manifest_hash:
                raise ValueError('Validation receipt refers to a different immutable package')
            entries.append({'path': relative, **value})
        except Exception as error:
            errors.append({'path': relative, 'message': str(error), 'type': type(error).__name__})
    return entries, errors


def _validation(root, definition, manifest_hash):
    receipts, errors = _receipts(root, definition['factor_id'], definition['version'], manifest_hash)
    latest = receipts[-1] if receipts else None
    status = 'rejected' if definition['status'] == 'rejected' else latest['status'] if latest else 'unvalidated'
    matches = latest.get('validator', {}).get('hash') == _validator_signature()['hash'] if latest else None
    if errors and status != 'rejected':
        status = 'failed'
    return {'status': status, 'latest_receipt': latest['path'] if latest else None,
            'receipt': latest['path'] if latest else None,
            'receipt_sha256': W.digest(root / latest['path']) if latest else None,
            'receipt_count': len(receipts), 'failed_receipt_count': sum(x['status'] == 'failed' for x in receipts),
            'receipt_paths': [x['path'] for x in receipts], 'receipt_errors': errors,
            'validator_matches_current': matches, 'scope': _SCOPE}


def resolve(config, factor_id, version, *, require_runnable=True):
    """Verify all bytes before returning a package; historical rejections cannot run."""
    root = _root(config)
    folder = _folder(root, factor_id, version)
    manifest_path = folder / 'manifest.json'
    if manifest_path.is_symlink():
        raise ValueError('Factor manifest cannot be a symlink')
    manifest = W.read(manifest_path)
    if (not isinstance(manifest, dict) or manifest.get('schema_version') != 1
            or manifest.get('factor_id') != factor_id or manifest.get('version') != version
            or not isinstance(manifest.get('files'), dict)):
        raise ValueError('Invalid factor manifest identity or schema')
    for relative, digest in manifest['files'].items():
        if (not isinstance(relative, str) or Path(relative).is_absolute() or '..' in Path(relative).parts
                or not isinstance(digest, str) or not _SHA256.fullmatch(digest)):
            raise ValueError('Invalid factor manifest file entry')
    if manifest.get('payload_hash') != W.identity(manifest['files']):
        raise ValueError('Factor manifest payload hash mismatch')
    if _hashes(folder) != manifest['files']:
        raise ValueError('Factor package changed: modified, missing or extra files')
    definition = _definition(folder)
    if definition['factor_id'] != factor_id or definition['version'] != version:
        raise ValueError('Factor definition identity does not match registry path')
    if require_runnable and definition['status'] == 'rejected':
        raise ValueError('Rejected factor cannot be used as a research input: ' + factor_id)
    manifest_hash = W.digest(manifest_path)
    return {'factor_id': factor_id, 'version': version, 'folder': str(folder),
            'code_path': str(folder / 'factor.py') if definition['status'] == 'accepted' else None,
            'manifest_path': str(manifest_path), 'manifest_hash': manifest_hash,
            'definition': definition, 'validation': _validation(root, definition, manifest_hash)}


def add(config, source):
    """Copy a definition package atomically. Existing identical versions are reused."""
    from filelock import FileLock

    source = Path(source).expanduser().absolute()
    _files(source, manifest=True)
    if (source / 'manifest.json').exists():
        raise ValueError('Source should be a definition package without a generated manifest.json')
    definition = _definition(source)
    before = _hashes(source)
    root = _root(config, create=True)
    if root.is_relative_to(source.resolve()):
        raise ValueError('Factor source cannot contain the factor root')
    folder = _folder(root, definition['factor_id'], definition['version'])
    with FileLock(str(root / '.factors.lock'), timeout=0):
        if folder.exists() or folder.is_symlink():
            existing = resolve(config, definition['factor_id'], definition['version'], require_runnable=False)
            if W.read(existing['manifest_path'])['files'] != before:
                raise ValueError('Factor version already exists with different content; create a new version')
            if _hashes(source) != before:
                raise ValueError('Factor source changed during snapshot import')
            _refresh(config)
            return {**existing, 'reused': True}
        folder.parent.mkdir(parents=True, exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix='.import-', dir=folder.parent))
        try:
            for relative, path in _files(source).items():
                target = temporary / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
            if before != _hashes(source) or before != _hashes(temporary):
                raise ValueError('Factor source changed during snapshot import')
            if _definition(temporary) != definition:
                raise ValueError('Factor definition changed during snapshot import')
            W.write(temporary / 'manifest.json', {
                'schema_version': 1, 'factor_id': definition['factor_id'], 'version': definition['version'],
                'registered_at': W.now(), 'files': before, 'payload_hash': W.identity(before),
            })
            temporary.rename(folder)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
        result = resolve(config, definition['factor_id'], definition['version'], require_runnable=False)
        _refresh(config)
        return {**result, 'reused': False}


def seed(config):
    """Install bundled definitions without changing existing immutable versions."""
    if not SEED_ROOT.is_dir():
        raise ValueError('Bundled factor definitions are missing')
    results = [add(config, path.parent) for path in sorted(SEED_ROOT.glob('*/*/definition.json'))]
    if not results:
        raise ValueError('Bundled factor definitions are empty')
    return {'factors': results, 'count': len(results), 'index': str(_root(config) / 'index.md')}


def list_factors(config):
    """Read every small factor package; corruption remains visible in the inventory."""
    root = _root(config)
    entries = []
    if not root.exists():
        return entries
    for identity in sorted(root.iterdir()):
        if identity.name.startswith('.') or identity.name in _RESERVED or identity.is_file():
            continue
        if identity.is_symlink():
            entries.append({'factor_id': identity.name, 'version': None,
                            'error': {'type': 'ValueError', 'message': 'Factor paths cannot be symlinks'}})
            continue
        for folder in sorted(identity.iterdir()):
            if folder.name.startswith('.'):
                continue
            entry = {'factor_id': identity.name, 'version': folder.name,
                     'path': folder.relative_to(root).as_posix()}
            try:
                record = resolve(config, identity.name, folder.name, require_runnable=False)
                definition = record['definition']
                entry.update(display_name=definition['display_name'], aliases=definition['aliases'],
                             status=definition['status'], runnable=definition['status'] == 'accepted',
                             manifest_hash=record['manifest_hash'], validation=record['validation'],
                             source=definition['source'], limitations=definition['limitations'],
                             definition_path=str(folder.relative_to(root) / 'definition.json'),
                             manifest_path=str(folder.relative_to(root) / 'manifest.json'),
                             code_path=str(folder.relative_to(root) / 'factor.py') if record['code_path'] else None)
                if definition.get('rejection'):
                    entry['rejection'] = definition['rejection']
            except Exception as error:
                entry['error'] = {'type': type(error).__name__, 'message': str(error)}
            entries.append(entry)
    return entries


def _refresh(config):
    root = _root(config, create=True)
    entries = list_factors(config)
    index = {'schema_version': 1, 'updated_at': W.now(), 'scope': _SCOPE, 'factors': entries,
             'totals': {'versions': len(entries), 'runnable': sum(x.get('runnable', False) for x in entries),
                        'rejected': sum(x.get('status') == 'rejected' for x in entries),
                        'errors': sum('error' in x for x in entries)}}
    W.write(root / 'index.json', index)
    lines = ['# Factor library', '', _SCOPE, '',
             '| Factor | Version | Definition | Validation | Source | Limitations / rejection |',
             '| --- | --- | --- | --- | --- | --- |']
    def cell(value):
        return str(value).replace('|', '\\|').replace('\n', ' ')
    for entry in entries:
        if 'error' in entry:
            lines.append(f"| {cell(entry['factor_id'])} | {cell(entry['version'])} | error | error | — | {cell(entry['error']['message'])} |")
            continue
        restrictions = '; '.join(entry['limitations'])
        if entry.get('rejection'):
            restrictions += ('; ' if restrictions else '') + json.dumps(entry['rejection'], ensure_ascii=False)
        validation = entry['validation']
        state = validation['status']
        if validation['validator_matches_current'] is False:
            state += ' (different validator; revalidate)'
        if validation['latest_receipt']:
            state = f"[{cell(state)}]({validation['latest_receipt']})"
        lines.append(f"| [{cell(entry['display_name'])}]({entry['definition_path']}) | {cell(entry['version'])} | {cell(entry['status'])} | {state} | {cell(entry['source']['kind'])} | {cell(restrictions)} |")
    lines.extend(['', 'Definitions and original evidence are immutable within each version. Validation receipts retain failed attempts.',
                  'Draft new factors inside a study, then register them under a new factor ID or semantic version.', ''])
    temporary = root / ('.index-' + uuid.uuid4().hex + '.md')
    try:
        temporary.write_text('\n'.join(lines), encoding='utf-8')
        temporary.replace(root / 'index.md')
    finally:
        temporary.unlink(missing_ok=True)
    return index


def refresh(config):
    from filelock import FileLock

    root = _root(config, create=True)
    with FileLock(str(root / '.factors.lock'), timeout=0):
        return _refresh(config)


def validation_bars(lookback=60):
    """Deterministic synthetic market bars for execution-contract verification."""
    import numpy as np
    import pandas as pd

    count = max(220, lookback * 3 + 3)
    dates = pd.bdate_range('2020-01-02', periods=count)
    random = np.random.default_rng(871340)
    frames = []
    for number, instrument in enumerate(('TEST_A', 'TEST_B', 'TEST_C')):
        close = (10 + 30 * number) * np.exp(np.cumsum(random.normal(.0002, .018, count)))
        open_ = close * np.exp(random.normal(0, .005, count))
        frame = pd.DataFrame({'datetime': dates, 'instrument': instrument, 'open': open_,
                              'high': np.maximum(open_, close) * (1 + random.uniform(.001, .025, count)),
                              'low': np.minimum(open_, close) * (1 - random.uniform(.001, .025, count)),
                              'close': close, 'volume': random.lognormal(12 + .4 * number, .5, count),
                              'factor': 1.0})
        frames.append(frame)
    return pd.concat(frames).set_index(['datetime', 'instrument']).sort_index()


def validate(config, factor_id, version):
    """Append a real execution receipt, retaining failures without altering code."""
    from filelock import FileLock
    from . import factors

    record = resolve(config, factor_id, version)
    definition = record['definition']
    root = _root(config)
    receipt = {'schema_version': 1, 'factor_id': factor_id, 'version': version,
               'manifest_hash': record['manifest_hash'], 'started_at': W.now(),
               'validator': _validator_signature(), 'scope': _SCOPE,
               'limitations': definition['limitations'], 'fixture': {'synthetic': True, 'seed': 871340,
               'instruments': 3, 'sessions': max(220, definition['max_lookback'] * 3 + 3)},
               'historical_context': definition['validation_context']}
    try:
        with tempfile.TemporaryDirectory(prefix='quant-factor-validation-') as temporary:
            workspace = Path(temporary)
            shutil.copy2(record['code_path'], workspace / 'factor.py')
            candidate = {'features': [], 'factor_file': 'factor.py', 'max_lookback': definition['max_lookback'],
                         'scale_invariant': definition['scale_invariant'],
                         'factor_params': definition.get('parameters', {}), 'factor_timeout': 120}
            output, checks = factors.compute(workspace, candidate, validation_bars(definition['max_lookback']))
            if definition.get('output_columns') and list(output.columns) != definition['output_columns']:
                raise ValueError('Computed columns do not match definition.output_columns')
            after = resolve(config, factor_id, version)
            if after['manifest_hash'] != record['manifest_hash']:
                raise ValueError('Factor version changed during validation')
            receipt.update(status='passed_with_limitations' if definition['limitations'] else 'passed',
                           checks=checks, output_columns=list(output.columns))
    except Exception as error:
        receipt.update(status='failed', error={'type': type(error).__name__, 'message': str(error)})
    receipt['completed_at'] = W.now()
    receipt['receipt_hash'] = W.identity(receipt)
    name = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ-') + uuid.uuid4().hex[:12] + '.json'
    path = root / 'validations' / factor_id / version / name
    with FileLock(str(root / '.factors.lock'), timeout=0):
        for parent in (root / 'validations', path.parent.parent, path.parent):
            if parent.is_symlink():
                raise ValueError('Validation paths cannot be symlinks')
        if path.exists():
            raise ValueError('Validation receipt already exists')
        W.write(path, receipt)
        _refresh(config)
    return {**receipt, 'receipt_path': str(path), 'receipt': path.relative_to(root).as_posix()}
