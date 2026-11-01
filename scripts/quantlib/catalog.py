"""Portable study names and a disposable, file-based research index."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import html
import os
from pathlib import Path
import re
import secrets
import tempfile
from urllib.parse import quote

from filelock import FileLock

from . import workspace as W


def _research_root(config):
    root = Path(config['research_root']).expanduser().resolve()
    if root.is_relative_to(W.SKILL.resolve()):
        raise ValueError('Research root must be outside the skill directory')
    if not root.is_dir():
        raise ValueError('Configured research root does not exist; run config init first')
    return root


def allocate(config, slug, mode, title=None):
    """Reserve an empty workspace; the caller initializes its research protocol."""
    if not isinstance(slug, str) or len(slug) > 48 or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', slug):
        raise ValueError('Study slug requires 1-48 lowercase letters/digits with separating hyphens')
    if mode not in W.MODES:
        raise ValueError('Unknown study mode')
    title = slug if title is None else title
    if not isinstance(title, str) or not title.strip() or len(title) > 300:
        raise ValueError('Study title must contain 1-300 characters')
    root = _research_root(config)
    timestamp = datetime.now(timezone.utc)
    for _ in range(20):
        identity = f'{timestamp:%Y%m%d-%H%M%SZ}-{mode}-{slug}-{secrets.token_hex(3)}'
        workspace = root / identity
        try:
            workspace.mkdir()
        except FileExistsError:
            continue
        return workspace, {'schema_version': 1, 'id': identity, 'slug': slug,
                           'title': title.strip(), 'mode': mode, 'created_at': timestamp.isoformat()}
    raise ValueError('Could not reserve a unique study name; existing research was preserved')


def finish_registration(root, metadata):
    """Attach portable identity after successful initialization, without rewriting evidence."""
    root = Path(root).resolve()
    protocol = W.load(root)
    value = dict(metadata)
    if value.get('schema_version') != 1 or value.get('id') != root.name or value.get('mode') != protocol['mode']:
        raise ValueError('Registration does not match the allocated study')
    target = root / 'registry.json'
    if target.exists() or target.is_symlink():
        raise ValueError('Study registration already exists; identity is immutable')
    W.write(target, value)
    return value


def _guard(root, path):
    """Do not traverse study-controlled symlinks while rebuilding a catalog."""
    path = Path(path)
    relative = path.relative_to(root)
    cursor = root
    for part in relative.parts:
        cursor /= part
        if cursor.is_symlink():
            raise ValueError('Index does not follow symlinks: ' + relative.as_posix())
    return path


def _object(root, path):
    value = W.read(_guard(root, path))
    if not isinstance(value, dict):
        raise ValueError(path.name + ' must be a JSON object')
    return value


def _run_records(root):
    records, files = [], []
    for phase in ('discovery', 'final'):
        parent = _guard(root, root / 'runs' / phase)
        if not parent.exists():
            continue
        if not parent.is_dir():
            raise ValueError('Run phase must be a directory: ' + phase)
        for candidate in sorted(parent.iterdir()):
            _guard(root, candidate)
            if not candidate.is_dir():
                continue
            path = _guard(root, candidate / 'run.json')
            if not path.exists():
                continue
            run = _object(root, path)
            if run.get('status') not in {'running', 'failed', 'complete'}:
                raise ValueError('Unknown run status: ' + path.relative_to(root).as_posix())
            if run.get('candidate', candidate.name) != candidate.name or run.get('phase', phase) != phase:
                raise ValueError('Run identity does not match its directory')
            records.append({**run, 'candidate': candidate.name, 'phase': phase})
            files.append(path)
    return records, files


def _summarize(root):
    # A row remains visible even when some of its metadata is damaged.
    result = {'id': root.name, 'title': root.name, 'workspace': root.name,
              'mode': None, 'created_at': None, 'last_updated': None,
              'dataset': None, 'source_format': None, 'candidate_count': 0,
              'status': 'error', 'artifact_integrity': 'not_checked',
              'report_html': None, 'report_markdown': None, 'errors': []}
    observed = []
    try:
        registry_path = _guard(root, root / 'registry.json')
        if registry_path.exists():
            registry = _object(root, registry_path)
            if registry.get('schema_version') != 1 or not isinstance(registry.get('id'), str) or not registry['id']:
                raise ValueError('Invalid registry identity')
            # A renamed/moved directory does not change the registered identity.
            result.update(id=registry['id'], title=registry.get('title', registry['id']))
            observed.append(registry_path)
        for filename in ('study.json', 'protocol.json'):
            observed.append(_guard(root, root / filename))
        protocol = W.load(root)
        study = _object(root, root / 'study.json')
        result.update(mode=protocol['mode'], created_at=study.get('created_at'),
                      source_format=protocol.get('data', {}).get('format'))
        reference = protocol.get('data', {}).get('dataset')
        if isinstance(reference, dict):
            result['dataset'] = {key: reference.get(key) for key in ('id', 'version')}
        elif protocol.get('data', {}).get('dataset_id'):
            result['dataset'] = {'id': protocol['data']['dataset_id'],
                                 'version': protocol['data'].get('dataset_version')}
        candidate_dir = _guard(root, root / 'candidates')
        if candidate_dir.exists():
            for child in candidate_dir.iterdir():
                _guard(root, child)
                if child.is_dir() and _guard(root, child / 'candidate.json').exists():
                    result['candidate_count'] += 1
                    observed.append(child / 'candidate.json')
        records, files = _run_records(root)
        observed.extend(files)
        counts = Counter(record['status'] for record in records)
        result['run_counts'] = {name: counts[name] for name in ('running', 'complete', 'failed')}
        prepared_path = _guard(root, root / 'prepared.json')
        prepared = prepared_path.exists()
        if prepared:
            observed.append(prepared_path)
        freeze_path = _guard(root, root / 'freeze.json')
        frozen = freeze_path.exists()
        selected = {}
        if frozen:
            freeze = _object(root, freeze_path)
            selected = freeze.get('candidates')
            if not isinstance(selected, dict) or not selected:
                raise ValueError('Frozen selection must identify at least one candidate')
            if study.get('freeze_hash') != W.digest(freeze_path):
                raise ValueError('Frozen selection manifest changed or has no recorded hash')
            observed.append(freeze_path)
        final = {record['candidate']: record for record in records if record['phase'] == 'final'}
        exposed = bool(study.get('final_exposed'))
        if (exposed or final) and not frozen:
            raise ValueError('Final evaluation has no frozen selection')
        if any(name not in selected for name in final):
            raise ValueError('Final runs include an unselected candidate')
        if counts['running']:
            result['status'] = 'running'
        elif exposed or final:
            if any(record['status'] == 'failed' for record in final.values()):
                result['status'] = 'final_failed'
            elif all(final.get(name, {}).get('status') == 'complete' for name in selected):
                result['status'] = 'final_complete'
            else:
                result['status'] = 'final_pending'
        elif frozen:
            result['status'] = 'frozen'
        elif any(record['status'] == 'complete' for record in records):
            result['status'] = 'discovery_complete'
        elif counts['failed']:
            result['status'] = 'failed'
        else:
            result['status'] = 'prepared' if prepared else 'initialized'
        for key, filename in [('report_html', 'report.html'), ('report_markdown', 'report.md')]:
            report = _guard(root, root / filename)
            if report.is_file():
                result[key] = (Path(root.name) / filename).as_posix()
                observed.append(report)
    except (ValueError, KeyError, TypeError, AttributeError, OSError) as error:
        result['status'] = 'error'
        result['errors'].append(str(error).replace(str(root), '.'))
    present = [path for path in observed if path.exists() and not path.is_symlink()]
    if present:
        result['last_updated'] = datetime.fromtimestamp(max(p.stat().st_mtime for p in present), timezone.utc).isoformat()
    return result


def _summarize_archive(root):
    """A historical envelope is not a new execution of the current protocol."""
    from .history import read_archive

    result = {'id': root.name, 'title': root.name, 'workspace': root.name,
              'mode': None, 'created_at': None, 'last_updated': None,
              'dataset': None, 'datasets': [], 'source_format': 'historical_archive',
              'candidate_count': None, 'status': 'error', 'historical_status': None,
              'artifact_integrity': 'not_checked', 'report_html': None,
              'report_markdown': None, 'errors': []}
    try:
        _guard(root, root / 'archive.json')
        archive = read_archive(root)
        result.update(id=archive['id'], title=archive['title'], mode=archive['mode'],
                      created_at=archive['imported_at'], last_updated=archive['imported_at'],
                      status='archived', historical_status=archive['historical_status'],
                      datasets=archive['datasets'], original_source=archive['original_source'])
        if len(archive['datasets']) == 1:
            result['dataset'] = {key: archive['datasets'][0][key] for key in ('id', 'version')}
        if archive.get('report'):
            path = archive['report']
            key = 'report_html' if Path(path).suffix.lower() in {'.htm', '.html'} else 'report_markdown'
            result[key] = (Path(root.name) / path).as_posix()
    except (ValueError, KeyError, TypeError, AttributeError, OSError) as error:
        result['errors'].append(str(error).replace(str(root), '.'))
    return result


def _write_text(path, value):
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _markdown(index):
    def text(value):
        return (html.escape(str(value if value is not None else ''))
                .replace('\\', '\\\\').replace('[', '\\[').replace(']', '\\]')
                .replace('|', '&#124;').replace('\n', ' ').replace('\r', ' '))

    lines = ['# Research index', '', 'Generated: ' + index['generated_at'], '',
             'Rebuildable summary. Artifact integrity is not checked by this index; run study status and the research checks to inspect evidence.', '',
             '| Study | Mode | Dataset | Status | Candidates | Updated | Report |',
             '|---|---|---|---|---|---|---|']
    for row in index['studies']:
        dataset = row.get('dataset') or {}
        reference = '/'.join(str(dataset.get(key) or '') for key in ('id', 'version')) if dataset else row.get('source_format')
        if len(row.get('datasets', [])) > 1:
            reference = ', '.join(item['id'] + '/' + item['version'] for item in row['datasets'])
        study_link = '[' + text(row['title']) + '](' + quote(row['workspace'], safe='') + '/)'
        report = row['report_html'] or row['report_markdown']
        report_link = '[report](' + quote(report, safe='/') + ')' if report else ''
        state = row['status']
        if state == 'archived' and row.get('historical_status'):
            state += ' (' + row['historical_status'] + ')'
        lines.append('| ' + ' | '.join([study_link, text(row['mode']), text(reference), text(state),
                                       text(row['candidate_count']), text(row['last_updated']), report_link]) + ' |')
        if row['errors']:
            lines.append('| ' + text(row['id']) + ' | | | ' + text('; '.join(row['errors'])) + ' | | | |')
    if index['skipped_symlinks']:
        lines.extend(['', 'Symlinks were not followed: ' + ', '.join(text(name) for name in index['skipped_symlinks'])])
    if index.get('factor_library'):
        lines.extend(['', '[Factor library: versions, provenance, validations and rejections]('
                      + quote(index['factor_library']['index_markdown'], safe='/') + ')'])
    return '\n'.join(lines) + '\n'


def refresh(config):
    """Rebuild a portable catalog from study files; never edit research evidence."""
    root = _research_root(config)
    for filename in ('.catalog.lock', 'index.json', 'index.md'):
        if (root / filename).is_symlink():
            raise ValueError('Catalog output must not be a symlink: ' + filename)
    with FileLock(str(root / '.catalog.lock'), timeout=30):
        rows, skipped = [], []
        for child in sorted(root.iterdir()):
            if child.name.startswith('.history-import-'):
                continue
            if child.is_symlink():
                skipped.append(child.name)
                continue
            if child.is_dir():
                if (child / 'archive.json').exists() or (child / 'archive.json').is_symlink():
                    rows.append(_summarize_archive(child))
                elif any((child / name).exists() or (child / name).is_symlink()
                         for name in ('registry.json', 'study.json', 'protocol.json')):
                    rows.append(_summarize(child))
        ids = Counter(row['id'] for row in rows)
        for row in rows:
            if ids[row['id']] > 1:
                row['status'] = 'error'
                row['errors'].append('Duplicate registered study id: ' + row['id'])
        index = {'schema_version': 1, 'generated_at': W.now(), 'studies': rows, 'skipped_symlinks': skipped}
        if config.get('factor_root'):
            index['factor_library'] = {
                'index_json': Path(os.path.relpath(Path(config['factor_root']) / 'index.json', root)).as_posix(),
                'index_markdown': Path(os.path.relpath(Path(config['factor_root']) / 'index.md', root)).as_posix()}
        W.write(root / 'index.json', index)
        _write_text(root / 'index.md', _markdown(index))
    return {'index_json': str(root / 'index.json'), 'index_markdown': str(root / 'index.md'),
            'count': len(rows), 'errors': sum(row['status'] == 'error' for row in rows),
            'skipped_symlinks': skipped, 'entries': rows}
