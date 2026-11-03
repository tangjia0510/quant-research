"""File-based research provenance, immutable candidates and atomic outputs."""
from __future__ import annotations
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import re
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from .defaults import DEFAULT_INITIAL_CASH

SKILL = Path(__file__).resolve().parents[2]
MODES = {'factor', 'model', 'joint', 'report'}


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False, default=str) + '\n'
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def identity(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def inside(root, path):
    root = Path(root).resolve()
    result = (root / path).resolve()
    if not result.is_relative_to(root):
        raise ValueError('Path must stay inside the study workspace: ' + str(path))
    return result


def validate(config):
    if config.get('schema_version', 1) != 1:
        raise ValueError('Unsupported protocol schema_version')
    if config.get('mode') not in MODES:
        raise ValueError('mode must be factor, model, joint or report')
    if config['data'].get('format') not in {'csv', 'parquet', 'qlib'}:
        raise ValueError('data.format must be csv, parquet or qlib')
    spec = config['data']
    if any(key in spec for key in ('dataset_id', 'dataset_version', 'manifest_hash')):
        if not all(isinstance(spec.get(key), str) and spec[key] for key in ('dataset_id', 'dataset_version', 'manifest_hash')):
            raise ValueError('Managed data requires dataset_id, dataset_version and manifest_hash')
        if not re.fullmatch(r'[0-9a-f]{64}', spec['manifest_hash']):
            raise ValueError('Managed data manifest_hash must be SHA256')
        if any(key in spec for key in ('path', 'universe', 'calendar')):
            raise ValueError('Managed data uses registered paths; omit path, universe and calendar')
    previous = None
    for key in ('train', 'valid', 'discovery', 'final'):
        interval = config['splits'][key]
        if len(interval) != 2:
            raise ValueError('Every split requires [start,end]')
        start, end = map(date.fromisoformat, interval)
        if start > end or (previous is not None and start <= previous):
            raise ValueError('Splits must be ordered, disjoint and nonempty')
        previous = end
    label = config.setdefault('label', {})
    label.setdefault('price', 'open')
    label.setdefault('entry_lag', 1)
    label.setdefault('horizon', 5)
    if label['price'] not in ('open', 'close') or any(type(label[k]) is not int or label[k] < 1 for k in ('entry_lag', 'horizon')):
        raise ValueError('Label needs open/close price and positive entry_lag/horizon')
    portfolio = config.setdefault('portfolio', {})
    for key, val in dict(top_k=10, rebalance=5, initial_cash=DEFAULT_INITIAL_CASH, position=.95,
                         buy_cost=.0005, sell_cost=.0015, min_cost=0, trade_unit=100).items():
        portfolio.setdefault(key, val)
    if not 0 < portfolio['position'] <= 1 or portfolio['top_k'] < 1 or portfolio['rebalance'] < 1:
        raise ValueError('Invalid portfolio position, top_k or rebalance')
    if any(type(portfolio[k]) is not int or portfolio[k] < 1 for k in ('top_k', 'rebalance', 'trade_unit')):
        raise ValueError('Portfolio counts must be positive integers')
    if any(not isinstance(portfolio[k], (int, float)) or not math.isfinite(portfolio[k]) for k in portfolio):
        # String execution settings are validated separately below.
        for key in ('initial_cash', 'position', 'buy_cost', 'sell_cost', 'min_cost'):
            if not isinstance(portfolio[key], (int, float)) or not math.isfinite(portfolio[key]):
                raise ValueError('Non-finite portfolio parameter: ' + key)
    if any(portfolio[k] < 0 for k in ('buy_cost', 'sell_cost', 'min_cost')) or portfolio['initial_cash'] <= 0:
        raise ValueError('Costs must be nonnegative and cash positive')
    budget = config.setdefault('budget', {})
    for key, val in dict(max_trials=6, max_repairs=2, timeout_seconds=600).items():
        budget.setdefault(key, val)
        if not isinstance(budget[key], int) or budget[key] < (0 if key == 'max_repairs' else 1):
            raise ValueError('Invalid budget ' + key)
    config.setdefault('model', {'kind': 'ridge', 'params': {'alpha': 1.0}})
    return config


def initialize(root, protocol, mode=None, *, data_override=None):
    root = Path(root).resolve()
    if root.exists() and any(root.iterdir()):
        raise ValueError('init requires a new or empty workspace; existing research is preserved')
    config = read(protocol)
    if mode:
        config['mode'] = mode
    if data_override is not None:
        config['data'] = data_override
    config = validate(config)
    for key in ('path', 'universe', 'calendar'):
        if config['data'].get(key):
            config['data'][key] = str((Path(protocol).resolve().parent / config['data'][key]).resolve())
    root.mkdir(parents=True, exist_ok=True)
    write(root / 'protocol.json', config)
    write(root / 'study.json', {'schema_version': 1, 'created_at': now(),
          'protocol_hash': digest(root / 'protocol.json'), 'mode': config['mode'],
          'final_exposed': False, 'scope': 'historical_research'})
    return {'workspace': str(root), 'mode': config['mode']}


def load(root):
    root = Path(root).resolve()
    study = read(root / 'study.json')
    if study['protocol_hash'] != digest(root / 'protocol.json'):
        raise ValueError('Frozen protocol changed; create a new study to change research settings')
    return validate(read(root / 'protocol.json'))


def event(root, action, **details):
    path = Path(root) / 'events.jsonl'
    with path.open('a', encoding='utf-8') as stream:
        stream.write(json.dumps({'at': now(), 'action': action, **details}, ensure_ascii=False, default=str) + '\n')


def _registered_factor_snapshots(root, name, references, library_config_path, existing):
    """Bind exact library versions once; subsequent runs use only frozen local bytes."""
    if not isinstance(references, list) or not references or len(references) > 32:
        raise ValueError('factor_refs must contain 1 to 32 exact id/version references')
    normalized = []
    for reference in references:
        if (not isinstance(reference, dict) or set(reference) - {'id', 'version', 'params'}
                or not all(isinstance(reference.get(k), str) and reference[k] for k in ('id', 'version'))
                or not isinstance(reference.get('params', {}), dict)):
            raise ValueError('factor_refs entries require id, version and optional params object')
        normalized.append({'id': reference['id'], 'version': reference['version'],
                           'params': reference.get('params', {})})
    if len({r['id'] for r in normalized}) != len(normalized):
        raise ValueError('A candidate cannot repeat a factor id')
    if existing and existing.get('factor_refs') == normalized:
        copies = {filename: inside(root / 'candidates' / name, filename).read_bytes()
                  for filename in existing['files'] if filename.startswith(('factors/', 'factor-validations/'))}
        return normalized, existing['registered_factors'], copies
    from . import library, factor_registry
    configuration = library.load_config(library_config_path)
    snapshots, copies = [], {}
    for reference in normalized:
        resolved = factor_registry.resolve(configuration, reference['id'], reference['version'])
        definition = resolved['definition']
        if reference['params'] != definition.get('parameters', {}):
            raise ValueError('Registered factor parameters are versioned; register a new version to change parameters')
        folder = Path(resolved['folder'])
        manifest = read(folder / 'manifest.json')
        prefix = f"factors/{reference['id']}/{reference['version']}"
        # Registry resolution verifies the complete manifest before snapshotting.
        for filename in [*manifest['files'], 'manifest.json']:
            content = inside(folder, filename).read_bytes()
            expected = resolved['manifest_hash'] if filename == 'manifest.json' else manifest['files'][filename]
            if hashlib.sha256(content).hexdigest() != expected:
                raise ValueError('Registered factor changed during snapshot copy')
            copies[f'{prefix}/{filename}'] = content
        validation = resolved.get('validation', {})
        receipt_path = None
        if validation.get('receipt'):
            content = inside(Path(configuration['factor_root']), validation['receipt']).read_bytes()
            if hashlib.sha256(content).hexdigest() != validation['receipt_sha256']:
                raise ValueError('Factor validation receipt changed during snapshot copy')
            receipt_relative = f"factor-validations/{reference['id']}/{reference['version']}.json"
            receipt_path = f'candidates/{name}/{receipt_relative}'
            copies[receipt_relative] = content
        snapshots.append({'id': reference['id'], 'version': reference['version'],
                          'factor_file': f'candidates/{name}/{prefix}/factor.py',
                          'manifest_hash': resolved['manifest_hash'], 'params': reference['params'],
                          'max_lookback': definition['max_lookback'],
                          'scale_invariant': definition['scale_invariant'],
                          'output_columns': definition['output_columns'],
                          'limitations': definition.get('limitations', []),
                          'source': definition.get('source', {}),
                          'library_validation': validation, 'validation_receipt': receipt_path})
    return normalized, snapshots, copies


def register(root, candidate_path, *, library_config_path=None):
    root = Path(root)
    config = load(root)
    candidate = read(candidate_path)
    name = candidate.get('id', '')
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}', name):
        raise ValueError('Candidate id must be a short alphanumeric name')
    if candidate.get('kind') != config['mode']:
        raise ValueError('Candidate kind must match study mode')
    if not candidate.get('hypothesis'):
        raise ValueError('A testable hypothesis is required')
    if 'registered_factors' in candidate:
        raise ValueError('registered_factors is generated from factor_refs; it cannot be supplied by a candidate')
    if candidate['kind'] in {'factor', 'joint', 'report'} and not (candidate.get('factor_file') or candidate.get('factor_refs')):
        raise ValueError('This mode requires factor_file or factor_refs')
    if candidate['kind'] in {'model', 'joint'} and not candidate.get('model'):
        raise ValueError('This mode requires a model specification')
    copies = {}
    folder = root / 'candidates' / name
    existing = verify_candidate(root, name) if (folder / 'candidate.json').exists() else None
    if 'factor_refs' in candidate:
        references, snapshots, registered_copies = _registered_factor_snapshots(
            root, name, candidate['factor_refs'], library_config_path, existing)
        candidate['factor_refs'] = references
        candidate['registered_factors'] = snapshots
        copies.update(registered_copies)
    for obj, key, dest in [(candidate, 'factor_file', 'factor.py'),
                           (candidate.setdefault('model', config['model'].copy()), 'file', 'model.py')]:
        if obj.get(key):
            source = inside(root, obj[key])
            copies[dest] = source.read_bytes()
            obj[key] = f'candidates/{name}/{dest}'
    if candidate['kind'] == 'report':
        source = candidate.get('source', {})
        if not isinstance(source, dict) or not all(source.get(k) for k in ('path', 'locator', 'formula')):
            raise ValueError('Report candidate requires source.path, locator and formula')
        p = inside(root, source['path'])
        dest = 'source' + p.suffix.lower()
        copies[dest] = p.read_bytes()
        source['path'] = f'candidates/{name}/{dest}'
    file_hashes = {p: hashlib.sha256(b).hexdigest() for p, b in copies.items()}
    candidate['files'] = file_hashes
    candidate.pop('candidate_hash', None)
    candidate['candidate_hash'] = identity(candidate)
    if (folder / 'candidate.json').exists():
        if read(folder / 'candidate.json')['candidate_hash'] != candidate['candidate_hash']:
            raise ValueError('Candidate id is immutable; assign a new id to revised code or parameters')
        return verify_candidate(root, name)
    if (root / 'freeze.json').exists():
        raise ValueError('Study is frozen; new candidates require a new study')
    count = len(list((root / 'candidates').glob('*/candidate.json')))
    if count >= config['budget']['max_trials']:
        raise ValueError('Candidate budget exhausted')
    folder.mkdir(parents=True)
    for name_, content in copies.items():
        destination = folder / name_
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
    write(folder / 'candidate.json', candidate)
    event(root, 'candidate_registered', candidate=name, candidate_hash=candidate['candidate_hash'])
    return candidate


def verify_candidate(root, name):
    folder = inside(root, 'candidates/' + name)
    c = read(folder / 'candidate.json')
    expected = c['candidate_hash']
    if identity({k: v for k, v in c.items() if k != 'candidate_hash'}) != expected:
        raise ValueError('Candidate metadata changed after registration')
    for filename, value in c['files'].items():
        if digest(inside(folder, filename)) != value:
            raise ValueError('Candidate code/source changed after registration')
    return c


def snapshot(root):
    paths = sorted(p for p in (Path(root) / 'data').rglob('*') if p.is_file())
    if not paths:
        raise ValueError('Run prepare before evaluation')
    return {str(p.relative_to(root)): digest(p) for p in paths}


def fingerprint(root, candidate, phase):
    versions = {}
    for name in ('pyqlib', 'numpy', 'pandas', 'pyarrow', 'scipy', 'statsmodels', 'scikit-learn', 'lightgbm', 'xgboost', 'torch'):
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            pass
    runtime = {str(p.relative_to(SKILL)): digest(p) for p in sorted((SKILL / 'scripts').rglob('*.py'))}
    versions['python'] = platform.python_version()
    versions['platform'] = platform.platform()
    versions['machine'] = platform.machine()
    return identity({'protocol': digest(Path(root) / 'protocol.json'), 'candidate': candidate['candidate_hash'],
                     'data': snapshot(root), 'phase': phase, 'runtime': runtime, 'versions': versions,
                     'worker_threads': int(os.environ.get('QUANT_WORKER_THREADS', '4'))})
