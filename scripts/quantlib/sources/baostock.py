"""BaoStock public API adapter, with raw-response preservation and strict units."""
from __future__ import annotations

import contextlib
import importlib
import importlib.metadata
import math
import re
import socket
import sys
import threading
import time
from types import SimpleNamespace

import numpy as np
import pandas as pd

from . import SourceError
from ..data import normalize


_LOCK = threading.Lock()  # The upstream SDK stores one process-global session.
_A_SHARE = re.compile(r'(?:sh\.(?:60\d{4}|688\d{3})|sz\.(?:00|30)\d{4})\Z')
_OHLC = ['open', 'high', 'low', 'close']
_FIELDS = 'date,code,open,high,low,close,volume,amount,adjustflag,tradestatus,isST'


def _date(value, label='date'):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise ValueError(label + ' must be an ISO date')
    parsed = pd.Timestamp(value)
    if pd.isna(parsed):
        raise ValueError(label + ' must be a date')
    return value


def _range(start, end):
    _date(start, 'start')
    _date(end, 'end')
    if start > end:
        raise ValueError('start must not follow end')


def _require(frame, columns, kind):
    missing = set(columns) - set(frame.columns)
    if missing:
        raise ValueError('BaoStock ' + kind + ' missing columns: ' + ', '.join(sorted(missing)))


class _DeadlineSocket:
    """Bound the SDK's reads and reject its otherwise endless empty-recv loop."""
    def __init__(self, inner, owner):
        self.inner, self.owner = inner, owner

    def _bound(self):
        remaining = self.owner._deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('BaoStock request deadline exceeded')
        self.inner.settimeout(remaining)

    def connect(self, *args):
        self._bound()
        return self.inner.connect(*args)

    def send(self, message, *args):
        self._bound()
        self.inner.sendall(message, *args)
        return len(message)

    def recv(self, *args):
        self._bound()
        result = self.inner.recv(*args)
        if not result:
            raise ConnectionError('BaoStock connection closed before the response completed')
        return result

    def __getattr__(self, name):
        return getattr(self.inner, name)


class BaoStockSource:
    name = 'baostock'

    def __init__(self, delay=.2, timeout=30, retries=1, sdk=None):
        if (not math.isfinite(delay) or delay < 0 or not math.isfinite(timeout) or timeout <= 0
                or not isinstance(retries, int) or isinstance(retries, bool) or not 0 <= retries <= 2):
            raise ValueError('Source needs nonnegative delay, positive timeout and 0–2 retries')
        self.delay, self.timeout, self.retries = delay, timeout, retries
        self._sdk = sdk
        self._injected_sdk = sdk is not None
        self._active = False
        self._deadline = 0
        self._last_request = 0
        self._context = self._socketutil = self._old_socket_module = None
        self._old_send_msg = None
        try:
            version = importlib.metadata.version('baostock')
        except importlib.metadata.PackageNotFoundError:
            version = None
        self.metadata = {
            'source': self.name, 'source_version': version, 'region': 'cn', 'synthetic': False,
            'price_basis': 'adjusted', 'volume_unit': 'units', 'currency': 'CNY',
            'frequency': 'day',
            'price_unit': 'CNY_per_adjusted_unit',
            'adjustment_identity': 'baostock-hfq-return-v1',
            'adjustment': 'BaoStock return-based backward adjustment (adjustflag=1)',
            'adjustment_policy': 'Backward adjustment from paired raw and hfq source prices',
            'factor_definition': 'adjusted_close/raw_close',
            'volume_basis': 'raw_shares_divided_by_factor',
            'suspension_policy': 'Raw tradestatus=0 maps OHLC to NaN and volume to zero',
            'nontrading_policy': 'Matched zero raw volume also masks OHLC when tradestatus=1; these rows are counted separately',
            'missing_volume_policy': 'Matched blank volumes are zero only when both responses explicitly declare tradestatus=0',
            'transport_integrity': 'Every SDK response must be nonempty; paginated responses must advance exactly one page; bounded retries restart the entire query',
            'universe_basis': 'Source basic listing/delisting intervals; not historical index membership',
            'universe_scope': 'Shanghai/Shenzhen ordinary A shares including source-reported delisted securities',
            'supported_markets': ['Shanghai A shares (60xxxx,688xxx)', 'Shenzhen A shares (00xxxx,30xxxx)'],
            'limitations': [
                'Source listing history is not independently certified complete; Beijing, B shares, CDRs and indices are excluded.',
                'ST status is preserved in raw responses but does not automatically exclude securities.',
                'Exchange price-limit and T+1 execution rules are not certified by ingestion.',
                'Backward-adjusted source history can be revised; each download is an immutable snapshot.',
                'Adjusted prices and volumes are simulation units; raw prices and shares remain in raw responses.',
                'Explicit suspension rows may contain blank volume at delisting; matched raw/hfq blanks become zero with an audit count.',
                'Zero-volume status=1 rows are non-executable and masked separately from declared suspensions.',
            ],
            'documentation': 'https://www.baostock.com/mainContent?file=stockKData.md',
        }

    def __enter__(self):
        if self._active or not _LOCK.acquire(blocking=False):
            raise SourceError('BaoStock SDK permits one active session per process')
        try:
            if not self._injected_sdk:
                try:
                    self._sdk = importlib.import_module('baostock')
                except ImportError as error:
                    raise SourceError('BaoStock is not installed; run bootstrap to install the skill locked dependencies') from error
                self._context = importlib.import_module('baostock.common.context')
                self._socketutil = importlib.import_module('baostock.util.socketutil')
                self._old_socket_module = self._socketutil.socket
                self._old_send_msg = self._socketutil.send_msg
                self._old_context = {name: getattr(self._context, name) for name in ('apiKey', 'user_id', 'default_socket')
                                     if hasattr(self._context, name)}
                if self._old_context.get('default_socket') is not None:
                    raise SourceError('An existing BaoStock session is active; close it before data preparation')
                # Only this SDK module is patched; Python socket defaults are untouched.
                self._socketutil.socket = SimpleNamespace(
                    AF_INET=socket.AF_INET, SOCK_STREAM=socket.SOCK_STREAM,
                    socket=lambda *args, **kwargs: _DeadlineSocket(socket.socket(*args, **kwargs), self))
                # ResultData.next() silently returns False on a failed receive
                # while leaving error_code='0'. Guard the shared SDK transport
                # before that failure can be mistaken for a completed last page.
                self._socketutil.send_msg = self._send_checked
                self._context.apiKey = '0'  # Explicit public endpoint; no inherited paid credentials.
            self._active = True
            self._login()
            return self
        except BaseException:
            self._restore()
            raise

    def _restore(self):
        if self._context is not None:
            current = getattr(self._context, 'default_socket', None)
            previous = getattr(self, '_old_context', {}).get('default_socket')
            if current is not None and current is not previous:
                current.close()
            for name in ('apiKey', 'user_id', 'default_socket'):
                if name in getattr(self, '_old_context', {}):
                    setattr(self._context, name, self._old_context[name])
                elif hasattr(self._context, name):
                    delattr(self._context, name)
        if self._socketutil is not None and self._old_socket_module is not None:
            self._socketutil.socket = self._old_socket_module
            self._socketutil.send_msg = self._old_send_msg
        self._active = False
        _LOCK.release()

    def __exit__(self, exc_type, exc, tb):
        try:
            if self._active:
                self._begin_request()
                with contextlib.redirect_stdout(sys.stderr):
                    self._sdk.logout()
        except Exception as error:
            print('BaoStock logout failed: ' + str(error), file=sys.stderr)
        finally:
            self._restore()

    def _begin_request(self):
        remaining = self.delay - (time.monotonic() - self._last_request)
        if remaining > 0:
            time.sleep(remaining)
        self._last_request = time.monotonic()
        self._deadline = self._last_request + self.timeout

    @staticmethod
    def _transport_error(code, message):
        error = SourceError('BaoStock ' + message)
        error.code, error.retryable = code, True
        return error

    def _send_checked(self, message):
        # One timeout per network exchange, including every pagination request;
        # a large valid result is not limited to one page's timeout budget.
        self._begin_request()
        try:
            response = self._old_send_msg(message)
        except (OSError, UnicodeError, ValueError) as error:
            raise self._transport_error('transport_failure', 'transport failed: ' + str(error)) from error
        if not isinstance(response, str) or not response.strip():
            raise self._transport_error(
                'transport_empty_response',
                'transport returned no complete response (SDK may have suppressed a timeout or decode error)')
        return response

    def _next_row(self, result, method):
        expected_page = None
        # Use the actual SDK's paging contract. Test adapters without these
        # attributes retain their own iterator/error contract.
        if all(hasattr(result, name) for name in ('data', 'cur_row_num', 'cur_page_num')):
            constants = importlib.import_module('baostock.common.contants')
            if len(result.data) == constants.BAOSTOCK_PER_PAGE_COUNT and result.cur_row_num >= len(result.data):
                page = str(result.cur_page_num)
                if not page.isdigit():
                    raise self._transport_error('pagination_invalid_page', 'pagination has an invalid current page number')
                expected_page = int(page) + 1
        try:
            more = result.next()
        except (UnicodeError, ValueError, IndexError, TypeError) as error:
            raise self._transport_error('pagination_decode_error', 'pagination response could not be decoded: ' + str(error)) from error
        self._check(result, method)
        if expected_page is not None and str(result.cur_page_num) != str(expected_page):
            raise self._transport_error(
                'pagination_no_progress', 'pagination did not advance to page ' + str(expected_page))
        return more

    @staticmethod
    def _check(result, method):
        if result is None:
            raise SourceError('BaoStock ' + method + ' returned no response')
        code = str(result.error_code)
        if code != '0':
            error = SourceError('BaoStock ' + method + ' failed [' + code + ']: ' + str(result.error_msg))
            error.retryable = code.startswith('10002')
            raise error

    def _login(self):
        self._begin_request()
        with contextlib.redirect_stdout(sys.stderr):
            result = self._sdk.login()
        self._check(result, 'login')

    def _frame(self, method, *args, **kwargs):
        if not self._active:
            raise SourceError('Use BaoStock inside its context manager')
        for attempt in range(self.retries + 1):
            try:
                if self._injected_sdk:
                    self._begin_request()
                with contextlib.redirect_stdout(sys.stderr):
                    result = getattr(self._sdk, method)(*args, **kwargs)
                    self._check(result, method)
                    rows = []
                    while self._next_row(result, method):
                        self._check(result, method)
                        rows.append(result.get_row_data())
                    self._check(result, method)
                return pd.DataFrame(rows, columns=result.fields)
            except (SourceError, OSError, TimeoutError) as error:
                if attempt >= self.retries or (isinstance(error, SourceError) and not getattr(error, 'retryable', False)):
                    raise
                if self._context is not None:
                    previous = getattr(self._context, 'default_socket', None)
                    if previous is not None:
                        previous.close()
                self._login()

    def fetch_calendar(self, start, end):
        _range(start, end)
        return self._frame('query_trade_dates', start_date=start, end_date=end)

    def normalize_calendar(self, raw):
        _require(raw, ['calendar_date', 'is_trading_day'], 'calendar')
        if raw.empty:
            raise ValueError('BaoStock returned an empty calendar')
        dates = raw.calendar_date.map(_date)
        flags = raw.is_trading_day.astype(str)
        if dates.duplicated().any() or not dates.is_monotonic_increasing or not flags.isin(['0', '1']).all():
            raise ValueError('BaoStock calendar must be ordered, unique and have valid trading flags')
        result = dates[flags == '1'].tolist()
        if not result:
            raise ValueError('BaoStock calendar has no trading sessions')
        return result

    def fetch_instruments(self):
        return self._frame('query_stock_basic')

    def normalize_instruments(self, raw, start, end):
        _range(start, end)
        _require(raw, ['code', 'ipoDate', 'outDate', 'type', 'status'], 'stock basic')
        selected = raw[(raw['type'].astype(str) == '1') & raw.code.astype(str).str.fullmatch(_A_SHARE)].copy()
        if selected.code.duplicated().any():
            raise ValueError('BaoStock basic data repeats an instrument')
        rows = []
        for row in selected.itertuples(index=False):
            listed = _date(row.ipoDate, 'IPO date')
            delisted = None if pd.isna(row.outDate) or str(row.outDate).strip() == '' else _date(row.outDate, 'delisting date')
            if delisted is not None and delisted < listed:
                raise ValueError('BaoStock delisting precedes listing: ' + row.code)
            first, last = max(start, listed), min(end, delisted or end)
            if first <= last:
                rows.append((row.code, first, last))
        if not rows:
            raise ValueError('BaoStock basic data contains no supported A shares in the requested dates')
        return pd.DataFrame(rows, columns=['instrument', 'start', 'end']).sort_values('instrument').reset_index(drop=True)

    def fetch_bars(self, instrument, start, end):
        _range(start, end)
        if not isinstance(instrument, str) or not _A_SHARE.fullmatch(instrument):
            raise ValueError('BaoStock requires a supported A-share identifier such as sh.600000 or sz.000001')
        return {name: self._frame('query_history_k_data_plus', instrument, _FIELDS,
                                 start_date=start, end_date=end, frequency='d', adjustflag=flag)
                for name, flag in [('raw', '3'), ('adjusted', '1')]}

    def normalize_bars(self, payload):
        if set(payload) != {'raw', 'adjusted'}:
            raise ValueError('BaoStock normalization requires raw and adjusted responses')
        keyed = {}
        for name, flag in [('raw', '3'), ('adjusted', '1')]:
            frame = payload[name].copy()
            _require(frame, ['date', 'code', *_OHLC, 'volume', 'adjustflag', 'tradestatus'], name + ' bars')
            if frame.empty:
                raise ValueError('BaoStock ' + name + ' response is empty')
            frame['date'] = frame.date.map(_date)
            if not frame.code.astype(str).str.fullmatch(_A_SHARE).all():
                raise ValueError('BaoStock response contains unsupported instrument identifiers')
            if frame.duplicated(['date', 'code']).any():
                raise ValueError('BaoStock response has duplicate date/instrument rows')
            if not frame.adjustflag.astype(str).eq(flag).all():
                raise ValueError('BaoStock response adjustment flag does not match the request')
            if not frame.tradestatus.astype(str).isin(['0', '1']).all():
                raise ValueError('BaoStock response has unknown trading status')
            frame = frame.set_index(['date', 'code']).sort_index()
            blank_volume = frame.volume.isna() | frame.volume.astype(str).str.strip().eq('')
            frame['volume'] = frame.volume.where(~blank_volume, np.nan)
            frame[_OHLC + ['volume']] = frame[_OHLC + ['volume']].apply(pd.to_numeric, errors='raise')
            allowed_blank = blank_volume & frame.tradestatus.astype(str).eq('0')
            if (not np.isfinite(frame[_OHLC].to_numpy()).all()
                    or (~np.isfinite(frame.volume) & ~allowed_blank).any()):
                raise ValueError('BaoStock source OHLCV must be finite; missing responses are not prices')
            if (frame[_OHLC] <= 0).any().any() or (frame.volume < 0).any():
                raise ValueError('BaoStock source requires positive prices and nonnegative volume')
            keyed[name] = frame
        raw, adjusted = keyed['raw'], keyed['adjusted']
        if not raw.index.equals(adjusted.index):
            raise ValueError('BaoStock raw/adjusted date and instrument rows do not align')
        if (not raw.tradestatus.astype(str).equals(adjusted.tradestatus.astype(str))
                or not np.allclose(raw.volume, adjusted.volume, rtol=0, atol=0, equal_nan=True)):
            raise ValueError('BaoStock raw/adjusted trading status or raw share volume disagree')
        factor = adjusted.close / raw.close
        if not np.isfinite(factor).all() or (factor <= 0).any():
            raise ValueError('BaoStock adjustment factor must be positive and finite')
        # Source raw prices are rounded to four decimals. Compare in raw-price
        # space; do not accept a different factor for each OHLC field.
        if not np.allclose(adjusted[_OHLC].div(factor, axis=0), raw[_OHLC], rtol=1e-8, atol=.00015):
            raise ValueError('BaoStock OHLC do not share one multiplicative adjustment factor')
        suspended = raw.tradestatus.astype(str).eq('0')
        if (raw.loc[suspended, 'volume'].fillna(0) != 0).any():
            raise ValueError('BaoStock suspended rows must have zero raw volume')
        zero_volume_active = ~suspended & raw.volume.eq(0)
        bars = adjusted[_OHLC].copy()
        bars['volume'] = raw.volume.fillna(0) / factor
        bars['factor'] = factor
        bars.loc[suspended | zero_volume_active, _OHLC] = np.nan
        bars.index.names = ['datetime', 'instrument']
        result = normalize(bars.reset_index()).reset_index()
        result.attrs['source_conversion_counts'] = {
            'declared_suspension_rows': int(suspended.sum()),
            'empty_suspension_volume_rows': int((suspended & raw.volume.isna()).sum()),
            'zero_volume_active_rows': int(zero_volume_active.sum()),
        }
        return result
