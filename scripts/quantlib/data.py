"""Versioned local input data and a Qlib-compatible daily provider."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

REQUIRED = ('open', 'high', 'low', 'close', 'volume')
INDEX = ['datetime', 'instrument']
BENCHMARK = 'QRBENCH'


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def _json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    os.replace(temporary, path)


def normalize(frame, column_map=None):
    """Canonicalize names without filling prices or manufacturing observations."""
    frame = frame.copy()
    if isinstance(frame.index, pd.MultiIndex) or frame.index.name:
        frame = frame.reset_index()
    frame = frame.rename(columns=column_map or {})
    frame = frame.rename(columns={c: c.removeprefix('$') for c in frame if isinstance(c, str)})
    if 'datetime' not in frame and 'date' in frame:
        frame = frame.rename(columns={'date': 'datetime'})
    if 'instrument' not in frame and 'symbol' in frame:
        frame = frame.rename(columns={'symbol': 'instrument'})
    missing = set(INDEX + list(REQUIRED)) - set(frame.columns)
    if missing:
        raise ValueError(f'Data missing columns: {sorted(missing)}')
    if frame['instrument'].isna().any():
        raise ValueError('Missing instrument identifier')
    frame['instrument'] = frame.instrument.astype(str)
    if frame.instrument.str.contains(r'[^A-Za-z0-9_.-]', regex=True).any():
        raise ValueError('Instrument identifiers must be safe letters, numbers, dot, underscore or hyphen')
    if frame.instrument.str.lower().isin(['qrbench', '.', '..']).any():
        raise ValueError('Reserved instrument identifier')
    symbols = frame.instrument.unique()
    if len({s.lower() for s in symbols}) != len(symbols):
        raise ValueError('Instrument identifiers collide after case normalization')
    frame['datetime'] = pd.to_datetime(frame.datetime, errors='raise')
    if frame.datetime.isna().any() or frame.datetime.dt.tz is not None:
        raise ValueError('Dates must be non-null exchange-local dates without timezone suffixes')
    if not frame.datetime.eq(frame.datetime.dt.normalize()).all():
        raise ValueError('Only daily midnight observations are supported')
    frame = frame.set_index(INDEX).sort_index()
    if not frame.index.is_unique:
        raise ValueError('Duplicate datetime/instrument observations')
    if frame.empty:
        raise ValueError('Empty dataset')
    columns = list(REQUIRED) + (['factor'] if 'factor' in frame else [])
    frame = frame[columns].apply(pd.to_numeric, errors='raise').astype('float64')
    if np.isinf(frame.to_numpy()).any():
        raise ValueError('Infinite price or volume')
    for column in ('open', 'high', 'low', 'close', 'factor'):
        if column in frame and (frame[column].dropna() <= 0).any():
            raise ValueError(f'{column} must be positive when present')
    if (frame.volume.dropna() < 0).any():
        raise ValueError('Volume must be nonnegative')
    good = frame[['open', 'high', 'low', 'close']].dropna()
    if ((good.high < good[['open', 'low', 'close']].max(axis=1)) |
            (good.low > good[['open', 'high', 'close']].min(axis=1))).any():
        raise ValueError('OHLC bounds are inconsistent')
    return frame


def _source_path(workspace, value):
    p = Path(value).expanduser()
    return p.resolve() if p.is_absolute() else (Path(workspace) / p).resolve()


def _read_qlib(path, spec, config):
    import qlib
    from qlib.data import D
    qlib.init(provider_uri=str(path), region=spec.get('region', 'cn'), kernels=1,
              expression_cache=None, dataset_cache=None)
    instruments = spec.get('instruments', 'all')
    if isinstance(instruments, str):
        membership = D.list_instruments(D.instruments(instruments), as_list=False)
        instruments = list(membership)
    else:
        membership = None
    # Read through evaluation end, with all prior observations for causal warmup.
    end = max(v[1] for v in config['splits'].values() if v)
    fields = ['$' + x for x in REQUIRED] + ['$factor']
    frame = D.features(instruments, fields, end_time=end)
    paths = [path / 'calendars/day.txt']
    paths += sorted((path / 'instruments').glob('*.txt'))
    for symbol in frame.index.get_level_values('instrument').unique():
        paths += [path / 'features' / str(symbol).lower() / f'{field}.day.bin'
                  for field in (*REQUIRED, 'factor')]
    hashes = {str(p.relative_to(path)): file_hash(p) for p in paths if p.is_file()}
    intervals = None if membership is None else pd.DataFrame(
        [(symbol, start, end) for symbol, spans in membership.items() for start, end in spans],
        columns=['instrument', 'start', 'end'])
    return frame, hashes, intervals, pd.DatetimeIndex(D.calendar(end_time=end))


def _eligibility(frame, path):
    result = pd.DataFrame({'eligible': True}, index=frame.index)
    if path is None:
        return result
    intervals = path.copy() if isinstance(path, pd.DataFrame) else pd.read_csv(path, dtype={'instrument': str})
    if not {'instrument', 'start', 'end'}.issubset(intervals):
        raise ValueError('Universe needs instrument,start,end columns')
    intervals['start'] = pd.to_datetime(intervals.start)
    intervals['end'] = pd.to_datetime(intervals.end)
    if intervals[['start', 'end']].isna().any().any() or (intervals.start > intervals.end).any():
        raise ValueError('Invalid membership interval')
    selected = np.zeros(len(frame), dtype=bool)
    dates = frame.index.get_level_values('datetime')
    # One instrument grouping instead of an all-market string scan per interval.
    groups = frame.groupby(level='instrument', sort=False).indices
    for row in intervals.itertuples():
        positions = groups.get(row.instrument)
        if positions is None:
            continue
        subset_dates = dates.take(positions)
        selected[positions[(subset_dates >= row.start) & (subset_dates <= row.end)]] = True
    result['eligible'] = selected
    if not result.eligible.any():
        raise ValueError('No observations overlap the declared universe')
    return result


def make_provider(bars, destination, membership=None):
    """Write Qlib's documented calendar/instrument/float32 binary format.

    Missing observations remain NaN. QRBENCH is a synthetic equal-weight *price*
    reference, not an index license feed or a net tradable equal-weight strategy.
    """
    root = Path(destination)
    (root / 'calendars').mkdir(parents=True, exist_ok=True)
    (root / 'instruments').mkdir(exist_ok=True)
    calendar = pd.DatetimeIndex(bars.index.get_level_values('datetime').unique()).sort_values()
    dates = calendar.strftime('%Y-%m-%d').tolist()
    (root / 'calendars/day.txt').write_text('\n'.join(dates) + '\n')
    # Qlib requests the next timestamp at simulation termination. These two
    # sentinel dates are NOT asserted to be real future exchange sessions.
    sentinels = pd.bdate_range(calendar[-1] + pd.Timedelta(days=1), periods=2)
    (root / 'calendars/day_future.txt').write_text('\n'.join(dates + sentinels.strftime('%Y-%m-%d').tolist()) + '\n')
    rows = []
    for symbol, group in bars.groupby(level='instrument', sort=True):
        daily = group.droplevel('instrument').reindex(calendar)
        folder = root / 'features' / symbol.lower()
        folder.mkdir(parents=True, exist_ok=True)
        series = {column: daily[column] for column in REQUIRED}
        series['factor'] = daily.factor if 'factor' in daily else pd.Series(1., index=calendar)
        series['change'] = daily.close.pct_change(fill_method=None)
        for name, values in series.items():
            np.r_[np.float32(0), values.to_numpy(dtype=np.float32)].astype('<f4').tofile(folder / f'{name}.day.bin')
        observed = group.index.get_level_values('datetime')
        rows.append(f'{symbol}\t{observed.min():%Y-%m-%d}\t{observed.max():%Y-%m-%d}')
    (root / 'instruments/all.txt').write_text('\n'.join(rows) + '\n')
    closes = bars.close.unstack('instrument').reindex(calendar)
    returns = closes.pct_change(fill_method=None)
    if membership is not None:
        eligible = membership.eligible.unstack('instrument').reindex(index=calendar, columns=closes.columns, fill_value=False)
        # Membership at the preceding close decides the synthetic return basket.
        returns = returns.where(eligible.shift(1, fill_value=False))
    mean = returns.mean(axis=1)
    # Empty basket means cash for the reference; explicitly listed as a limitation.
    benchmark = (1 + mean.fillna(0)).cumprod() * 100
    folder = root / 'features' / BENCHMARK.lower()
    folder.mkdir(parents=True, exist_ok=True)
    for name in ('open', 'high', 'low', 'close'):
        np.r_[np.float32(0), benchmark.to_numpy(dtype=np.float32)].astype('<f4').tofile(folder / f'{name}.day.bin')
    for name, value in [('factor', 1.), ('volume', 1e12)]:
        np.r_[np.float32(0), np.full(len(calendar), value, dtype=np.float32)].astype('<f4').tofile(folder / f'{name}.day.bin')
    (root / 'instruments/qrbench.txt').write_text(f'{BENCHMARK}\t{dates[0]}\t{dates[-1]}\n')
    return {'benchmark': BENCHMARK, 'calendar': dates,
            'terminal_calendar_sentinels': sentinels.strftime('%Y-%m-%d').tolist()}


def prepare(workspace, config):
    workspace = Path(workspace).resolve()
    spec = config['data']
    source = _source_path(workspace, spec['path'])
    fmt = spec.get('format', source.suffix.lstrip('.')).lower()
    limitations = spec.get('limitations', [])
    if not isinstance(limitations, list) or any(not isinstance(item, str) for item in limitations):
        raise ValueError('Data limitations must be a list of strings')
    limitations = list(limitations)
    if spec.get('volume_unit', 'shares') not in ('shares', 'units'):
        raise ValueError('volume_unit must be shares or units; convert lots explicitly before import')
    if spec.get('price_basis', 'unspecified') not in ('raw', 'adjusted', 'unspecified'):
        raise ValueError('price_basis must be raw, adjusted or unspecified')
    if spec.get('price_basis', 'unspecified') == 'unspecified':
        limitations.append('Price adjustment basis unspecified; no PIT or corporate-action certification')
    if 'volume_unit' not in spec:
        limitations.append('Volume units not independently verified; simulator treats quantities as shares/units')
    implied_universe = None
    calendar = None
    if fmt == 'qlib':
        frame, hashes, implied_universe, calendar = _read_qlib(source, spec, config)
    elif fmt in ('csv', 'parquet'):
        frame = pd.read_csv(source, dtype={'instrument': str, 'symbol': str}) if fmt == 'csv' else pd.read_parquet(source)
        hashes = {source.name: file_hash(source)}
    else:
        raise ValueError('data.format must be csv, parquet or qlib')
    bars = normalize(frame, spec.get('columns'))
    observed_rows = len(bars)
    if spec.get('calendar'):
        calendar_path = _source_path(workspace, spec['calendar'])
        calendar = pd.DatetimeIndex(pd.to_datetime(calendar_path.read_text().splitlines()))
        hashes['calendar/' + calendar_path.name] = file_hash(calendar_path)
    if calendar is not None:
        if calendar.has_duplicates or not calendar.is_monotonic_increasing or calendar.hasnans:
            raise ValueError('Trading calendar must be ordered, unique, non-null dates')
        observed_dates = bars.index.get_level_values('datetime')
        if not observed_dates.isin(calendar).all():
            raise ValueError('Some market observations fall outside the supplied calendar')
        aligned = []
        for symbol, group in bars.groupby(level='instrument', sort=True):
            daily = group.droplevel('instrument')
            sessions = calendar[(calendar >= daily.index.min()) & (calendar <= daily.index.max())]
            daily = daily.reindex(sessions)
            daily.index.name = 'datetime'
            daily['instrument'] = symbol
            aligned.append(daily.reset_index().set_index(INDEX))
        bars = pd.concat(aligned).sort_index()
    universe_path = _source_path(workspace, spec['universe']) if spec.get('universe') else None
    eligible = _eligibility(bars, universe_path if universe_path is not None else implied_universe)
    if universe_path:
        hashes['universe/' + universe_path.name] = file_hash(universe_path)
    elif implied_universe is None:
        limitations.append('No independent historical membership file; observed universe may have survivorship bias')
    else:
        limitations.append('Universe intervals inherited from source Qlib provider; PIT validity not independently certified')
    requested_dates = [pd.Timestamp(v) for split in config['splits'].values() if split for v in split]
    if min(requested_dates) < bars.index.get_level_values('datetime').min() or max(requested_dates) > bars.index.get_level_values('datetime').max():
        raise ValueError('Configured splits extend beyond observed data coverage')
    if calendar is None:
        limitations.append('Calendar is inferred from observed dates; exchange completeness must be independently checked')
    destination = workspace / 'data'
    destination.mkdir(parents=True, exist_ok=True)
    bars.to_parquet(destination / 'bars.parquet')
    eligible.to_parquet(destination / 'eligibility.parquet')
    provider = make_provider(bars, destination / 'provider', eligible)
    source_identity = str(source)
    identity_spec = spec
    warehouse_dataset = {}
    if spec.get('dataset_id'):
        source_identity = 'warehouse://' + spec['dataset_id'] + '/' + spec['dataset_version']
        identity_spec = {k: v for k, v in spec.items() if k not in ('path', 'universe', 'calendar')}
        warehouse_dataset = {'warehouse_dataset': {'id': spec['dataset_id'], 'version': spec['dataset_version'],
                                                   'manifest_hash': spec['manifest_hash']}}
    manifest = {'schema_version': 1, 'source': source_identity, 'format': fmt, **warehouse_dataset,
                'interpretation': {key: spec[key] for key in ('region', 'price_basis', 'volume_unit', 'currency',
                    'frequency', 'adjustment_identity', 'adjustment_policy', 'volume_basis', 'universe_scope') if key in spec},
                'acquisition': spec.get('acquisition'),
                'source_hashes': hashes, 'rows': len(bars), 'observed_source_rows': observed_rows,
                'calendar_gap_rows': len(bars) - observed_rows,
                'instruments': sorted(bars.index.get_level_values('instrument').unique()),
                'first_date': str(bars.index.get_level_values('datetime').min().date()),
                'last_date': str(bars.index.get_level_values('datetime').max().date()),
                'missing_values': {k: int(v) for k, v in bars.isna().sum().items()},
                'eligible_rows': int(eligible.eligible.sum()),
                'bars_sha256': file_hash(destination / 'bars.parquet'),
                'eligibility_sha256': file_hash(destination / 'eligibility.parquet'),
                'provider_path': 'data/provider', **provider,
                'provider_hashes': {str(p.relative_to(destination / 'provider')): file_hash(p) for p in sorted((destination / 'provider').rglob('*')) if p.is_file()},
                'limitations': limitations + ['QRBENCH is a synthetic equal-weight close-price reference; cash on dates without a valid basket; no transaction costs', 'Daily-bar simulation does not certify real fills, capacity or point-in-time data quality']}
    manifest['dataset_id'] = hashlib.sha256(json.dumps({'hashes': hashes, 'spec': identity_spec}, sort_keys=True).encode()).hexdigest()
    _json(destination / 'manifest.json', manifest)
    return manifest


def load_bars(workspace):
    root = Path(workspace) / 'data'
    manifest = json.loads((root / 'manifest.json').read_text())
    if file_hash(root / 'bars.parquet') != manifest['bars_sha256'] or file_hash(root / 'eligibility.parquet') != manifest['eligibility_sha256']:
        raise ValueError('Prepared data changed since registration; create a new study snapshot')
    return pd.read_parquet(root / 'bars.parquet')


def verify(workspace):
    """Verify registered immutable working data, not mutable upstream locations."""
    root = Path(workspace) / 'data'
    manifest = json.loads((root / 'manifest.json').read_text())
    load_bars(workspace)
    for relative, digest in manifest.get('provider_hashes', {}).items():
        if file_hash(root / 'provider' / relative) != digest:
            raise ValueError(f'Prepared Qlib provider changed: {relative}')
    return {'dataset_id': manifest['dataset_id'], 'snapshot_verified': True}
