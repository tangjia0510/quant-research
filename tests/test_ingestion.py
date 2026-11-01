"""Acquisition must preserve raw attempts and refuse incomplete publication."""
from datetime import datetime
from pathlib import Path
import shutil

import pandas as pd
import pytest

from quantlib import ingestion as I
from quantlib import library as L
from quantlib import sources
from quantlib import workspace as W


METADATA = {'region': 'cn', 'price_basis': 'adjusted', 'volume_unit': 'units',
            'volume_basis': 'raw_shares_divided_by_factor', 'currency': 'CNY',
            'adjustment_identity': 'test-hfq-v1', 'frequency': 'day',
            'synthetic': False, 'limitations': []}
SESSIONS = ['2026-10-26', '2026-10-27', '2026-10-28', '2026-10-29', '2026-10-30']
NOW = datetime.fromisoformat('2026-11-01T12:00:00+08:00')


class FakeSource:
    metadata = METADATA

    def __init__(self):
        self.calls = []
        self.fail = None
        self.gaps = {}
        self.suspended = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def fetch_calendar(self, start, end):
        self.calls.append('calendar')
        return pd.DataFrame({'date': [d for d in SESSIONS if start <= d <= end]})

    def normalize_calendar(self, raw):
        return raw.date.tolist()

    def fetch_instruments(self):
        self.calls.append('instruments')
        return pd.DataFrame({'instrument': ['sh.600000', 'sz.000001'],
                             'start': [SESSIONS[0]] * 2, 'end': [SESSIONS[-1]] * 2})

    def normalize_instruments(self, raw, start, end):
        result = raw.copy()
        result['start'] = result.start.map(lambda d: max(start, d))
        result['end'] = result.end.map(lambda d: min(end, d))
        return result

    def fetch_bars(self, instrument, start, end):
        self.calls.append(instrument)
        if self.fail == instrument:
            raise RuntimeError('Source request failed')
        dates = [d for d in SESSIONS if start <= d <= end and d not in self.gaps.get(instrument, [])]
        frame = pd.DataFrame({'datetime': dates, 'instrument': instrument,
                              'open': 20., 'high': 22., 'low': 18., 'close': 20.,
                              'volume': 500., 'factor': 2.})
        if self.suspended:
            frame.loc[0, ['open', 'high', 'low', 'close']] = float('nan')
            frame.loc[0, 'volume'] = 0.
        return {'raw': frame.copy(), 'adjusted': frame.copy()}

    def normalize_bars(self, payload):
        frame = payload['adjusted'].copy()
        frame.attrs['source_conversion_counts'] = {'declared_suspension_rows': int(self.suspended)}
        return frame


@pytest.fixture
def setup(tmp_path, monkeypatch):
    config = L.config_init(tmp_path / 'library/quant-research.json')
    source = FakeSource()
    monkeypatch.setattr(sources, 'get_source', lambda name, **options: source)
    return config, source


def acquire(config, **kwargs):
    return I.ingest(config, 'fake', 'cn-daily', 'v1', start=SESSIONS[0], now=NOW, **kwargs)


def batch(config):
    return next(p for p in Path(config['sources_root']).glob('fake/*') if p.is_dir())


def test_complete_import_pins_raw_quality_and_relocates(setup, tmp_path):
    config, source = setup
    result = acquire(config)
    assert result['status'] == 'complete'
    assert result['quality']['rows'] == 10
    registered = L.dataset_resolve(config, 'cn-daily', 'v1')
    folder = Path(registered['path']).parent
    assert W.read(folder / 'quality.json')['missing_calendar_rows'] == 0
    acquisition = W.read(folder / 'acquisition.json')
    assert len(acquisition['raw_files']) >= 6
    assert not acquisition['batch'].startswith('/')
    assert acquisition['adapter']['universe_basis'] == 'source_security_lifetimes'
    copied = tmp_path / 'copied'
    shutil.copytree(Path(config['config_path']).parent, copied)
    shutil.rmtree(Path(config['config_path']).parent)
    restored = L.load_config(copied / 'quant-research.json')
    assert I.batch_status(restored, result['batch'])['status'] == 'complete'
    assert L.dataset_resolve(restored, 'cn-daily', 'v1')['manifest_hash'] == registered['manifest_hash']


def test_failed_source_has_no_dataset_and_resume_reuses_verified_raw(setup):
    config, source = setup
    source.fail = 'sz.000001'
    with pytest.raises(RuntimeError, match='Source request failed') as failure:
        acquire(config)
    assert L.dataset_list(config) == []
    root = batch(config)
    assert failure.value.acquisition_batch == root.relative_to(Path(config['sources_root'])).as_posix()
    assert failure.value.acquisition_batch_path == str(root)
    status = I.batch_status(config, root)
    assert status['status'] == 'failed'
    assert status['completed_instruments'] == 1
    assert list(root.glob('raw/bars/sz.000001/attempt-1/failure.json'))
    source.fail = None
    source.calls.clear()
    result = acquire(config, resume=root)
    assert result['status'] == 'complete'
    assert source.calls == ['sz.000001']
    assert list(root.glob('raw/bars/sz.000001/attempt-2/raw.parquet'))


def test_corrupt_partial_cache_is_rejected_not_redownloaded(setup):
    config, source = setup
    source.fail = 'sz.000001'
    with pytest.raises(RuntimeError):
        acquire(config)
    root = batch(config)
    path = next(root.glob('raw/bars/sh.600000/attempt-*/*.parquet'))
    path.write_bytes(b'altered')
    source.fail = None
    with pytest.raises(ValueError, match='evidence changed'):
        acquire(config, resume=root)
    assert L.dataset_list(config) == []


def test_resume_rejects_changed_request_and_adapter(setup):
    config, source = setup
    source.fail = 'sz.000001'
    with pytest.raises(RuntimeError):
        acquire(config)
    root = batch(config)
    with pytest.raises(ValueError, match='identical acquisition request'):
        acquire(config, resume=root, end=SESSIONS[-1])
    source.metadata = {**METADATA, 'source_version': 'changed'}
    with pytest.raises(ValueError, match='adapter changed'):
        acquire(config, resume=root)


def test_resume_rejects_changed_normalization_implementation(setup, monkeypatch):
    config, source = setup
    source.fail = 'sz.000001'
    with pytest.raises(RuntimeError):
        acquire(config)
    root = batch(config)
    monkeypatch.setattr(I, '_implementation', lambda adapter: {'adapter_sha256': 'changed'})
    with pytest.raises(ValueError, match='adapter changed'):
        acquire(config, resume=root)
    assert L.dataset_list(config) == []


def test_missing_internal_session_never_publishes(setup):
    config, source = setup
    source.gaps = {'sh.600000': ['2026-10-28']}
    with pytest.raises(ValueError, match='Incomplete security/calendar coverage'):
        acquire(config)
    assert L.dataset_list(config) == []
    assert I.batch_status(config, batch(config))['status'] == 'failed'


def test_default_end_uses_observed_prices_and_records_source_lag(setup):
    config, source = setup
    source.gaps = {instrument: ['2026-10-30'] for instrument in ['sh.600000', 'sz.000001']}
    result = acquire(config)
    assert result['quality']['source_latest_session'] == '2026-10-29'
    assert result['quality']['unavailable_trailing_sessions'] == ['2026-10-30']
    assert result['quality']['rows'] == 8


def test_explicit_end_missing_tail_fails(setup):
    config, source = setup
    source.gaps = {instrument: ['2026-10-30'] for instrument in ['sh.600000', 'sz.000001']}
    with pytest.raises(ValueError, match='latest exchange sessions'):
        acquire(config, end='2026-10-30')
    assert L.dataset_list(config) == []


def test_only_one_stale_security_is_not_global_lag(setup):
    config, source = setup
    source.gaps = {'sh.600000': ['2026-10-30']}
    with pytest.raises(ValueError, match='Incomplete security/calendar coverage'):
        acquire(config)


def test_completed_clock_bound_and_future_request(setup):
    config, _ = setup
    assert I.completed_date_bound(datetime.fromisoformat('2026-10-30T19:59:59+08:00')) == '2026-10-29'
    assert I.completed_date_bound(datetime.fromisoformat('2026-10-30T20:00:00+08:00')) == '2026-10-30'
    with pytest.raises(ValueError, match='completed exchange-date bound'):
        acquire(config, end='2026-11-02')
    assert not list(Path(config['sources_root']).iterdir())


def test_explicit_sample_and_suspension_remain_declared(setup):
    config, source = setup
    source.suspended = True
    result = acquire(config, instruments=['sh.600000'])
    assert result['quality']['non_trading_rows'] == 1
    assert result['quality']['source_conversion_counts']['declared_suspension_rows'] == 1
    assert result['quality']['instruments'] == 1
    data = L.dataset_resolve(config, 'cn-daily', 'v1')
    assert data['metadata']['universe_basis'] == 'explicit_security_sample'
    assert 'not a full-market' in ' '.join(data['metadata']['limitations'])


def test_synthetic_source_is_never_relabelled_as_real(setup):
    config, source = setup
    source.metadata = {**METADATA, 'synthetic': True}
    acquire(config)
    metadata = L.dataset_resolve(config, 'cn-daily', 'v1')['metadata']
    assert metadata['synthetic'] is True
    assert 'not real market observations' in ' '.join(metadata['limitations'])


def test_uppercase_source_identifiers_are_preserved(setup):
    config, source = setup
    source.fetch_instruments = lambda: pd.DataFrame({'instrument': ['SH600000'],
                                                    'start': [SESSIONS[0]], 'end': [SESSIONS[-1]]})
    result = acquire(config, instruments=['SH600000'])
    registered = L.dataset_resolve(config, 'cn-daily', 'v1')
    assert set(pd.read_parquet(registered['path']).index.get_level_values('instrument')) == {'SH600000'}
    assert result['quality']['coverage'][0]['instrument'] == 'SH600000'


def test_case_colliding_identifiers_are_rejected_before_download(setup):
    config, source = setup
    with pytest.raises(ValueError, match='collide'):
        acquire(config, instruments=['A', 'a'])
    assert source.calls == []


@pytest.mark.parametrize('kind', ['duplicate', 'ohlc', 'partial_nan', 'factor', 'volume'])
def test_invalid_normalized_data_is_rejected(kind):
    source = FakeSource()
    bars = source.fetch_bars('sh.600000', SESSIONS[0], SESSIONS[-1])['raw']
    if kind == 'duplicate':
        bars = pd.concat([bars, bars.iloc[:1]])
    elif kind == 'ohlc':
        bars.loc[0, 'high'] = 1
    elif kind == 'partial_nan':
        bars.loc[0, 'open'] = float('nan')
    elif kind == 'factor':
        bars.loc[0, 'factor'] = float('nan')
    else:
        bars.loc[0, 'volume'] = -1
    universe = source.fetch_instruments().iloc[:1]
    with pytest.raises(ValueError):
        I.validate_input(bars, SESSIONS, universe, METADATA)


@pytest.mark.parametrize('factor', [2., float('nan')])
def test_raw_prices_reject_nonunit_or_missing_factors(factor):
    source = FakeSource()
    bars = source.fetch_bars('sh.600000', SESSIONS[0], SESSIONS[-1])['raw']
    bars['factor'] = factor
    metadata = {**METADATA, 'price_basis': 'raw', 'volume_unit': 'shares', 'volume_basis': 'raw_shares'}
    with pytest.raises(ValueError, match='Raw prices require factor=1'):
        I.validate_input(bars, SESSIONS, source.fetch_instruments().iloc[:1], metadata)


@pytest.mark.parametrize('include_factor', [True, False])
def test_raw_prices_allow_unit_factor_or_omitted_factor(include_factor):
    source = FakeSource()
    bars = source.fetch_bars('sh.600000', SESSIONS[0], SESSIONS[-1])['raw']
    bars['factor'] = 1.
    if not include_factor:
        bars = bars.drop(columns='factor')
    metadata = {**METADATA, 'price_basis': 'raw', 'volume_unit': 'shares', 'volume_basis': 'raw_shares'}
    assert I.validate_input(bars, SESSIONS, source.fetch_instruments().iloc[:1], metadata)['status'] == 'passed'


@pytest.mark.parametrize('field,value', [('frequency', None), ('frequency', 'minute'),
                                       ('synthetic', None), ('synthetic', 'false'), ('synthetic', 0)])
def test_validator_requires_daily_frequency_and_boolean_synthetic(field, value):
    source = FakeSource()
    bars = source.fetch_bars('sh.600000', SESSIONS[0], SESSIONS[-1])['raw']
    with pytest.raises(ValueError, match='explicitly declare'):
        I.validate_input(bars, SESSIONS, source.fetch_instruments().iloc[:1], {**METADATA, field: value})


def test_daily_frequency_alias_is_accepted():
    source = FakeSource()
    bars = source.fetch_bars('sh.600000', SESSIONS[0], SESSIONS[-1])['raw']
    assert I.validate_input(bars, SESSIONS, source.fetch_instruments().iloc[:1],
                            {**METADATA, 'frequency': 'daily'})['status'] == 'passed'


def test_complete_resume_is_read_only_and_tampering_fails(setup):
    config, source = setup
    first = acquire(config)
    source.calls.clear()
    again = acquire(config, resume=first['batch'])
    assert again == first
    assert source.calls == []
    (batch(config) / 'extra.txt').write_text('unexpected')
    with pytest.raises(ValueError, match='unexpected or missing'):
        I.batch_status(config, first['batch'])


def test_other_process_source_lock_prevents_network_calls(setup):
    from filelock import FileLock, Timeout

    config, source = setup
    root = Path(config['sources_root']) / 'fake'
    root.mkdir()
    with FileLock(str(root / '.source.lock'), timeout=0):
        with pytest.raises(Timeout):
            acquire(config)
    assert source.calls == []
    assert L.dataset_list(config) == []
    # The unstarted batch remains inspectable and can resume when the source is free.
    result = acquire(config, resume=batch(config))
    assert result['status'] == 'complete'


def test_resume_recovers_crash_after_atomic_dataset_publication(setup, monkeypatch):
    config, _ = setup
    original = W.write
    failed = False

    def crash_once(path, value):
        nonlocal failed
        if Path(path).name == 'manifest.json' and 'fake' in Path(path).parts and not failed:
            failed = True
            raise RuntimeError('simulated process failure')
        return original(path, value)

    monkeypatch.setattr(W, 'write', crash_once)
    with pytest.raises(RuntimeError, match='simulated process failure'):
        acquire(config)
    assert len(L.dataset_list(config)) == 1
    result = acquire(config, resume=batch(config))
    assert result['status'] == 'complete'


def test_old_config_defaults_sources_without_rewriting(tmp_path):
    path = tmp_path / 'config.json'
    old = {'schema_version': 1, 'warehouse_root': 'warehouse', 'research_root': 'studies',
           'runtime_root': 'runtime', 'factor_root': 'factors'}
    W.write(path, old)
    before = path.read_bytes()
    config = L.load_config(path)
    assert config['sources_root'] == str(tmp_path / 'sources')
    assert path.read_bytes() == before
    with pytest.raises(ValueError, match='disjoint'):
        L.config_init(tmp_path / 'bad.json', sources_root='warehouse/raw')


def test_evidence_is_immutable_and_reserved_names_are_rejected(setup, tmp_path):
    config, _ = setup
    source = tmp_path / 'bars.csv'
    source.write_text('x\n1\n')
    evidence = tmp_path / 'receipt.json'
    W.write(evidence, {'passed': True})
    with pytest.raises(ValueError, match='cannot replace'):
        L.dataset_add(config, 'data', 'v1', source, 'csv', evidence={'manifest.json': evidence})
    result = L.dataset_add(config, 'data', 'v1', source, 'csv', evidence={'quality.json': evidence})
    stored = Path(result['path']).parent / 'quality.json'
    assert W.read(stored)['passed'] is True
    stored.write_text('altered')
    with pytest.raises(ValueError, match='snapshot changed'):
        L.dataset_resolve(config, 'data', 'v1')
