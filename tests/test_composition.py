"""Multiple immutable sources supplement absent rows without erasing disagreements."""
import json
from pathlib import Path
import shutil

import numpy as np
import pandas as pd
import pytest

from quantlib import composition as C
from quantlib import library as L
from quantlib import workspace as W


DATES = ['2026-01-02', '2026-01-05', '2026-01-06']
META = {
    'region': 'cn', 'price_basis': 'adjusted', 'volume_unit': 'units',
    'adjustment_identity': 'baostock-hfq-return-v1',
    'volume_basis': 'raw_shares_divided_by_factor',
    'currency': 'CNY', 'frequency': 'daily', 'synthetic': True,
    'provider': 'fixture', 'limitations': ['Synthetic fixtures are not market data'],
}


@pytest.fixture
def config(tmp_path):
    return L.config_init(tmp_path / 'library/quant-research.json')


def source(config, tmp_path, name, dates=DATES, closes=None, metadata=None, suspension=(),
           universe=None, calendar=DATES, format='parquet', include_factor=True):
    root = tmp_path / ('input-' + name)
    root.mkdir()
    closes = closes if closes is not None else [10.0] * len(dates)
    rows = []
    for date, close in zip(dates, closes):
        suspended = date in suspension
        rows.append({'datetime': date, 'instrument': 'SH600000',
                     'open': np.nan if suspended else close,
                     'high': np.nan if suspended else close + 1,
                     'low': np.nan if suspended else close - 1,
                     'close': np.nan if suspended else close,
                     'volume': 0. if suspended else 1000., 'factor': 2.})
    frame = pd.DataFrame(rows)
    if not include_factor:
        frame = frame.drop(columns='factor')
    file = root / ('bars.' + format)
    if format == 'csv':
        frame.to_csv(file, index=False)
    else:
        frame.to_parquet(file, index=False)
    members = pd.DataFrame(universe or [('SH600000', DATES[0], DATES[-1])], columns=['instrument', 'start', 'end'])
    members.to_csv(root / 'members.csv', index=False)
    (root / 'calendar.txt').write_text('\n'.join(calendar) + '\n')
    return L.dataset_add(config, name, 'v1', file, format, universe=root / 'members.csv',
                         calendar=root / 'calendar.txt', metadata={**META, **(metadata or {})})


def refs(*names):
    return [{'id': name, 'version': 'v1'} for name in names]


def evidence(record, name):
    return Path(record['dataset']['path']).parent / name


def test_supplements_only_absent_rows_and_pins_per_row_lineage(config, tmp_path):
    primary = source(config, tmp_path, 'primary', dates=[DATES[0], DATES[2]], closes=[10., 12.])
    secondary = source(config, tmp_path, 'secondary', dates=[DATES[1]], closes=[11.], format='csv')
    result = C.combine(config, 'combined', 'v1', refs('primary', 'secondary'))
    bars = pd.read_parquet(result['dataset']['path'])
    lineage = pd.read_parquet(evidence(result, 'lineage.parquet'))
    assert bars.close.tolist() == [10., 11., 12.]
    assert lineage.source_id.tolist() == ['primary', 'secondary', 'primary']
    assert lineage.source_manifest_hash.tolist() == [primary['manifest_hash'], secondary['manifest_hash'], primary['manifest_hash']]
    assert result['conflict_count'] == 0
    assert json.loads((Path(result['batch_path']) / 'manifest.json').read_text())['status'] == 'complete'
    copied = L.dataset_resolve(config, 'combined', 'v1', result['dataset']['manifest_hash'])
    assert copied['metadata']['composition']['row_policy'] == 'first-present-whole-row'


@pytest.mark.parametrize('change', [
    {'adjustment_identity': 'different-anchor-v2'},
    {'volume_basis': 'raw_shares'},
    {'synthetic': False},
    {'currency': 'USD'},
])
def test_refuses_incompatible_semantics_and_keeps_failure_evidence(config, tmp_path, change):
    source(config, tmp_path, 'primary')
    source(config, tmp_path, 'secondary', metadata=change)
    with pytest.raises(ValueError, match='Incompatible dataset semantics'):
        C.combine(config, 'combined', 'v1', refs('primary', 'secondary'))
    assert not (Path(config['warehouse_root']) / 'combined/v1').exists()
    batches = list((Path(config['sources_root']) / 'combined').iterdir())
    assert len(batches) == 1
    assert W.read(batches[0] / 'manifest.json')['status'] == 'failed'
    assert len(W.read(batches[0] / 'sources.json')) == 2


def test_default_rejects_conflicts_and_explicit_priority_records_both_values(config, tmp_path):
    source(config, tmp_path, 'primary')
    source(config, tmp_path, 'secondary', closes=[10., 15., 10.])
    with pytest.raises(ValueError, match='rows conflict'):
        C.combine(config, 'combined', 'rejected', refs('primary', 'secondary'))
    rejected = next((Path(config['sources_root']) / 'combined').iterdir())
    disagreement = pd.read_parquet(rejected / 'conflicts.parquet')
    assert len(disagreement) == 4
    assert disagreement.other_id.eq('secondary').all()
    assert disagreement.chosen_id.eq('primary').all()
    result = C.combine(config, 'combined', 'resolved', refs('primary', 'secondary'), conflicts='prefer-first')
    assert pd.read_parquet(result['dataset']['path']).close.tolist() == [10., 10., 10.]
    archived = pd.read_parquet(evidence(result, 'conflicts.parquet'))
    close = archived.loc[archived.field == 'close'].iloc[0]
    assert close.chosen_value == 10 and close.other_value == 15
    assert result['conflict_count'] == 4


def test_suspension_row_is_never_filled_from_secondary(config, tmp_path):
    source(config, tmp_path, 'primary', suspension=[DATES[1]])
    source(config, tmp_path, 'secondary')
    with pytest.raises(ValueError, match='rows conflict'):
        C.combine(config, 'combined', 'reject', refs('primary', 'secondary'))
    result = C.combine(config, 'combined', 'v1', refs('primary', 'secondary'), conflicts='prefer-first')
    bars = pd.read_parquet(result['dataset']['path'])
    suspended = bars.loc[(pd.Timestamp(DATES[1]), 'SH600000')]
    assert suspended[['open', 'high', 'low', 'close']].isna().all()
    assert suspended.volume == 0
    mismatches = pd.read_parquet(evidence(result, 'conflicts.parquet'))
    assert mismatches.kind.eq('nan_mismatch').sum() == 4
    lineage = pd.read_parquet(evidence(result, 'lineage.parquet'))
    assert lineage.loc[(pd.Timestamp(DATES[1]), 'SH600000'), 'source_id'] == 'primary'


def test_membership_union_does_not_bridge_eligibility_gaps(config, tmp_path):
    source(config, tmp_path, 'primary', dates=[DATES[0]], universe=[('SH600000', DATES[0], DATES[0])])
    source(config, tmp_path, 'secondary', dates=[DATES[2]], universe=[('SH600000', DATES[2], DATES[2])])
    result = C.combine(config, 'combined', 'v1', refs('primary', 'secondary'))
    members = pd.read_csv(result['dataset']['universe'])
    assert members[['start', 'end']].values.tolist() == [[DATES[0], DATES[0]], [DATES[2], DATES[2]]]
    assert result['rows'] == 2


def test_conflict_tolerance_accepts_only_declared_roundoff(config, tmp_path):
    source(config, tmp_path, 'primary')
    source(config, tmp_path, 'secondary', closes=[10.00000001] * 3)
    accepted = C.combine(config, 'combined', 'rounded', refs('primary', 'secondary'))
    assert accepted['conflict_count'] == 0
    with pytest.raises(ValueError, match='rows conflict'):
        C.combine(config, 'combined', 'strict', refs('primary', 'secondary'), rtol=0, atol=0)


def test_lineage_is_immutable_and_dataset_remains_portable(config, tmp_path):
    source(config, tmp_path, 'primary')
    source(config, tmp_path, 'secondary')
    result = C.combine(config, 'combined', 'v1', refs('primary', 'secondary'))
    moved = tmp_path / 'relocated'
    shutil.copytree(Path(config['config_path']).parent, moved)
    relocated = L.load_config(moved / 'quant-research.json')
    record = L.dataset_resolve(relocated, 'combined', 'v1', result['dataset']['manifest_hash'])
    lineage = pd.read_parquet(Path(record['path']).parent / 'lineage.parquet')
    assert lineage.source_id.eq('primary').all()
    assert record['metadata']['composition']['source_batch'].startswith('combined/')
    assert not Path(record['metadata']['composition']['source_batch']).is_absolute()
    (Path(record['path']).parent / 'lineage.parquet').write_bytes(b'tampered')
    with pytest.raises(ValueError, match='snapshot changed'):
        L.dataset_resolve(relocated, 'combined', 'v1', result['dataset']['manifest_hash'])
    assert L.dataset_resolve(config, 'combined', 'v1')['manifest_hash'] == result['dataset']['manifest_hash']


@pytest.mark.parametrize('metadata,include_factor,message', [
    ({'adjustment_identity': ''}, True, 'semantic metadata'),
    ({'volume_unit': 'shares', 'volume_basis': 'unknown'}, True, 'semantic metadata'),
    ({'synthetic': None}, True, 'boolean synthetic'),
    ({}, False, 'factor column'),
])
def test_unknown_contract_and_missing_factor_are_rejected(config, tmp_path, metadata, include_factor, message):
    source(config, tmp_path, 'primary')
    source(config, tmp_path, 'secondary', metadata=metadata, include_factor=include_factor)
    with pytest.raises(ValueError, match=message):
        C.combine(config, 'combined', 'v1', refs('primary', 'secondary'))


def test_rejects_duplicate_inputs_and_existing_output_version(config, tmp_path):
    source(config, tmp_path, 'primary')
    source(config, tmp_path, 'secondary')
    with pytest.raises(ValueError, match='distinct'):
        C.combine(config, 'combined', 'v1', refs('primary', 'primary'))
    first = C.combine(config, 'combined', 'v1', refs('primary', 'secondary'))
    with pytest.raises(ValueError, match='already exists'):
        C.combine(config, 'combined', 'v1', refs('primary', 'secondary'))
    assert L.dataset_resolve(config, 'combined', 'v1')['manifest_hash'] == first['dataset']['manifest_hash']


def test_tampered_source_cannot_contribute_rows(config, tmp_path):
    source(config, tmp_path, 'primary')
    second = source(config, tmp_path, 'secondary')
    Path(second['path']).write_bytes(b'tampered')
    with pytest.raises(ValueError, match='snapshot changed'):
        C.combine(config, 'combined', 'v1', refs('primary', 'secondary'))
    assert not (Path(config['warehouse_root']) / 'combined/v1').exists()


def test_union_calendar_is_sorted_and_shared_lifetime_must_be_complete(config, tmp_path):
    source(config, tmp_path, 'primary', dates=[DATES[0]], calendar=[DATES[0]])
    source(config, tmp_path, 'secondary', dates=[DATES[1], DATES[2]], calendar=DATES[1:])
    result = C.combine(config, 'combined', 'v1', refs('primary', 'secondary'))
    assert Path(result['dataset']['calendar']).read_text().splitlines() == DATES
    source(config, tmp_path, 'missing', dates=[DATES[2]])
    with pytest.raises(ValueError):
        C.combine(config, 'combined', 'gap', refs('primary', 'missing'))
    assert not (Path(config['warehouse_root']) / 'combined/gap').exists()


def test_source_name_and_complete_status_survive_relocation(config, tmp_path):
    source(config, tmp_path, 'primary', metadata={'source': 'baostock', 'provider': 'old-label'})
    source(config, tmp_path, 'secondary')
    result = C.combine(config, 'combined', 'v1', refs('primary', 'secondary'))
    assert result['batch'].startswith('combined/') and result['status'] == 'complete'
    lineage = pd.read_parquet(evidence(result, 'lineage.parquet'))
    assert lineage.source_provider.eq('baostock').all()
    checked = C.batch_status(config, result['batch'])
    assert checked['artifact_integrity'] == 'verified'
    assert checked['dataset']['dataset_id'] == 'combined'
    moved = tmp_path / 'moved'
    shutil.copytree(Path(config['config_path']).parent, moved)
    relocated = L.load_config(moved / 'quant-research.json')
    checked = C.batch_status(relocated, result['batch'])
    assert checked['status'] == 'complete' and str(moved) in checked['batch_path']


def test_failed_batch_status_is_inspectable(config, tmp_path):
    source(config, tmp_path, 'primary')
    source(config, tmp_path, 'secondary', closes=[20., 20., 20.])
    with pytest.raises(ValueError, match='rows conflict'):
        C.combine(config, 'combined', 'v1', refs('primary', 'secondary'))
    batch = next((Path(config['sources_root']) / 'combined').iterdir())
    status = C.batch_status(config, batch)
    assert status['status'] == 'failed'
    assert status['artifact_integrity'] == 'verified'
    assert 'conflict' in status['error']['message']


@pytest.mark.parametrize('tamper', ['request', 'artifact', 'manifest', 'warehouse', 'extra'])
def test_batch_status_detects_tampering(config, tmp_path, tamper):
    source(config, tmp_path, 'primary')
    source(config, tmp_path, 'secondary')
    result = C.combine(config, 'combined', 'v1', refs('primary', 'secondary'))
    batch = Path(result['batch_path'])
    if tamper == 'request':
        request = W.read(batch / 'request.json')
        request['conflict_policy'] = 'prefer-first'
        W.write(batch / 'request.json', request)
    elif tamper == 'manifest':
        manifest = W.read(batch / 'manifest.json')
        manifest['created_at'] = 'changed'
        W.write(batch / 'manifest.json', manifest)
    elif tamper == 'warehouse':
        Path(result['dataset']['path']).write_bytes(b'changed')
    elif tamper == 'extra':
        (batch / 'unregistered.txt').write_text('extra')
    else:
        (batch / 'lineage.parquet').write_bytes(b'changed')
    with pytest.raises(ValueError):
        C.batch_status(config, result['batch'])
