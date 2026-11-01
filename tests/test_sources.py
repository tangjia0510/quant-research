"""Source evidence must survive strict conversion, including tradability/units."""
from __future__ import annotations

import socket
import importlib
import json
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from quantlib.sources import SourceError, get_source, list_sources, register_source
from quantlib.sources.baostock import BaoStockSource, _DeadlineSocket


def payload():
    raw = pd.DataFrame([
        ['2020-01-02', 'sh.600000', '10', '12', '9', '11', '1000', '3', '1'],
        ['2020-01-03', 'sh.600000', '11', '11', '11', '11', '0', '3', '0'],
    ], columns=['date', 'code', 'open', 'high', 'low', 'close', 'volume', 'adjustflag', 'tradestatus'])
    adjusted = raw.copy()
    adjusted[['open', 'high', 'low', 'close']] = adjusted[['open', 'high', 'low', 'close']].astype(float) * 2
    adjusted['adjustflag'] = '1'
    return {'raw': raw, 'adjusted': adjusted}


def test_registry_and_metadata():
    assert list_sources()[0]['name'] == 'baostock'
    source = get_source('baostock')
    assert source.metadata['synthetic'] is False
    assert source.metadata['volume_unit'] == 'units'
    assert source.metadata['volume_basis'] == 'raw_shares_divided_by_factor'
    assert source.metadata['frequency'] == 'day'
    with pytest.raises(ValueError, match='Unknown data source'):
        get_source('not-registered')
    with pytest.raises(ValueError, match='already registered'):
        register_source('baostock', object, {})


def test_adjustment_preserves_raw_notional_and_suspension():
    bars = BaoStockSource().normalize_bars(payload())
    assert list(bars.columns) == ['datetime', 'instrument', 'open', 'high', 'low', 'close', 'volume', 'factor']
    assert bars.factor.tolist() == [2., 2.]
    assert bars.iloc[0].volume == 500
    assert bars.iloc[0].volume * bars.iloc[0].close == 1000 * 11
    assert bars.iloc[1][['open', 'high', 'low', 'close']].isna().all()
    assert bars.iloc[1].volume == 0
    assert bars.attrs['source_conversion_counts']['declared_suspension_rows'] == 1


def test_blank_volume_only_allowed_on_matched_declared_suspensions():
    p = payload()
    for frame in p.values():
        frame.loc[1, 'volume'] = ''
    bars = BaoStockSource().normalize_bars(p)
    assert bars.iloc[1].volume == 0
    assert bars.iloc[1][['open', 'high', 'low', 'close']].isna().all()
    assert bars.attrs['source_conversion_counts']['empty_suspension_volume_rows'] == 1
    assert p['raw'].loc[1, 'volume'] == ''  # Raw evidence is never rewritten.
    p['adjusted'].loc[1, 'volume'] = '0'
    with pytest.raises(ValueError, match='volume disagree'):
        BaoStockSource().normalize_bars(p)
    p = payload()
    for frame in p.values():
        frame.loc[0, 'volume'] = ''
    with pytest.raises(ValueError, match='must be finite'):
        BaoStockSource().normalize_bars(p)


def test_zero_volume_active_rows_cannot_trade():
    p = payload()
    for frame in p.values():
        frame.loc[0, 'volume'] = '0'
    bars = BaoStockSource().normalize_bars(p)
    assert bars.iloc[0][['open', 'high', 'low', 'close']].isna().all()
    assert bars.iloc[0].volume == 0
    assert bars.attrs['source_conversion_counts'] == {
        'declared_suspension_rows': 1,
        'empty_suspension_volume_rows': 0,
        'zero_volume_active_rows': 1,
    }


@pytest.mark.parametrize('mutate,message', [
    (lambda p: p['adjusted'].drop(index=1, inplace=True), 'do not align'),
    (lambda p: p['adjusted'].__setitem__('adjustflag', '2'), 'adjustment flag'),
    (lambda p: p['adjusted'].loc.__setitem__((0, 'high'), 30), 'one multiplicative'),
    (lambda p: p['adjusted'].loc.__setitem__((0, 'volume'), 500), 'volume disagree'),
    (lambda p: p['raw'].loc.__setitem__((0, 'tradestatus'), '9'), 'unknown trading'),
    (lambda p: p['raw'].loc.__setitem__((0, 'open'), np.nan), 'must be finite'),
    (lambda p: p['raw'].loc.__setitem__((0, 'open'), '-1'), 'positive prices'),
    (lambda p: p['raw'].loc.__setitem__((0, 'date'), '2020-01-02T12:00:00'), 'ISO date'),
    (lambda p: p['raw'].loc.__setitem__((0, 'code'), 'sz.200001'), 'unsupported instrument'),
])
def test_bad_bars_are_rejected(mutate, message):
    data = payload()
    mutate(data)
    with pytest.raises(ValueError, match=message):
        BaoStockSource().normalize_bars(data)


def test_duplicate_and_nonzero_suspension_rejected():
    p = payload()
    p['raw'] = pd.concat([p['raw'], p['raw'].iloc[[0]]])
    with pytest.raises(ValueError, match='duplicate'):
        BaoStockSource().normalize_bars(p)
    p = payload()
    p['raw'].loc[1, 'volume'] = '100'
    p['adjusted'].loc[1, 'volume'] = '100'
    with pytest.raises(ValueError, match='suspended rows'):
        BaoStockSource().normalize_bars(p)


def test_calendar():
    source = BaoStockSource()
    raw = pd.DataFrame({'calendar_date': ['2020-01-01', '2020-01-02'], 'is_trading_day': ['0', '1']})
    assert source.normalize_calendar(raw) == ['2020-01-02']
    with pytest.raises(ValueError, match='ordered, unique'):
        source.normalize_calendar(pd.concat([raw, raw]))
    raw.loc[0, 'is_trading_day'] = 'unknown'
    with pytest.raises(ValueError, match='valid trading flags'):
        source.normalize_calendar(raw)


def test_listing_intervals_include_delisted_not_current_only():
    raw = pd.DataFrame([
        ['sh.600000', '1999-11-10', '', '1', '1'],
        ['sz.000001', '1991-04-03', '2020-06-01', '1', '0'],
        ['sz.300001', '2021-01-05', '', '1', '1'],
        ['sz.200001', '1991-01-01', '', '1', '1'],
        ['sh.000001', '1991-01-01', '', '2', '1'],
        ['bj.830001', '2020-01-01', '', '1', '1'],
        ['sh.689009', '2020-01-01', '', '1', '1'],
    ], columns=['code', 'ipoDate', 'outDate', 'type', 'status'])
    selected = BaoStockSource().normalize_instruments(raw, '2019-01-01', '2020-12-31')
    assert selected.to_dict('records') == [
        {'instrument': 'sh.600000', 'start': '2019-01-01', 'end': '2020-12-31'},
        {'instrument': 'sz.000001', 'start': '2019-01-01', 'end': '2020-06-01'},
    ]


class Result:
    def __init__(self, rows=(), fields=(), code='0', message='success', pagination_error=False):
        self.error_code, self.error_msg = code, message
        self.fields, self.rows = list(fields), list(rows)
        self.at = -1
        self.pagination_error = pagination_error

    def next(self):
        self.at += 1
        if self.at >= len(self.rows):
            if self.pagination_error:
                self.error_code, self.error_msg = '10002007', 'failed on page two'
            return False
        return True

    def get_row_data(self):
        return self.rows[self.at]


class SDK:
    def __init__(self, results):
        self.results = iter(results)
        self.logins = self.logouts = self.calls = 0

    def login(self):
        self.logins += 1
        print('login success!')
        return Result()

    def logout(self):
        self.logouts += 1
        print('logout success!')
        return Result()

    def query_trade_dates(self, **kwargs):
        self.calls += 1
        return next(self.results)


def test_sdk_logs_do_not_corrupt_json_stdout(capsys):
    sdk = SDK([Result([['2020-01-02', '1']], ['calendar_date', 'is_trading_day'])])
    with BaoStockSource(sdk=sdk, delay=0) as source:
        frame = source.fetch_calendar('2020-01-01', '2020-01-03')
        assert len(frame) == 1
    output = capsys.readouterr()
    assert output.out == ''
    assert 'login success!' in output.err and 'logout success!' in output.err


def test_transient_error_retry_is_bounded_and_partial_pages_rejected():
    sdk = SDK([Result(code='10002007', message='connection lost'),
               Result([['2020-01-02', '1']], ['calendar_date', 'is_trading_day'], pagination_error=True)])
    with BaoStockSource(sdk=sdk, retries=1, delay=0) as source:
        with pytest.raises(SourceError, match='failed on page two'):
            source.fetch_calendar('2020-01-01', '2020-01-03')
    assert sdk.calls == 2 and sdk.logins == 2


def test_permissions_error_is_not_retried():
    sdk = SDK([Result(code='10001006', message='access denied')])
    with BaoStockSource(sdk=sdk, retries=2, delay=0) as source:
        with pytest.raises(SourceError, match='access denied'):
            source.fetch_calendar('2020-01-01', '2020-01-03')
    assert sdk.calls == 1


def test_connection_proxy_rejects_eof_and_restores_no_global_timeout():
    original = socket.getdefaulttimeout()
    owner = SimpleNamespace(_deadline=10**20)
    fake = SimpleNamespace(settimeout=lambda value: None, recv=lambda count: b'')
    with pytest.raises(ConnectionError, match='closed'):
        _DeadlineSocket(fake, owner).recv(8192)
    assert socket.getdefaulttimeout() == original


def test_sessions_cannot_overlap_and_lock_is_released():
    with BaoStockSource(sdk=SDK([]), delay=0):
        with pytest.raises(SourceError, match='one active session'):
            with BaoStockSource(sdk=SDK([]), delay=0):
                pass
    with BaoStockSource(sdk=SDK([]), delay=0):
        pass


def _real_result_page(rows, page='1'):
    resultset = importlib.import_module('baostock.data.resultset')
    result = resultset.ResultData()
    result.error_code, result.error_msg = '0', 'success'
    result.fields, result.data = ['code'], rows
    result.cur_page_num, result.per_page_count = page, '2'
    result.msg_type = '45'
    result.msg_body = '\x01'.join(['query_stock_basic', 'anonymous', '1', '2', '', ''])
    return result


def _patch_real_sdk_without_network(monkeypatch, send_msg):
    sdk = importlib.import_module('baostock')
    constants = importlib.import_module('baostock.common.contants')
    socketutil = importlib.import_module('baostock.util.socketutil')
    monkeypatch.setattr(constants, 'BAOSTOCK_PER_PAGE_COUNT', 2)
    monkeypatch.setattr(sdk, 'login', lambda: Result())
    monkeypatch.setattr(sdk, 'logout', lambda: Result())
    monkeypatch.setattr(sdk, 'query_stock_basic', lambda: _real_result_page([['sh.600000'], ['sh.600001']]))
    monkeypatch.setattr(socketutil, 'send_msg', send_msg)
    return socketutil


@pytest.mark.parametrize('empty_response', [None, '', '  '])
def test_real_sdk_silent_pagination_truncation_is_never_success(monkeypatch, empty_response):
    # ResultData.next() returns False on empty receive without clearing code=0.
    # Reproduce this against the actual SDK, not a fake that fixes the SDK bug.
    socketutil = _patch_real_sdk_without_network(monkeypatch, lambda msg: empty_response)
    before = socketutil.send_msg
    with BaoStockSource(delay=0, retries=0) as source:
        with pytest.raises(SourceError, match='(transport|pagination)'):
            source.fetch_instruments()
    assert socketutil.send_msg is before


def _wire_page(rows, page):
    header = importlib.import_module('baostock.data.messageheader')
    body = '\x01'.join(['0', 'success', 'query_stock_basic', 'anonymous', str(page), '2',
                       json.dumps({'record': rows}), '', '', 'code']) + '\n'
    return header.to_message_header('46', len(body)) + body


def test_real_sdk_repeated_page_is_rejected(monkeypatch):
    responses = iter([_wire_page([['sh.600000'], ['sh.600001']], 1), _wire_page([], 2)])
    _patch_real_sdk_without_network(monkeypatch, lambda msg: next(responses))
    with BaoStockSource(delay=0, retries=0) as source:
        with pytest.raises(SourceError, match='pagination'):
            source.fetch_instruments()


def test_real_sdk_transport_retry_restarts_query_and_returns_all_rows(monkeypatch):
    responses = iter([None, _wire_page([['sh.600002']], 2)])
    _patch_real_sdk_without_network(monkeypatch, lambda msg: next(responses))
    sdk = importlib.import_module('baostock')
    calls = []
    def query():
        calls.append('query')
        return _real_result_page([['sh.600000'], ['sh.600001']])
    monkeypatch.setattr(sdk, 'query_stock_basic', query)
    with BaoStockSource(delay=0, retries=1) as source:
        frame = source.fetch_instruments()
    assert len(calls) == 2
    assert frame.code.tolist() == ['sh.600000', 'sh.600001', 'sh.600002']


def test_real_sdk_permanent_transport_error_has_bounded_attempts(monkeypatch):
    calls = []
    def failed_receive(msg):
        calls.append(msg)
        return None
    _patch_real_sdk_without_network(monkeypatch, failed_receive)
    with BaoStockSource(delay=0, retries=2) as source:
        with pytest.raises(SourceError, match='transport') as caught:
            source.fetch_instruments()
    assert len(calls) == 3
    assert caught.value.code == 'transport_empty_response'
    assert caught.value.retryable is True


def test_real_sdk_timeout_budget_resets_for_each_network_page(monkeypatch):
    clock = [100.]
    adapter_module = importlib.import_module('quantlib.sources.baostock')
    monkeypatch.setattr(adapter_module.time, 'monotonic', lambda: clock[0])
    source = BaoStockSource(delay=0, timeout=1, retries=0)
    responses = iter([_wire_page([['sh.600002'], ['sh.600003']], 2),
                      _wire_page([['sh.600004']], 3)])
    deadlines = []
    def receive(msg):
        deadlines.append(source._deadline)
        assert source._deadline == clock[0] + 1
        clock[0] += 10  # Between pages, total elapsed time exceeds one timeout.
        return next(responses)
    _patch_real_sdk_without_network(monkeypatch, receive)
    with source:
        frame = source.fetch_instruments()
    assert len(frame) == 5
    assert deadlines == [101., 111.]
