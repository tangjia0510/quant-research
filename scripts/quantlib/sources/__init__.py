"""Explicit, credential-free source registry for daily market-data adapters.

Adapters fetch source responses separately from normalization so ingestion can
preserve even responses that later fail the canonical data contract.
"""
from __future__ import annotations

from typing import Callable, Protocol

import pandas as pd


class SourceError(RuntimeError):
    """A source request failed; no partial response is accepted as success."""


class SourceAdapter(Protocol):
    name: str
    metadata: dict

    def __enter__(self): ...
    def __exit__(self, *args): ...
    def fetch_calendar(self, start: str, end: str) -> pd.DataFrame: ...
    def normalize_calendar(self, raw: pd.DataFrame) -> list[str]: ...
    def fetch_instruments(self) -> pd.DataFrame: ...
    def normalize_instruments(self, raw: pd.DataFrame, start: str, end: str) -> pd.DataFrame: ...
    def fetch_bars(self, instrument: str, start: str, end: str) -> dict[str, pd.DataFrame]: ...
    def normalize_bars(self, payload: dict[str, pd.DataFrame]) -> pd.DataFrame: ...


_FACTORIES: dict[str, Callable[..., SourceAdapter]] = {}
_DESCRIPTIONS: dict[str, dict] = {}


def register_source(name: str, factory: Callable[..., SourceAdapter], description: dict):
    """Register reviewed Python adapters; never load executable user JSON."""
    from ..library import safe_name
    safe_name(name, 'Source name')
    if name in _FACTORIES:
        raise ValueError('Source already registered: ' + name)
    if not callable(factory) or not isinstance(description, dict):
        raise ValueError('Source registration requires a callable and metadata object')
    _FACTORIES[name] = factory
    _DESCRIPTIONS[name] = {**description, 'name': name}


def list_sources():
    return [dict(_DESCRIPTIONS[name]) for name in sorted(_DESCRIPTIONS)]


def get_source(name, **options):
    if name not in _FACTORIES:
        raise ValueError('Unknown data source: ' + str(name))
    return _FACTORIES[name](**options)


from .baostock import BaoStockSource  # noqa: E402

register_source('baostock', BaoStockSource, {
    'description': 'Free anonymous Shanghai/Shenzhen A-share daily history',
    'requires_credentials': False,
    'dependency': 'baostock==0.9.4',
    'default_start': '2019-01-01',
    'capabilities': ['daily_bars', 'trading_calendar', 'listing_intervals', 'raw_responses'],
    'documentation': 'https://www.baostock.com/mainContent?file=stockKData.md',
})
