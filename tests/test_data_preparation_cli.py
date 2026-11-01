"""The public CLI connects acquisition to frozen research assumptions and reports."""
from pathlib import Path

import pandas as pd
import pytest

import quant
from quantlib import library, sources, workspace as W


class FixtureSource:
    name = 'fixture'
    metadata = {'source': 'fixture', 'source_version': '1', 'region': 'cn',
                'price_basis': 'raw', 'volume_unit': 'shares', 'synthetic': True,
                'currency': 'CNY', 'frequency': 'day', 'adjustment_identity': 'raw-v1',
                'volume_basis': 'raw_shares', 'universe_scope': 'Synthetic integration fixture',
                'limitations': ['This is a synthetic connection test, never market evidence.']}
    dates = ['2019-01-02', '2020-01-02', '2021-01-04', '2022-01-04', '2023-01-03',
             '2024-01-02', '2025-01-02', '2025-07-01', '2026-01-05', '2026-10-30']

    def __init__(self, **options):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def fetch_calendar(self, start, end):
        return pd.DataFrame({'date': self.dates})

    def normalize_calendar(self, raw):
        return raw.date.tolist()

    def fetch_instruments(self):
        return pd.DataFrame({'instrument': ['A'], 'start': ['2019-01-01'], 'end': ['2026-10-30']})

    def normalize_instruments(self, raw, start, end):
        return raw.copy()

    def fetch_bars(self, instrument, start, end):
        return {'raw': pd.DataFrame({'datetime': self.dates, 'instrument': instrument,
                                    'open': 10., 'high': 11., 'low': 9., 'close': 10.,
                                    'volume': 1000., 'factor': 1.})}

    def normalize_bars(self, payload):
        return payload['raw'].copy()


def test_fetch_to_default_study_preserves_source_limits(tmp_path, monkeypatch):
    monkeypatch.setitem(sources._FACTORIES, 'fixture', FixtureSource)
    config = library.config_init(tmp_path / 'quant-research.json')

    def run(*args):
        return quant.dispatch(quant.parser().parse_args(['--config', config['config_path'], *args]))

    run('data', 'fetch', '--source', 'fixture', '--id', 'fixture-data', '--version', 'v1', '--end', '2026-10-30')
    run('data', 'validate', '--id', 'fixture-data', '--version', 'v1')
    result = run('study', 'new', '--dataset', 'fixture-data', '--version', 'v1', '--slug', 'source-defaults')
    root = Path(result['workspace'])
    protocol = W.read(root / 'protocol.json')
    assert protocol['portfolio']['initial_cash'] == 100000
    assert protocol['splits']['train'] == ['2020-01-02', '2024-01-02']
    assert protocol['splits']['valid'][0] == '2025-01-02'
    assert protocol['splits']['discovery'][0] == '2025-07-01'
    assert protocol['splits']['final'] == ['2026-01-05', '2026-10-30']
    assert protocol['data']['currency'] == 'CNY'
    assert protocol['data']['adjustment_identity'] == 'raw-v1'
    assert FixtureSource.metadata['limitations'][0] in protocol['data']['limitations']
    run('prepare', '--workspace', str(root))
    run('report', '--workspace', str(root))
    assert FixtureSource.metadata['limitations'][0] in (root / 'report.md').read_text()
    assert W.read(root / 'data/manifest.json')['interpretation']['volume_basis'] == 'raw_shares'


def test_source_inventory_does_not_need_library(tmp_path, monkeypatch):
    monkeypatch.setenv('QUANT_RESEARCH_CONFIG', str(tmp_path / 'missing.json'))
    result = quant.dispatch(quant.parser().parse_args(['source', 'list']))
    assert any(row['name'] == 'baostock' and not row['requires_credentials'] for row in result['sources'])


def test_source_limitations_cannot_be_reinterpreted_by_protocol(tmp_path):
    config = library.config_init(tmp_path / 'quant-research.json')
    source = tmp_path / 'bars.csv'
    FixtureSource().fetch_bars('A', None, None)['raw'].to_csv(source, index=False)
    library.dataset_add(config, 'fixture', 'v1', source, 'csv', metadata=FixtureSource.metadata)
    protocol = tmp_path / 'input.json'
    W.write(protocol, {'mode': 'factor', 'data': {'currency': 'USD'},
                      'splits': {'train': ['2020-01-02', '2024-01-02'],
                                 'valid': ['2025-01-02', '2025-01-02'],
                                 'discovery': ['2025-07-01', '2025-07-01'],
                                 'final': ['2026-01-05', '2026-10-30']}})
    args = quant.parser().parse_args(['--config', config['config_path'], 'study', 'new',
                                     '--dataset', 'fixture', '--version', 'v1', '--slug', 'wrong-currency',
                                     '--protocol', str(protocol)])
    with pytest.raises(ValueError, match='currency'):
        quant.dispatch(args)
    assert not list(Path(config['research_root']).glob('*/study.json'))
