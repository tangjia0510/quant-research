"""Compose compatible immutable datasets with explicit row priority and lineage."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import uuid

import numpy as np
import pandas as pd

from . import data, library, workspace as W


SIGNATURE_FIELDS = (
    'region', 'price_basis', 'volume_unit', 'adjustment_identity',
    'volume_basis', 'currency', 'frequency',
)
_CONFLICT_COLUMNS = [
    'datetime', 'instrument', 'field', 'chosen_id', 'chosen_version',
    'chosen_manifest_hash', 'chosen_provider', 'other_id', 'other_version',
    'other_manifest_hash', 'other_provider', 'chosen_value', 'other_value',
    'absolute_difference', 'kind',
]


def _signature(metadata):
    result = {}
    for name in SIGNATURE_FIELDS:
        value = metadata.get(name)
        if (not isinstance(value, str) or not value.strip()
                or value.strip().lower() in {'unknown', 'unspecified', 'none', 'n/a'}):
            raise ValueError('Composition requires explicit semantic metadata: ' + name)
        result[name] = value
    if result['price_basis'] not in {'raw', 'adjusted'}:
        raise ValueError('Composition price_basis must be raw or adjusted')
    if result['volume_unit'] not in {'shares', 'units'}:
        raise ValueError('Composition volume_unit must be shares or units')
    if type(metadata.get('synthetic')) is not bool:
        raise ValueError('Composition requires explicit boolean synthetic metadata')
    result['synthetic'] = metadata['synthetic']
    return result


def _calendar(path):
    dates = pd.DatetimeIndex(pd.to_datetime(Path(path).read_text().splitlines(), errors='raise'))
    if (dates.empty or dates.hasnans or dates.tz is not None or dates.has_duplicates
            or not dates.is_monotonic_increasing or not dates.equals(dates.normalize())):
        raise ValueError('Composition calendar must contain ordered unique exchange-local daily dates')
    return dates


def _universe(path):
    table = pd.read_csv(path, dtype={'instrument': str})
    if not {'instrument', 'start', 'end'}.issubset(table.columns):
        raise ValueError('Composition universe requires instrument,start,end')
    table = table[['instrument', 'start', 'end']].copy()
    if table.empty or table.instrument.isna().any() or table.instrument.eq('').any():
        raise ValueError('Composition universe is empty or has missing instruments')
    for field in ('start', 'end'):
        table[field] = pd.to_datetime(table[field], errors='raise')
        dates = pd.DatetimeIndex(table[field])
        if dates.hasnans or dates.tz is not None or not dates.equals(dates.normalize()):
            raise ValueError('Composition membership dates must be exchange-local daily dates')
    if (table.start > table.end).any():
        raise ValueError('Composition membership interval is reversed')
    return table


def _merge_intervals(tables):
    """Exact interval union, never bridging a gap in declared eligibility."""
    table = pd.concat(tables, ignore_index=True).drop_duplicates()
    rows = []
    for instrument, intervals in table.groupby('instrument', sort=True):
        start = end = None
        for row in intervals.sort_values(['start', 'end']).itertuples():
            if start is None:
                start, end = row.start, row.end
            elif row.start <= end + pd.Timedelta(days=1):
                end = max(end, row.end)
            else:
                rows.append((instrument, start, end))
                start, end = row.start, row.end
        rows.append((instrument, start, end))
    return pd.DataFrame(rows, columns=['instrument', 'start', 'end'])


def _read_dataset(config, reference):
    registered = library.dataset_resolve(config, reference['id'], reference['version'])
    if registered['format'] not in {'csv', 'parquet'}:
        raise ValueError('Composition supports registered CSV or Parquet datasets only')
    if not registered.get('calendar') or not registered.get('universe'):
        raise ValueError('Composition inputs require registered calendar and universe sidecars')
    metadata = registered['metadata']
    signature = _signature(metadata)
    path = registered['path']
    frame = (pd.read_csv(path, dtype={'instrument': str, 'symbol': str})
             if registered['format'] == 'csv' else pd.read_parquet(path))
    bars = data.normalize(frame, metadata.get('columns'))
    if signature['price_basis'] == 'adjusted' and 'factor' not in bars:
        raise ValueError('Adjusted composition inputs require a factor column')
    if 'factor' not in bars:
        bars['factor'] = 1.0
    if bars.factor.isna().any() or bars.volume.isna().any():
        raise ValueError('Composition inputs require non-missing factor and volume')
    if signature['price_basis'] == 'raw' and not bars.factor.dropna().eq(1.0).all():
        raise ValueError('Raw composition input must use factor=1')
    absent_prices = bars[['open', 'high', 'low', 'close']].isna().sum(axis=1)
    if (~absent_prices.isin([0, 4])).any():
        raise ValueError('Composition input has partially missing OHLC')
    if (bars.loc[absent_prices.eq(4), 'volume'] != 0).any():
        raise ValueError('Composition non-trading rows require zero volume')
    calendar = _calendar(registered['calendar'])
    if not bars.index.get_level_values('datetime').isin(calendar).all():
        raise ValueError('Composition observations fall outside their registered calendar')
    universe = _universe(registered['universe'])
    if not bars.index.get_level_values('instrument').isin(universe.instrument).all():
        raise ValueError('Composition observations have no declared universe instrument')
    provider = metadata.get('source', metadata.get('provider', reference['id']))
    if not isinstance(provider, str):
        provider = reference['id']
    identity = {**reference, 'manifest_hash': registered['manifest_hash'], 'provider': provider}
    return registered, identity, signature, bars, calendar, universe


def _lineage(index, identity):
    return pd.DataFrame({
        'source_id': identity['id'], 'source_version': identity['version'],
        'source_manifest_hash': identity['manifest_hash'], 'source_provider': identity['provider'],
    }, index=index)


def _differences(chosen, other, lineage, identity, rtol, atol):
    overlap = chosen.index.intersection(other.index)
    if overlap.empty:
        return pd.DataFrame(columns=_CONFLICT_COLUMNS)
    left = chosen.loc[overlap].to_numpy()
    right = other.loc[overlap, chosen.columns].to_numpy()
    rows, columns = np.nonzero(~np.isclose(left, right, rtol=rtol, atol=atol, equal_nan=True))
    if not len(rows):
        return pd.DataFrame(columns=_CONFLICT_COLUMNS)
    keys = overlap[rows]
    provenance = lineage.loc[keys]
    left_values, right_values = left[rows, columns], right[rows, columns]
    return pd.DataFrame({
        'datetime': keys.get_level_values('datetime'),
        'instrument': keys.get_level_values('instrument'),
        'field': chosen.columns[columns],
        'chosen_id': provenance.source_id.to_numpy(),
        'chosen_version': provenance.source_version.to_numpy(),
        'chosen_manifest_hash': provenance.source_manifest_hash.to_numpy(),
        'chosen_provider': provenance.source_provider.to_numpy(),
        'other_id': identity['id'], 'other_version': identity['version'],
        'other_manifest_hash': identity['manifest_hash'], 'other_provider': identity['provider'],
        'chosen_value': left_values, 'other_value': right_values,
        'absolute_difference': np.abs(left_values - right_values),
        'kind': np.where(np.isnan(left_values) != np.isnan(right_values), 'nan_mismatch', 'numeric_difference'),
    })


def _new_batch(config):
    sources = Path(config['sources_root'])
    root = sources / 'combined'
    if root.is_symlink():
        raise ValueError('Composition batch directory cannot be a symlink')
    root.mkdir(parents=True, exist_ok=True)
    batch_id = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S%fZ-') + uuid.uuid4().hex[:8]
    batch = root / batch_id
    batch.mkdir()
    return batch_id, batch


def batch_status(config, batch):
    """Verify a completed or failed composition, including its warehouse snapshot."""
    sources = Path(config['sources_root']).resolve()
    given = Path(batch).expanduser()
    candidate = given if given.is_absolute() else sources / given
    if '..' in candidate.parts or candidate.parent.resolve() != sources / 'combined':
        raise ValueError('Composition batch must be a direct child of sources_root/combined')
    if (sources / 'combined').is_symlink() or candidate.is_symlink():
        raise ValueError('Composition batch cannot contain symlinks')
    folder = candidate.resolve()
    files = library._files(folder)
    state = W.read(folder / 'manifest.json')
    receipt = W.read(folder / 'status.json')
    request = W.read(folder / 'request.json')
    if (state.get('schema_version') != 1 or request.get('schema_version') != 1
            or state.get('batch_id') != folder.name or request.get('batch_id') != folder.name
            or request.get('operation') != 'combine'):
        raise ValueError('Composition batch identity is invalid')
    if W.identity(request) != receipt.get('request_hash') or W.identity(request) != state.get('request_hash'):
        raise ValueError('Composition request identity changed')
    if W.digest(folder / 'manifest.json') != receipt.get('manifest_hash'):
        raise ValueError('Composition manifest changed')
    if receipt.get('status') != state.get('status') or receipt.get('dataset') != state.get('dataset'):
        raise ValueError('Composition status differs from manifest')
    if state.get('status') not in {'running', 'complete', 'failed'}:
        raise ValueError('Unknown composition batch status')
    integrity = 'in_progress'
    if state['status'] != 'running':
        expected = state.get('files')
        if not isinstance(expected, dict) or 'request.json' not in expected:
            raise ValueError('Composition manifest has no evidence hashes')
        actual = {name: W.digest(path) for name, path in files.items()
                  if name not in {'manifest.json', 'status.json'}}
        if actual != expected:
            raise ValueError('Composition evidence changed: unexpected, missing or modified files')
        integrity = 'verified'
    if state['status'] == 'complete':
        reference = state.get('dataset', {})
        if (reference.get('dataset_id') != request.get('dataset_id')
                or reference.get('version') != request.get('version')):
            raise ValueError('Composition output dataset identity differs from request')
        library.dataset_resolve(config, reference['dataset_id'], reference['version'], reference['manifest_hash'])
    return {**state, 'batch': folder.relative_to(sources).as_posix(), 'batch_path': str(folder),
            'request': request, 'artifact_integrity': integrity}


def combine(config, dataset_id, version, inputs, conflicts='reject', rtol=1e-6, atol=1e-8):
    """Publish the union of compatible full rows; inputs are ordered by priority.

    A present row, including a suspension row or any NaN, is never filled from a
    lower-priority source. Disagreement is rejected unless prefer-first is explicit.
    """
    from .ingestion import validate_input

    library.safe_name(dataset_id)
    library.safe_name(version, 'Dataset version')
    if conflicts not in {'reject', 'prefer-first'}:
        raise ValueError('conflicts must be reject or prefer-first')
    if (isinstance(rtol, bool) or isinstance(atol, bool) or not np.isfinite(rtol)
            or not np.isfinite(atol) or rtol < 0 or atol < 0):
        raise ValueError('Composition tolerances must be finite and nonnegative')
    if not isinstance(inputs, list) or len(inputs) < 2:
        raise ValueError('Composition requires at least two distinct dataset references')
    refs = []
    for item in inputs:
        if not isinstance(item, dict) or set(item) != {'id', 'version'}:
            raise ValueError('Each composition input must contain only id and version')
        refs.append({'id': library.safe_name(item['id']),
                     'version': library.safe_name(item['version'], 'Dataset version')})
    if len({(ref['id'], ref['version']) for ref in refs}) != len(refs):
        raise ValueError('Composition input references must be distinct')

    batch_id, batch = _new_batch(config)
    request = {'schema_version': 1, 'operation': 'combine', 'batch_id': batch_id,
               'dataset_id': dataset_id, 'version': version, 'inputs': refs,
               'conflict_policy': conflicts, 'rtol': float(rtol), 'atol': float(atol),
               'row_policy': 'first-present-whole-row', 'created_at': W.now()}
    W.write(batch / 'request.json', request)
    state = {'schema_version': 1, 'batch_id': batch_id, 'status': 'running', 'created_at': W.now(),
             'request_hash': W.identity(request)}
    W.write(batch / 'manifest.json', state)
    W.write(batch / 'status.json', {'status': 'running', 'request_hash': state['request_hash'],
                                   'manifest_hash': W.digest(batch / 'manifest.json')})
    try:
        identities, signatures = [], []
        calendars, universes, differences, stats, limitations = [], [], [], [], []
        result = provenance = None
        metadata = None
        for reference in refs:
            registered, identity, signature, bars, calendar, universe = _read_dataset(config, reference)
            identities.append(identity)
            W.write(batch / 'sources.json', identities)
            if signatures and signature != signatures[0]:
                mismatched = [key for key in signature if signature[key] != signatures[0][key]]
                raise ValueError('Incompatible dataset semantics: ' + ', '.join(mismatched))
            signatures.append(signature)
            if metadata is None:
                metadata = dict(signature)
            inherited = registered['metadata'].get('limitations', [])
            if not isinstance(inherited, list) or any(not isinstance(item, str) for item in inherited):
                raise ValueError('Dataset limitations must be a list of strings')
            limitations.extend(inherited)
            calendars.append(calendar)
            universes.append(universe)
            if result is None:
                result = bars
                provenance = _lineage(bars.index, identity)
                added, overlap, mismatch = len(bars), 0, pd.DataFrame(columns=_CONFLICT_COLUMNS)
            else:
                mismatch = _differences(result, bars, provenance, identity, rtol, atol)
                missing = bars.index.difference(result.index)
                added, overlap = len(missing), len(bars) - len(missing)
                result = pd.concat([result, bars.loc[missing]]).sort_index()
                provenance = pd.concat([provenance, _lineage(missing, identity)]).sort_index()
            if not mismatch.empty:
                differences.append(mismatch)
            stats.append({**identity, 'source_rows': len(bars), 'added_rows': added,
                          'overlap_rows': overlap, 'conflicting_fields': len(mismatch)})

        merged_calendar = calendars[0]
        for calendar in calendars[1:]:
            merged_calendar = merged_calendar.union(calendar)
        merged_calendar = merged_calendar.sort_values()
        merged_universe = _merge_intervals(universes)
        conflict_table = (pd.concat(differences, ignore_index=True) if differences
                          else pd.DataFrame(columns=_CONFLICT_COLUMNS))
        result.to_parquet(batch / 'data.parquet')
        provenance.to_parquet(batch / 'lineage.parquet')
        conflict_table.to_parquet(batch / 'conflicts.parquet', index=False)
        merged_universe.to_csv(batch / 'universe.csv', index=False, date_format='%Y-%m-%d')
        (batch / 'calendar.txt').write_text('\n'.join(merged_calendar.strftime('%Y-%m-%d')) + '\n')
        W.write(batch / 'composition.json', {'schema_version': 1, 'inputs': stats,
                                           'conflict_policy': conflicts, 'row_policy': request['row_policy'],
                                           'conflicting_fields': len(conflict_table),
                                           'conflicting_rows': int(conflict_table[['datetime', 'instrument']].drop_duplicates().shape[0]),
                                           'semantic_signature': signatures[0], 'rtol': rtol, 'atol': atol})
        if len(conflict_table) and conflicts == 'reject':
            W.write(batch / 'quality.json', {'status': 'rejected', 'reason': 'source_conflicts',
                                           'conflicting_fields': len(conflict_table)})
            raise ValueError(f'Overlapping dataset rows conflict ({len(conflict_table)} fields); '
                             'inspect conflicts.parquet or explicitly choose prefer-first')
        # Carry only common semantics. A primary source's coverage, provider or
        # column aliases no longer describe the composed snapshot.
        limitations.append('Composition preserves whole rows by explicit source priority; it does not certify point-in-time vendor data')
        if len(conflict_table):
            limitations.append('Conflicting source rows resolved by explicit prefer-first policy; discrepancies are retained in conflicts.parquet')
        metadata.update(provider='combined', source_datasets=identities,
                        universe_scope='union_of_registered_membership_intervals',
                        limitations=list(dict.fromkeys(limitations)),
                        composition={'batch_id': batch_id, 'source_batch': 'combined/' + batch_id,
                                     'conflict_policy': conflicts, 'row_policy': request['row_policy'],
                                     'lineage': 'lineage.parquet', 'conflicts': 'conflicts.parquet',
                                     'rtol': rtol, 'atol': atol})
        quality = validate_input(result, merged_calendar, merged_universe, metadata)
        W.write(batch / 'quality.json', quality)
        W.write(batch / 'metadata.json', metadata)
        for identity in identities:
            library.dataset_resolve(config, identity['id'], identity['version'], identity['manifest_hash'])
        evidence = {name: batch / name for name in (
            'request.json', 'sources.json', 'composition.json', 'lineage.parquet', 'conflicts.parquet', 'quality.json',
        )}
        published = library.dataset_add(config, dataset_id, version, batch / 'data.parquet', 'parquet',
                                        universe=batch / 'universe.csv', calendar=batch / 'calendar.txt',
                                        metadata=metadata, evidence=evidence)
        state.update(status='complete', completed_at=W.now(), dataset={
            'dataset_id': dataset_id, 'version': version, 'manifest_hash': published['manifest_hash']})
        return_value = {'batch': 'combined/' + batch_id, 'batch_id': batch_id,
                        'batch_path': str(batch), 'status': 'complete', 'dataset': published,
                        'quality': quality, 'rows': len(result), 'conflict_count': len(conflict_table), 'policy': conflicts}
    except Exception as error:
        if not (batch / 'quality.json').exists():
            W.write(batch / 'quality.json', {'status': 'failed', 'error': {'type': type(error).__name__, 'message': str(error)}})
        state.update(status='failed', completed_at=W.now(), error={'type': type(error).__name__, 'message': str(error)})
        raise ValueError(f'{error}; composition evidence retained at {batch}') from error
    finally:
        state['files'] = {path.name: W.digest(path) for path in sorted(batch.iterdir())
                          if path.is_file() and path.name not in {'manifest.json', 'status.json'}}
        W.write(batch / 'manifest.json', state)
        W.write(batch / 'status.json', {'status': state['status'], 'request_hash': state['request_hash'],
                                       'manifest_hash': W.digest(batch / 'manifest.json'),
                                       **({'dataset': state['dataset']} if 'dataset' in state else {})})
    return return_value
