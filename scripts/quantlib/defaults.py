"""User-selected research defaults, materialized against a registered dataset."""
from __future__ import annotations

from pathlib import Path

DEFAULT_INITIAL_CASH = 100000
POLICY_ID = 'calendar-2020-2026-v1'
WINDOWS = {
    'train': ('2020-01-01', '2024-12-31'),
    'valid': ('2025-01-01', '2025-06-30'),
    'discovery': ('2025-07-01', '2025-12-31'),
    'final': ('2026-01-01', '2026-12-31'),
}


def policy():
    """Return fresh JSON-compatible policy data, without reading a library."""
    return {
        'policy_id': POLICY_ID,
        'mode': 'factor',
        'data_preparation': {'start': '2019-01-01', 'end': 'latest_available_completed_session',
                             'source': 'baostock', 'timezone': 'Asia/Shanghai'},
        'training_years': [2020, 2021, 2022, 2023, 2024],
        'validation_year': 2025,
        'test_year': 2026,
        'requested_splits': {key: list(interval) for key, interval in WINDOWS.items()},
        'validation_roles': {'valid': '2025 H1 model validation', 'discovery': '2025 H2 factor screening'},
        'portfolio': {'initial_cash': DEFAULT_INITIAL_CASH, 'top_k': 10, 'position': .95, 'rebalance': 5},
        'date_resolution': 'Use first and last available source date inside each requested window; never day_future.txt',
        'coverage_requirement': 'Each training year and each later segment must contain source dates; calendar completeness remains a data-quality question',
        'override': 'Supply --protocol to study new for an explicit protocol; existing studies are unchanged',
    }


def _calendar(path):
    import pandas as pd

    calendar = pd.DatetimeIndex(pd.to_datetime(Path(path).read_text().splitlines(), errors='raise'))
    if (calendar.empty or calendar.hasnans or calendar.tz is not None or calendar.has_duplicates
            or not calendar.is_monotonic_increasing or not calendar.equals(calendar.normalize())):
        raise ValueError('Default research dates require an ordered, unique, exchange-local daily calendar')
    return calendar


def _source_dates(registered):
    import pandas as pd
    from .data import normalize

    if registered['format'] == 'qlib':
        # The actual day calendar is the provider contract. Preparation separately
        # verifies the supplied quote data; day_future is never evidence of quotes.
        observed = _calendar(Path(registered['path']) / 'calendars/day.txt')
        source = 'qlib/calendars/day.txt; quote coverage must still pass prepare'
    else:
        if registered['format'] == 'csv':
            frame = pd.read_csv(registered['path'], dtype={'instrument': str, 'symbol': str})
        elif registered['format'] == 'parquet':
            frame = pd.read_parquet(registered['path'])
        else:
            raise ValueError('Defaults require a registered csv, parquet or qlib dataset')
        bars = normalize(frame, registered.get('metadata', {}).get('columns'))
        # All-missing calendar padding must not extend the available test period.
        quoted = bars[['open', 'high', 'low', 'close']].notna().all(axis=1)
        observed = pd.DatetimeIndex(bars.index.get_level_values('datetime')[quoted].unique()).sort_values()
        source = 'observed dates with complete OHLC quotes'
    if registered.get('calendar'):
        observed = observed.intersection(_calendar(registered['calendar']))
        source += ', intersected with registered calendar'
    if observed.empty:
        raise ValueError('No observed dates available for default research splits')
    return observed, source


def protocol_for_dataset(registered):
    """Create a complete default protocol before allocating or freezing a study."""
    import pandas as pd

    dates, source = _source_dates(registered)
    missing_years = [year for year in range(2020, 2025) if not (dates.year == year).any()]
    if missing_years:
        raise ValueError('Default training period lacks source dates for years: ' + ', '.join(map(str, missing_years))
                         + '; supply another dataset or an explicit --protocol')
    splits = {}
    for name, (start, end) in WINDOWS.items():
        available = dates[(dates >= pd.Timestamp(start)) & (dates <= pd.Timestamp(end))]
        if available.empty:
            raise ValueError('Default ' + name + ' period has no source dates; supply another dataset or an explicit --protocol')
        splits[name] = [str(available[0].date()), str(available[-1].date())]
    return {
        'schema_version': 1,
        'mode': 'factor',
        'objective': 'Research with fixed 2020-2024 training, 2025 validation/screening and 2026 testing',
        'data': {'format': registered['format']},
        'splits': splits,
        'portfolio': dict(policy()['portfolio']),
        'defaults_applied': {'policy_id': POLICY_ID,
                             'requested_splits': {key: list(value) for key, value in WINDOWS.items()},
                             'available_dates_source': source,
                             'first_source_date': str(dates[0].date()),
                             'last_source_date': str(dates[-1].date()),
                             'calendar_completeness_certified': False},
    }
