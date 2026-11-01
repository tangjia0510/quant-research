"""Preserve historical studies without presenting them as new verified experiments."""
from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import shutil
import stat
import tempfile

from filelock import FileLock

from . import workspace as W

DEFAULT_EXCLUSIONS = {'.git', '.venv', 'venv', 'node_modules', '__pycache__',
                      '.pytest_cache', '.DS_Store', '.artifact-signing-key'}


def _relative(value):
    if not isinstance(value, str) or not value or '\\' in value:
        raise ValueError('Archive paths must be nonempty relative POSIX paths')
    path = PurePosixPath(value)
    if path.is_absolute() or '..' in path.parts or str(path) == '.':
        raise ValueError('Archive paths cannot escape their root')
    return path.as_posix()


def _exclusion(relative, supplied):
    for prefix, reason in supplied.items():
        if relative == prefix or relative.startswith(prefix + '/'):
            return reason
    for name in PurePosixPath(relative).parts:
        if name in DEFAULT_EXCLUSIONS:
            return 'Rebuildable environment/cache, repository metadata, or separately retained signing material'
        if name == '.env' or name.startswith('.env.'):
            return 'Environment configuration may contain credentials; original retained separately'
    return None


def _snapshot(source, supplied):
    files, links, excluded = {}, {}, {}
    for directory, directories, names in os.walk(source, topdown=True, followlinks=False):
        directory = Path(directory)
        kept = []
        for name in sorted(directories):
            path = directory / name
            relative = path.relative_to(source).as_posix()
            reason = _exclusion(relative, supplied)
            if reason:
                excluded[relative] = reason
            elif path.is_symlink():
                links[relative] = {'original_target': os.readlink(path), 'action': 'recorded_only',
                                   'reason': 'Directory symlink is recorded without following its contents'}
            else:
                kept.append(name)
        directories[:] = kept
        for name in sorted(names):
            path = directory / name
            relative = path.relative_to(source).as_posix()
            reason = _exclusion(relative, supplied)
            if reason:
                excluded[relative] = reason
            elif path.is_symlink():
                links[relative] = {'original_target': os.readlink(path), 'action': 'recorded_only'}
            elif stat.S_ISREG(path.lstat().st_mode):
                files[relative] = {'sha256': W.digest(path), 'bytes': path.stat().st_size,
                                   'mtime_ns': path.stat().st_mtime_ns}
            else:
                raise ValueError('Archive source contains an unsupported special file: ' + relative)
    for relative, link in links.items():
        try:
            target = (source / relative).resolve()
            link['resolved_original_target'] = str(target)
            if target.is_relative_to(source):
                target_relative = target.relative_to(source).as_posix()
                if target_relative in files:
                    link.update(action='materialized', materialized_from=target_relative)
                    link.pop('reason', None)
                else:
                    link.setdefault('reason', 'Target is a directory, absent, or excluded from the archive')
            else:
                link.setdefault('reason', 'External target is recorded, not traversed; see registered dataset references')
        except (OSError, RuntimeError) as error:
            link['reason'] = 'Unresolvable original link: ' + type(error).__name__
    return {'files': files, 'links': links, 'excluded_paths': excluded}


def _file_hashes(root):
    values, inodes = {}, {}
    for directory, directories, names in os.walk(root, followlinks=False):
        directory = Path(directory)
        for name in directories + names:
            if (directory / name).is_symlink():
                raise ValueError('Archive payload cannot contain symlinks')
        for name in names:
            path = directory / name
            metadata = path.lstat()
            if not stat.S_ISREG(metadata.st_mode):
                raise ValueError('Archive payload contains an unsupported special file')
            # Native RD workspaces often link the same large HDF5 input many times.
            identity = (metadata.st_dev, metadata.st_ino, metadata.st_size,
                        metadata.st_mtime_ns, metadata.st_ctime_ns)
            if identity not in inodes:
                inodes[identity] = W.digest(path)
            values[path.relative_to(root.parent).as_posix()] = inodes[identity]
    return values


def read_archive(root):
    """Validate metadata and containment without rehashing potentially large artifacts."""
    root = Path(root).resolve()
    path = root / 'archive.json'
    if path.is_symlink():
        raise ValueError('Archive manifest cannot be a symlink')
    value = W.read(path)
    if (not isinstance(value, dict) or value.get('schema_version') != 1
            or value.get('kind') != 'historical_archive' or value.get('status') != 'archived'
            or not isinstance(value.get('id'), str) or not value['id']
            or not isinstance(value.get('title'), str) or not value['title']
            or value.get('mode') not in W.MODES | {'unknown'}
            or not isinstance(value.get('files'), dict) or not value['files']):
        raise ValueError('Invalid historical archive manifest')
    for relative, digest in value['files'].items():
        relative = _relative(relative)
        if not relative.startswith('original/') or not isinstance(digest, str) or not re.fullmatch(r'[0-9a-f]{64}', digest):
            raise ValueError('Invalid archive payload identity')
    if not isinstance(value.get('datasets'), list) or not isinstance(value.get('links'), dict):
        raise ValueError('Invalid archive references')
    expected = W.identity({key: item for key, item in value.items() if key != 'manifest_hash'})
    if value.get('manifest_hash') != expected:
        raise ValueError('Historical archive manifest changed')
    if value.get('report'):
        relative = _relative(value['report'])
        report = W.inside(root, relative)
        if relative not in value['files'] or report.is_symlink() or not report.is_file():
            raise ValueError('Historical report is missing or not part of the recorded archive')
        cursor = root
        for part in PurePosixPath(relative).parts:
            cursor /= part
            if cursor.is_symlink():
                raise ValueError('Historical report path cannot contain symlinks')
    return value


def verify_history(root):
    root = Path(root).resolve()
    archive = read_archive(root)
    original = root / 'original'
    if original.is_symlink() or not original.is_dir():
        raise ValueError('Historical payload directory is missing or is a symlink')
    actual = _file_hashes(original)
    if actual != archive['files']:
        raise ValueError('Historical archive payload changed: unexpected, missing or modified files')
    return {'workspace': str(root), 'id': archive['id'], 'status': 'archived',
            'historical_status': archive['historical_status'], 'verified': True,
            'files': len(actual), 'bytes': archive['logical_bytes'],
            'content_identity': archive['content_identity'], 'manifest_hash': archive['manifest_hash']}


def import_history(config, source, slug, title, mode='unknown', historical_status='unknown',
                   report=None, datasets=None, exclusions=None, notes=None):
    """Copy a historical artifact tree into an immutable, separately indexed envelope."""
    source_input = Path(source).expanduser().absolute()
    if source_input.is_symlink() or not source_input.is_dir():
        raise ValueError('Historical source must be a real directory, not a symlink')
    source = source_input.resolve()
    root = Path(config['research_root']).expanduser().resolve()
    if not root.is_dir() or root.is_relative_to(W.SKILL) or source == root or root.is_relative_to(source):
        raise ValueError('Choose an existing research root outside the source and skill directories')
    if (not isinstance(slug, str) or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', slug)
            or len(slug) > 48):
        raise ValueError('Archive slug requires 1-48 lowercase letters/digits with separating hyphens')
    if not isinstance(title, str) or not title.strip() or len(title) > 300:
        raise ValueError('Archive title must contain 1-300 characters')
    if mode not in W.MODES | {'unknown'}:
        raise ValueError('Historical mode must be a known research mode or unknown')
    if not isinstance(historical_status, str) or not historical_status.strip() or len(historical_status) > 200:
        raise ValueError('Historical status must be a short descriptive value')
    if exclusions is not None and not isinstance(exclusions, dict):
        raise ValueError('Archive exclusions must map relative paths to reasons')
    if datasets is not None and not isinstance(datasets, list):
        raise ValueError('Archive datasets must be a list of registered references')
    supplied = {_relative(key): value for key, value in (exclusions or {}).items()}
    if any(not isinstance(value, str) or not value.strip() for value in supplied.values()):
        raise ValueError('Every excluded path needs a reason')
    references = []
    from . import library

    for item in datasets or []:
        if not isinstance(item, dict) or not all(isinstance(item.get(key), str) and item[key] for key in ('id', 'version', 'manifest_hash')):
            raise ValueError('Historical dataset reference requires id, version and manifest_hash')
        if not re.fullmatch(r'[0-9a-f]{64}', item['manifest_hash']):
            raise ValueError('Historical dataset reference requires a SHA256 manifest identity')
        if item.get('source_relative'):
            _relative(item['source_relative'])
        library.dataset_resolve(config, item['id'], item['version'], item['manifest_hash'])
        references.append(dict(item))
    if report is not None:
        report = _relative(report)
    if (root / '.history-import.lock').is_symlink():
        raise ValueError('History import lock cannot be a symlink')
    with FileLock(str(root / '.history-import.lock'), timeout=30):
        before = _snapshot(source, supplied)
        if not before['files']:
            raise ValueError('No historical artifact files remain after exclusions')
        record = {'original_source': str(source), 'title': title.strip(), 'mode': mode,
                  'historical_status': historical_status, 'report': 'original/' + report if report else None,
                  'datasets': references, 'exclusion_rules': supplied, 'notes': notes or [], **before}
        content_identity = W.identity(record)
        for existing in sorted(root.glob('*/archive.json')):
            if existing.parent.name.startswith('.') or existing.is_symlink() or existing.parent.is_symlink():
                continue
            try:
                archived = W.read(existing)
            except (ValueError, OSError):
                continue  # Damaged unrelated entries remain visible in the catalog.
            if (isinstance(archived, dict) and archived.get('original_source') == str(source)
                    and archived.get('content_identity') == content_identity):
                return {**verify_history(existing.parent), 'cached': True}
        temporary = Path(tempfile.mkdtemp(prefix='.history-import-', dir=root))
        try:
            original = temporary / 'original'
            original.mkdir()
            for relative in before['files']:
                target = original / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source / relative, target)
            for relative, link in before['links'].items():
                if link['action'] == 'materialized':
                    target = original / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    copied_target = original / link['materialized_from']
                    try:
                        os.link(copied_target, target)
                    except OSError:
                        shutil.copy2(copied_target, target)
            expected = {'original/' + path: item['sha256'] for path, item in before['files'].items()}
            expected.update({'original/' + path: before['files'][link['materialized_from']]['sha256']
                             for path, link in before['links'].items() if link['action'] == 'materialized'})
            if before != _snapshot(source, supplied) or expected != _file_hashes(original):
                raise ValueError('Historical source changed during import; incomplete copy was not published')
            if report and 'original/' + report not in expected:
                raise ValueError('Historical report must be an included regular file or materialized internal link')
            timestamp = datetime.now(timezone.utc)
            identity = f'{timestamp:%Y%m%d-%H%M%SZ}-archive-{slug}-{secrets.token_hex(3)}'
            destination = root / identity
            if destination.exists():
                raise ValueError('Archive name collision; retry without altering existing records')
            archive = {**record, 'schema_version': 1, 'kind': 'historical_archive', 'id': identity,
                       'status': 'archived', 'imported_at': timestamp.isoformat(),
                       'content_identity': content_identity, 'files': expected,
                       'source_file_metadata': before['files'],
                       'logical_bytes': sum((original / p.removeprefix('original/')).stat().st_size for p in expected)}
            archive['manifest_hash'] = W.identity(archive)
            W.write(temporary / 'archive.json', archive)
            verify_history(temporary)
            temporary.rename(destination)
            return {**verify_history(destination), 'cached': False}
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
