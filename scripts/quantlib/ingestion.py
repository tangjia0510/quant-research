"""Auditable acquisition batches, strict daily-bar validation and warehouse publication.

Adapters own vendor conventions. This module owns request identity, raw evidence,
exchange-date bounds, resumability and the gate before immutable registration.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from contextlib import contextmanager
import copy
import inspect
from pathlib import Path
import sys
import uuid
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from . import data as D
from . import library as L
from . import workspace as W

DEFAULT_START = '2019-01-01'
MAX_TRAILING_SOURCE_LAG = 3


def _date(value, label):
    try:
        result = date.fromisoformat(str(value))
    except (ValueError, TypeError) as error:
        raise ValueError(label + ' must be an ISO YYYY-MM-DD date') from error
    if result.isoformat() != str(value):
        raise ValueError(label + ' must be an ISO YYYY-MM-DD date')
    return result


def completed_date_bound(now=None):
    """Conservative China daily-source cutoff; a calendar still determines sessions."""
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError('Acquisition clock must include a timezone')
    local = current.astimezone(ZoneInfo('Asia/Shanghai'))
    return (local.date() if local.time() >= time(20) else local.date() - timedelta(days=1)).isoformat()


def _instrument(value):
    """Preserve canonical case while enforcing portable, collision-free names."""
    if not isinstance(value, str):
        raise ValueError('Source instrument must be a string')
    L.safe_name(value.lower(), 'Source instrument')
    return value


def validate_input(bars, calendar, universe, metadata, start=None, end=None):
    """Return a measurable quality receipt; any invalid/incomplete input raises.

Completeness applies to every declared security-life interval, not just dates
present in the source. Explicit suspended rows are represented as four NaN price
fields and zero volume. They are counted separately from absent observations.
"""
    frame = D.normalize(bars)
    if not isinstance(metadata, dict):
        raise ValueError('Source metadata must be an object')
    if metadata.get('frequency') not in ('day', 'daily'):
        raise ValueError('Source must explicitly declare daily frequency (day or daily)')
    if type(metadata.get('synthetic')) is not bool:
        raise ValueError('Source must explicitly declare boolean synthetic metadata')
    if metadata.get('price_basis') not in {'raw', 'adjusted'}:
        raise ValueError('Source must declare raw or adjusted price_basis')
    if metadata.get('volume_unit') not in {'shares', 'units'}:
        raise ValueError('Source must declare shares or units volume_unit')
    for key in ('region', 'currency', 'volume_basis'):
        if not isinstance(metadata.get(key), str) or not metadata[key]:
            raise ValueError('Source must declare ' + key)
    if metadata['price_basis'] == 'adjusted':
        if not metadata.get('adjustment_identity') or 'factor' not in frame:
            raise ValueError('Adjusted prices require adjustment_identity and factor')
        if frame.factor.isna().any():
            raise ValueError('Adjusted price factor cannot be missing')
    elif 'factor' in frame and not frame.factor.eq(1.0).all():
        raise ValueError('Raw prices require factor=1 on every row when supplied')
    if frame.volume.isna().any():
        raise ValueError('Volume cannot be missing in acquired rows')
    prices = frame[['open', 'high', 'low', 'close']]
    missing = prices.isna().sum(axis=1)
    if (~missing.isin([0, 4])).any():
        raise ValueError('Partially missing OHLC is not a valid suspension record')
    suspended = missing.eq(4)
    if (frame.loc[suspended, 'volume'] != 0).any():
        raise ValueError('Missing OHLC requires an explicit zero-volume non-trading row')
    if not (~suspended).any():
        raise ValueError('No tradable prices were acquired')

    dates = pd.DatetimeIndex(pd.to_datetime(list(calendar), errors='raise'))
    if (dates.empty or dates.hasnans or dates.has_duplicates or not dates.is_monotonic_increasing
            or dates.tz is not None or not dates.equals(dates.normalize())):
        raise ValueError('Calendar must contain ordered unique exchange-local daily dates')
    if start is not None:
        lower = pd.Timestamp(_date(start, 'start'))
        dates = dates[dates >= lower]
    if end is not None:
        upper = pd.Timestamp(_date(end, 'end'))
        dates = dates[dates <= upper]
    if dates.empty:
        raise ValueError('No exchange sessions in requested interval')
    observed_dates = frame.index.get_level_values('datetime')
    if not observed_dates.isin(dates).all():
        raise ValueError('Market rows fall outside the requested trading calendar')

    if not isinstance(universe, pd.DataFrame) or not {'instrument', 'start', 'end'}.issubset(universe):
        raise ValueError('Universe requires instrument,start,end columns')
    intervals = universe[['instrument', 'start', 'end']].copy()
    if intervals.empty or intervals.isna().any().any():
        raise ValueError('Universe intervals cannot be empty or null')
    intervals['instrument'] = intervals.instrument.astype(str)
    for key in ('start', 'end'):
        intervals[key] = pd.to_datetime(intervals[key], errors='raise')
        if intervals[key].dt.tz is not None or not intervals[key].eq(intervals[key].dt.normalize()).all():
            raise ValueError('Universe endpoints must be daily dates')
    if (intervals.start > intervals.end).any():
        raise ValueError('Invalid universe life interval')
    actual_symbols = set(frame.index.get_level_values('instrument'))
    if not actual_symbols.issubset(set(intervals.instrument)):
        raise ValueError('Bars contain a security outside the declared universe')
    coverage = []
    gap_examples = []
    total_expected = 0
    for instrument, spans in intervals.groupby('instrument', sort=True):
        eligible = np.zeros(len(dates), dtype=bool)
        for row in spans.itertuples():
            eligible |= (dates >= row.start) & (dates <= row.end)
        expected = dates[eligible]
        observed = (frame.xs(instrument, level='instrument').index
                    if instrument in actual_symbols else pd.DatetimeIndex([]))
        absent = expected.difference(observed)
        unexpected = observed.difference(expected)
        total_expected += len(expected)
        coverage.append({'instrument': instrument, 'expected_rows': len(expected),
                         'observed_rows': len(observed), 'missing_rows': len(absent),
                         'outside_lifetime_rows': len(unexpected)})
        if len(absent) or len(unexpected):
            gap_examples.append({'instrument': instrument,
                                 'missing': absent.strftime('%Y-%m-%d').tolist()[:5],
                                 'outside_lifetime': unexpected.strftime('%Y-%m-%d').tolist()[:5]})
    if gap_examples:
        raise ValueError('Incomplete security/calendar coverage: ' + str(gap_examples[:5]))
    return {'schema_version': 1, 'status': 'passed', 'rows': len(frame),
            'instruments': len(actual_symbols), 'first_date': observed_dates.min().date().isoformat(),
            'last_date': observed_dates.max().date().isoformat(), 'calendar_sessions': len(dates),
            'expected_rows': total_expected, 'missing_calendar_rows': 0,
            'non_trading_rows': int(suspended.sum()), 'tradable_rows': int((~suspended).sum()),
            'duplicate_rows': 0, 'infinite_values': 0, 'coverage': coverage,
            'limitations': list(metadata.get('limitations', []))}


def _sources_root(config):
    # load_config supplies this key; fallback also accommodates older API callers.
    return Path(config.get('sources_root', Path(config['config_path']).parent / 'sources')).resolve()


def _batch_folder(config, batch):
    root = _sources_root(config)
    given = Path(batch).expanduser()
    candidate = given if given.is_absolute() else root / given
    if not candidate.resolve().is_relative_to(root) or candidate.resolve() == root:
        raise ValueError('Acquisition batch must stay inside sources_root')
    relative = candidate.relative_to(root) if candidate.is_absolute() else candidate
    check = root
    for part in relative.parts:
        check = check / part
        if check.is_symlink():
            raise ValueError('Acquisition batch cannot contain symlinks')
    return candidate.resolve()


def _verify_hashes(folder, hashes):
    if not isinstance(hashes, dict) or not hashes:
        raise ValueError('Acquisition evidence has no payload hashes')
    for relative, digest in hashes.items():
        candidate = Path(folder) / relative
        if any(p.is_symlink() for p in (candidate, *candidate.parents) if p.is_relative_to(folder)):
            raise ValueError('Acquisition evidence cannot contain symlinks: ' + relative)
        path = W.inside(folder, relative)
        if path.is_symlink() or not path.is_file() or W.digest(path) != digest:
            raise ValueError('Acquisition evidence changed: ' + relative)


def batch_status(config, batch):
    folder = _batch_folder(config, batch)
    request = W.read(folder / 'request.json')
    state = W.read(folder / 'status.json')
    if W.identity(request) != state.get('request_hash'):
        raise ValueError('Acquisition request identity changed')
    if state.get('status') == 'complete':
        manifest = W.read(folder / 'manifest.json')
        if W.digest(folder / 'manifest.json') != state.get('manifest_hash'):
            raise ValueError('Acquisition manifest changed')
        _verify_hashes(folder, manifest['files'])
        actual = {p.relative_to(folder).as_posix() for p in folder.rglob('*')
                  if p.is_file() and p.name not in {'manifest.json', 'status.json', '.batch.lock'}}
        if actual != set(manifest['files']):
            raise ValueError('Acquisition batch has unexpected or missing evidence files')
        ref = state['dataset']
        L.dataset_resolve(config, ref['dataset_id'], ref['version'], ref['manifest_hash'])
    return {'batch': folder.relative_to(_sources_root(config)).as_posix(),
            'batch_path': str(folder), 'request': request, **state}


def _frames(folder, key, identity, fetch):
    """Cache only complete successful raw responses; retain every failed attempt."""
    root = folder / 'raw' / key
    receipt_path = root / 'receipt.json'
    if receipt_path.exists():
        receipt = W.read(receipt_path)
        if receipt.get('identity') != identity:
            raise ValueError('Cached request/source identity differs: ' + key)
        _verify_hashes(root, receipt['files'])
        return {name: pd.read_parquet(W.inside(root, relative)) for name, relative in receipt['frames'].items()}
    root.mkdir(parents=True, exist_ok=True)
    attempt = root / ('attempt-' + str(1 + len(list(root.glob('attempt-*')))))
    attempt.mkdir()
    W.write(attempt / 'request.json', {'identity': identity, 'started_at': W.now()})
    try:
        payload = fetch()
        if isinstance(payload, pd.DataFrame):
            payload = {'response': payload}
        if not isinstance(payload, dict) or not payload:
            raise ValueError('Source response must contain DataFrames')
        files, frames = {}, {}
        for name, frame in payload.items():
            L.safe_name(name, 'Source response name')
            if not isinstance(frame, pd.DataFrame):
                raise ValueError('Source response is not a DataFrame: ' + name)
            path = attempt / (name + '.parquet')
            frame.to_parquet(path, index=False)
            relative = path.relative_to(root).as_posix()
            frames[name] = relative
            files[relative] = W.digest(path)
        W.write(receipt_path, {'identity': identity, 'frames': frames, 'files': files,
                               'completed_at': W.now()})
        return payload
    except BaseException as error:
        W.write(attempt / 'failure.json', {'failed_at': W.now(), 'type': type(error).__name__,
                                         'message': str(error)})
        raise


def _implementation(adapter):
    source_file = inspect.getsourcefile(type(adapter))
    if source_file is None or not Path(source_file).is_file():
        raise ValueError('Source adapter must have an inspectable implementation file')
    # Logical labels and hashes migrate; machine-specific module paths do not.
    return {'ingestion_sha256': W.digest(__file__), 'adapter_sha256': W.digest(source_file)}


def _source_identity(request, metadata, implementation):
    return W.identity({'request': request, 'adapter': metadata, 'implementation': implementation})


@contextmanager
def _acquisition_locks(base, source, folder):
    from filelock import FileLock

    try:
        # SDK locks only coordinate one process; each library also serializes
        # requests to a provider across CLI processes, including retry delays.
        with FileLock(str(base / source / '.source.lock'), timeout=0), FileLock(str(folder / '.batch.lock'), timeout=0):
            yield
    except BaseException as error:
        error.acquisition_batch = folder.relative_to(base).as_posix()
        error.acquisition_batch_path = str(folder)
        raise


def ingest(config, source, dataset_id, version, start=DEFAULT_START, end=None,
           instruments=None, options=None, resume=None, now=None):
    """Download, normalize, strictly validate, then publish one immutable version.

No arguments imply all securities returned by the adapter's historical basics,
not today's index constituents. Explicit instruments are an intentionally scoped
sample. Resume pins the original clock cutoff as well as the request and adapter.
"""
    from .sources import get_source

    L.safe_name(source, 'Source name')
    L.safe_name(dataset_id)
    L.safe_name(version, 'Dataset version')
    start = _date(start, 'start').isoformat()
    if end is not None:
        end = _date(end, 'end').isoformat()
        if end < start:
            raise ValueError('Data end precedes start')
    selected = None if instruments is None else sorted(set(instruments))
    if selected is not None:
        if not selected:
            raise ValueError('Explicit instruments cannot be empty')
        for instrument in selected:
            _instrument(instrument)
        if len({instrument.lower() for instrument in selected}) != len(selected):
            raise ValueError('Source instrument identifiers collide after case normalization')
    options = options or {}
    # Credentials for future providers belong in their environment, not receipts.
    if not isinstance(options, dict) or set(options) - {'retries', 'timeout', 'delay'}:
        raise ValueError('Source options support only retries, timeout and delay')
    request = {'schema_version': 1, 'source': source, 'dataset_id': dataset_id, 'version': version,
               'start': start, 'end': end, 'instruments': selected, 'options': options}
    base = _sources_root(config)
    if resume is not None:
        folder = _batch_folder(config, resume)
        previous = batch_status(config, resume)
        if previous['request'] != request:
            raise ValueError('Resume requires the identical acquisition request')
        if previous['status'] == 'complete':
            return previous
        cutoff = previous['completed_date_bound']
    else:
        if L._dataset_folder(config, dataset_id, version).exists():
            raise ValueError('Dataset version already exists; use a new version instead of overwriting')
        cutoff = completed_date_bound(now)
        if end is not None and end > cutoff:
            raise ValueError('Requested end exceeds the completed exchange-date bound ' + cutoff)
        if start > cutoff:
            raise ValueError('Requested start is after the completed exchange-date bound')
        prefix = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%SZ').lower()
        folder = base / source / (prefix + '-' + uuid.uuid4().hex[:8])
        if (base / source).is_symlink():
            raise ValueError('Source acquisition folder cannot be a symlink')
        folder.mkdir(parents=True)
        W.write(folder / 'request.json', request)
        W.write(folder / 'status.json', {'status': 'created', 'request_hash': W.identity(request),
                                        'completed_date_bound': cutoff, 'created_at': W.now(),
                                        'attempt': 0})
    target_end = end or cutoff
    with _acquisition_locks(base, source, folder):
        state = W.read(folder / 'status.json')
        state.update(status='running', attempt=state['attempt'] + 1, started_at=W.now())
        state.pop('error', None)
        W.write(folder / 'status.json', state)
        try:
            with get_source(source, **options) as adapter:
                metadata = copy.deepcopy(adapter.metadata)
                if type(metadata.get('synthetic')) is not bool:
                    raise ValueError('Source adapter must explicitly declare synthetic true or false')
                implementation = _implementation(adapter)
                adapter_identity = _source_identity(request, metadata, implementation)
                adapter_file = folder / 'adapter.json'
                adapter_receipt = {'metadata': metadata, 'implementation': implementation}
                if adapter_file.exists() and W.read(adapter_file) != adapter_receipt:
                    raise ValueError('Source adapter changed; use a new acquisition batch')
                if not adapter_file.exists():
                    W.write(adapter_file, adapter_receipt)
                raw_calendar = _frames(folder, 'calendar', adapter_identity,
                                       lambda: adapter.fetch_calendar(start, target_end))['response']
                calendar = adapter.normalize_calendar(raw_calendar)
                calendar = pd.DatetimeIndex(pd.to_datetime(calendar, errors='raise'))
                if (calendar.empty or calendar.hasnans or calendar.has_duplicates
                        or not calendar.is_monotonic_increasing or calendar.tz is not None
                        or not calendar.equals(calendar.normalize())):
                    raise ValueError('Source returned an invalid trading calendar')
                if calendar.min() < pd.Timestamp(start) or calendar.max() > pd.Timestamp(target_end):
                    raise ValueError('Source calendar exceeds requested date bounds')
                expected_end = calendar.max().date().isoformat()
                raw_basic = _frames(folder, 'instruments', adapter_identity,
                                    adapter.fetch_instruments)['response']
                universe = adapter.normalize_instruments(raw_basic, start, expected_end)
                if not isinstance(universe, pd.DataFrame) or not {'instrument', 'start', 'end'}.issubset(universe):
                    raise ValueError('Source instrument normalization lacks lifetime intervals')
                if selected is not None:
                    absent = set(selected) - set(universe.instrument)
                    if absent:
                        raise ValueError('Requested instruments absent from source/lifetime: ' + str(sorted(absent)))
                    universe = universe[universe.instrument.isin(selected)].copy()
                if universe.empty or universe.instrument.duplicated().any():
                    raise ValueError('Source must return nonempty unique security lifetimes')
                if universe.instrument.map(_instrument).str.lower().duplicated().any():
                    raise ValueError('Source instrument identifiers collide after case normalization')
                frames = []
                conversion_counts = {}
                total = len(universe)
                for i, row in enumerate(universe.sort_values('instrument').itertuples(), 1):
                    instrument = row.instrument
                    _instrument(instrument)
                    first = max(start, _date(row.start, 'Instrument start').isoformat())
                    last = min(expected_end, _date(row.end, 'Instrument end').isoformat())
                    identity = W.identity({'adapter': adapter_identity, 'instrument': instrument,
                                           'start': first, 'end': last})
                    payload = _frames(folder, 'bars/' + instrument, identity,
                                      lambda: adapter.fetch_bars(instrument, first, last))
                    converted = adapter.normalize_bars(payload)
                    counts = converted.attrs.get('source_conversion_counts', {})
                    if not isinstance(counts, dict) or any(not isinstance(key, str) or type(value) is not int
                                                           or value < 0 for key, value in counts.items()):
                        raise ValueError('Source conversion counts must be nonnegative integer counters')
                    for key, count in counts.items():
                        conversion_counts[key] = conversion_counts.get(key, 0) + count
                    normalized = D.normalize(converted)
                    if set(normalized.index.get_level_values('instrument')) != {instrument}:
                        raise ValueError('Source returned a different instrument: ' + instrument)
                    frames.append(normalized)
                    state.update(completed_instruments=i, requested_instruments=total)
                    W.write(folder / 'status.json', state)
                    if i == 1 or i == total or i % 25 == 0:
                        print(f'Acquisition {source}: {i}/{total} securities downloaded', file=sys.stderr, flush=True)
            bars = pd.concat(frames).sort_index()
            observed_end = bars.index.get_level_values('datetime').max()
            missing_tail = calendar[calendar > observed_end]
            if len(missing_tail):
                if end is not None or len(missing_tail) > MAX_TRAILING_SOURCE_LAG:
                    raise ValueError('Source does not cover the requested latest exchange sessions: ' +
                                     ','.join(missing_tail.strftime('%Y-%m-%d')))
                calendar = calendar[calendar <= observed_end]
                metadata.setdefault('limitations', []).append(
                    'Source had no observations for trailing exchange sessions: ' +
                    ','.join(missing_tail.strftime('%Y-%m-%d')))
            resolved_end = calendar.max().date().isoformat()
            universe = universe.copy()
            universe['end'] = universe['end'].map(lambda value: min(str(value), resolved_end))
            universe = universe[universe.start.astype(str) <= universe.end.astype(str)]
            metadata.update(source=source,
                            universe_basis='explicit_security_sample' if selected is not None else 'source_security_lifetimes',
                            acquisition_start=start, acquisition_end=resolved_end)
            metadata.setdefault('limitations', []).append(
                'Security lifetimes are source-reported; they are not historical index membership or independently certified point-in-time availability')
            if selected is not None:
                metadata['limitations'].append('Explicit security sample; not a full-market or historical-index dataset')
            if metadata['synthetic']:
                metadata['limitations'].append('Source declares synthetic data; these are not real market observations')
            quality = validate_input(bars, calendar, universe, metadata, start, resolved_end)
            quality.update(requested_end=end, completed_date_bound=cutoff,
                           calendar_latest_session=expected_end, source_latest_session=resolved_end,
                           unavailable_trailing_sessions=missing_tail.strftime('%Y-%m-%d').tolist(),
                           source_conversion_counts=conversion_counts)
            normalized_root = folder / 'normalized'
            normalized_root.mkdir(exist_ok=True)
            bars.to_parquet(normalized_root / 'data.parquet')
            universe.to_csv(normalized_root / 'universe.csv', index=False)
            (normalized_root / 'calendar.txt').write_text('\n'.join(calendar.strftime('%Y-%m-%d')) + '\n')
            W.write(folder / 'quality.json', quality)
            raw_hashes = {p.relative_to(folder).as_posix(): W.digest(p)
                          for p in sorted((folder / 'raw').rglob('*')) if p.is_file()}
            batch_ref = folder.relative_to(base).as_posix()
            acquisition = {'schema_version': 1, 'source': source, 'batch': batch_ref,
                           'request': request, 'request_hash': W.identity(request),
                           'adapter': metadata, 'implementation': implementation, 'raw_files': raw_hashes,
                           'quality': quality, 'captured_at': state['created_at']}
            W.write(folder / 'acquisition.json', acquisition)
            metadata['acquisition'] = {'batch': batch_ref, 'evidence': 'acquisition.json',
                                       'raw_files_hash': W.identity(raw_hashes)}
            registered_folder = L._dataset_folder(config, dataset_id, version)
            if registered_folder.exists():
                # Recover a process exit between atomic publication and its final
                # batch receipt. Never adopt a version published by another batch.
                dataset = L.dataset_resolve(config, dataset_id, version)
                if (dataset['metadata'].get('acquisition', {}).get('batch') != batch_ref
                        or W.digest(dataset['path']) != W.digest(normalized_root / 'data.parquet')
                        or W.digest(dataset['universe']) != W.digest(normalized_root / 'universe.csv')
                        or W.digest(dataset['calendar']) != W.digest(normalized_root / 'calendar.txt')
                        or any(W.digest(registered_folder / name) != W.digest(folder / name)
                               for name in ('quality.json', 'acquisition.json'))):
                    raise ValueError('Existing dataset does not match this acquisition batch')
            else:
                dataset = L.dataset_add(config, dataset_id, version, normalized_root / 'data.parquet', 'parquet',
                                        universe=normalized_root / 'universe.csv', calendar=normalized_root / 'calendar.txt',
                                        metadata=metadata, evidence={'acquisition.json': folder / 'acquisition.json',
                                                                     'quality.json': folder / 'quality.json'})
            files = {p.relative_to(folder).as_posix(): W.digest(p) for p in sorted(folder.rglob('*'))
                     if p.is_file() and p.name not in {'manifest.json', 'status.json', '.batch.lock'}}
            W.write(folder / 'manifest.json', {'schema_version': 1, 'batch': batch_ref, 'files': files})
            state.update(status='complete', completed_at=W.now(),
                         manifest_hash=W.digest(folder / 'manifest.json'),
                         dataset={key: dataset[key] for key in ('dataset_id', 'version', 'manifest_hash')},
                         quality=quality)
            W.write(folder / 'status.json', state)
            return batch_status(config, batch_ref)
        except BaseException as error:
            state.update(status='failed', completed_at=W.now(),
                         error={'type': type(error).__name__, 'message': str(error)})
            W.write(folder / 'status.json', state)
            raise
