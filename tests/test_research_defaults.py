"""Default dates freeze observed coverage; explicit protocols remain authoritative."""
import json
from pathlib import Path
import subprocess
import sys

import pandas as pd
import pytest

import quant
from quantlib import defaults, library, workspace as W


DATES = ['2020-01-02', '2021-01-04', '2022-01-04', '2023-01-03', '2024-12-31',
         '2025-01-02', '2025-06-30', '2025-07-01', '2025-12-31', '2026-01-05', '2026-10-29']


def bars(dates=DATES):
    return pd.DataFrame({'datetime': dates, 'instrument': 'TEST', 'open': 10., 'high': 11.,
                         'low': 9., 'close': 10., 'volume': 1000.})


@pytest.fixture
def registered(tmp_path):
    config = library.config_init(tmp_path / 'library/quant-research.json')
    source = tmp_path / 'source.csv'
    bars().to_csv(source, index=False)
    record = library.dataset_add(config, 'market', 'v1', source, 'csv',
                                 metadata={'price_basis': 'raw', 'volume_unit': 'shares', 'synthetic': True})
    return config, record


def test_defaults_command_needs_no_library(tmp_path, monkeypatch):
    monkeypatch.setenv('QUANT_RESEARCH_CONFIG', str(tmp_path / 'missing.json'))
    result = quant.dispatch(quant.parser().parse_args(['defaults']))
    assert result['training_years'] == list(range(2020, 2025))
    assert result['validation_year'] == 2025 and result['test_year'] == 2026
    assert result['portfolio'] == {'initial_cash': 100000, 'top_k': 10, 'position': .95, 'rebalance': 5}
    result['requested_splits']['train'][0] = 'altered'
    assert defaults.policy()['requested_splits']['train'][0] == '2020-01-01'


def test_managed_cli_materializes_and_freezes_observed_default_dates(registered):
    config, record = registered
    before = Path(config['config_path']).read_bytes()
    process = subprocess.run([sys.executable, quant.__file__, '--config', config['config_path'],
                              'study', 'new', '--slug', 'default-study', '--dataset', 'market', '--version', 'v1'],
                             capture_output=True, text=True, timeout=30)
    payload = json.loads(process.stdout)
    assert process.returncode == 0 and payload['ok'], payload
    workspace = Path(payload['result']['workspace'])
    protocol = W.load(workspace)
    assert protocol['splits'] == {'train': ['2020-01-02', '2024-12-31'],
                                   'valid': ['2025-01-02', '2025-06-30'],
                                   'discovery': ['2025-07-01', '2025-12-31'],
                                   'final': ['2026-01-05', '2026-10-29']}
    assert protocol['portfolio']['initial_cash'] == 100000
    assert protocol['portfolio']['top_k'] == 10
    assert protocol['data']['manifest_hash'] == record['manifest_hash']
    assert protocol['data']['synthetic'] is True
    assert 'path' not in protocol['data']
    assert protocol['defaults_applied']['policy_id'] == defaults.POLICY_ID
    assert 'quant-default-protocol-' not in (workspace / 'protocol.json').read_text()
    assert Path(config['config_path']).read_bytes() == before


def test_explicit_protocol_and_cash_override_remain_unchanged(registered, tmp_path):
    config, record = registered
    content = defaults.protocol_for_dataset(record)
    content['portfolio']['initial_cash'] = 765432
    content['portfolio']['top_k'] = 7
    content['splits']['final'][1] = '2026-05-29'
    content.pop('defaults_applied')
    path = tmp_path / 'explicit.json'
    W.write(path, content)
    before = path.read_bytes()
    args = quant.parser().parse_args(['--config', config['config_path'], 'study', 'new', '--slug', 'explicit',
                                     '--dataset', 'market', '--version', 'v1', '--protocol', str(path)])
    root = Path(quant.dispatch(args)['workspace'])
    assert W.load(root)['portfolio']['initial_cash'] == 765432
    assert W.load(root)['portfolio']['top_k'] == 7
    assert W.load(root)['splits']['final'][1] == '2026-05-29'
    assert path.read_bytes() == before
    frozen = (root / 'protocol.json').read_bytes()
    # Loading an existing protocol never rematerializes its dates or its cash.
    assert W.load(root)['portfolio']['initial_cash'] == 765432
    assert (root / 'protocol.json').read_bytes() == frozen


def test_explicit_protocol_missing_cash_uses_new_default(registered):
    _, record = registered
    content = defaults.protocol_for_dataset(record)
    content.pop('portfolio')
    assert W.validate(content)['portfolio']['initial_cash'] == 100000


@pytest.mark.parametrize('missing', ['2022', '2025h1', '2025h2', '2026'])
def test_missing_requested_period_fails_without_allocating_study(tmp_path, missing):
    config = library.config_init(tmp_path / 'library/quant-research.json')
    frame = bars()
    dates = pd.to_datetime(frame.datetime)
    bad = {'2022': dates.dt.year.eq(2022),
           '2025h1': dates.dt.year.eq(2025) & dates.dt.month.le(6),
           '2025h2': dates.dt.year.eq(2025) & dates.dt.month.ge(7),
           '2026': dates.dt.year.eq(2026)}[missing]
    source = tmp_path / 'source.csv'
    frame.loc[~bad].to_csv(source, index=False)
    library.dataset_add(config, 'market', 'v1', source, 'csv')
    args = quant.parser().parse_args(['--config', config['config_path'], 'study', 'new', '--slug', 'missing',
                                     '--dataset', 'market', '--version', 'v1'])
    with pytest.raises(ValueError, match='Default'):
        quant.dispatch(args)
    assert not list(Path(config['research_root']).glob('*/study.json'))


def test_calendar_future_entries_and_nan_padding_do_not_extend_parquet_test_dates(tmp_path):
    source = tmp_path / 'source.parquet'
    frame = bars()
    padding = pd.DataFrame({'datetime': ['2026-12-31'], 'instrument': ['TEST']})
    frame = pd.concat([frame, padding], ignore_index=True).set_index(['datetime', 'instrument'])
    frame.to_parquet(source)
    calendar = tmp_path / 'calendar.txt'
    calendar.write_text('\n'.join(DATES + ['2026-12-31']) + '\n')
    protocol = defaults.protocol_for_dataset({'format': 'parquet', 'path': str(source),
                                              'calendar': str(calendar), 'metadata': {}})
    assert protocol['splits']['final'][-1] == '2026-10-29'


def test_custom_datetime_column_mapping_is_honored(tmp_path):
    source = tmp_path / 'mapped.csv'
    bars().rename(columns={'datetime': 'trading_day'}).to_csv(source, index=False)
    protocol = defaults.protocol_for_dataset({'format': 'csv', 'path': str(source),
                                              'metadata': {'columns': {'trading_day': 'datetime'}}})
    assert protocol['splits']['train'][0] == '2020-01-02'


def test_qlib_defaults_use_actual_day_calendar_not_future_calendar(tmp_path):
    calendar = tmp_path / 'provider/calendars'
    calendar.mkdir(parents=True)
    (calendar / 'day.txt').write_text('\n'.join(DATES) + '\n')
    (calendar / 'day_future.txt').write_text('\n'.join(DATES + ['2026-12-31']) + '\n')
    protocol = defaults.protocol_for_dataset({'format': 'qlib', 'path': str(calendar.parent), 'metadata': {}})
    assert protocol['splits']['final'][-1] == '2026-10-29'
    assert 'day.txt' in protocol['defaults_applied']['available_dates_source']


def test_mode_override_works_with_generated_protocol(registered):
    config, _ = registered
    args = quant.parser().parse_args(['--config', config['config_path'], 'study', 'new', '--slug', 'model-default',
                                     '--dataset', 'market', '--version', 'v1', '--mode', 'model'])
    root = Path(quant.dispatch(args)['workspace'])
    assert W.load(root)['mode'] == 'model'
