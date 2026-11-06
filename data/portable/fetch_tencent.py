#!/usr/bin/env python3
"""NEW, opt-in Tencent daily snapshot downloader. Never runs during init/tests/import."""
from __future__ import annotations
import argparse
import csv
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
import re
import time
import urllib.error
import urllib.parse
import urllib.request
try:
    from .paths import FIN_DATA, output_path
except ImportError:
    from paths import FIN_DATA, output_path

ENDPOINT = 'https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get'
BLOCKED = {401, 403, 429, 567}
class AccessRestricted(ValueError):
    pass


FIELDS = ['date','instrument','open','high','low','close','volume_shares','amount_cny','trade_status']


def parse_rows(payload, code, start, end):
    if not re.fullmatch(r'(sh(?:60\d{4}|688\d{3})|sz(?:00\d{4}|30\d{4}))', code):
        raise ValueError('Portable unit mapping supports ordinary SSE/SZSE A shares only; no inferred BSE/CDR units')
    text = payload.decode('utf-8', errors='replace') if isinstance(payload, bytes) else payload
    if any(marker in text.lower() for marker in ('captcha','access denied','forbidden','验证码','访问受限','禁止访问','访问频繁')):
        raise AccessRestricted('Response contains an access restriction or CAPTCHA; stop source')
    obj = json.loads(text)
    if isinstance(obj, dict) and obj.get('code') not in (0, None):
        raise AccessRestricted('Source returned a nonzero refusal/error code; stop pending review')
    if not isinstance(obj, dict) or obj.get('code') != 0 or not isinstance(obj.get('data', {}).get(code, {}).get('day'), list):
        raise ValueError('Unknown response contract; requires review, not automatic retry')
    multiplier = 1 if code.startswith('sh688') else 100
    rows = {}
    for row in obj['data'][code]['day']:
        if not isinstance(row, list) or len(row) < 6:
            raise ValueError('Malformed daily row')
        date = dt.date.fromisoformat(row[0]).isoformat()
        if not start <= date <= end:
            # The original collector documented padded rows outside short windows.
            # Preserve them in raw but never include them in the requested projection.
            continue
        op, close, high, low, volume = map(float, row[1:6])
        amount = float(row[8]) * 10000 if len(row) > 8 and row[8] not in ('', None) else None
        if not all(math.isfinite(x) for x in (op, close, high, low, volume)) or low <= 0 or volume < 0:
            raise ValueError('Invalid finite positive OHLC/nonnegative volume contract')
        if high < max(op, close) or low > min(op, close) or high < low:
            raise ValueError('OHLC bounds failed')
        shares = volume * multiplier
        if amount is not None:
            if not math.isfinite(amount) or amount < 0 or (amount > 0 and shares == 0):
                raise ValueError('Invalid amount')
            if amount > 0 and shares > 0 and not low * .98 <= amount/shares <= high * 1.02:
                raise ValueError('Amount/volume unit cross-check failed; do not guess conversion')
        result = dict(zip(FIELDS, [date,code,op,high,low,close,shares,amount,'unknown']))
        if date in rows and rows[date] != result:
            raise ValueError('Conflicting duplicate daily row')
        rows[date] = result
    return rows


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, 'Redirect requires endpoint review', headers, fp)


def download(code, start, end, destination, source_root=None):
    start_date, end_date = dt.date.fromisoformat(start), dt.date.fromisoformat(end)
    if start_date > end_date or end_date >= dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date():
        raise ValueError('Require start<=end and completed prior Asia/Shanghai civil dates; no partial current-day bars')
    # Validate support before any network or filesystem side effects.
    parse_rows(json.dumps({'code':0,'data':{code:{'day':[]}}}), code, start, end)
    destination = Path(destination).expanduser().resolve()
    source_root = Path(source_root) if source_root is not None else FIN_DATA / 'tencent'
    source_marker = source_root / 'ACCESS_BLOCKED.json'
    if source_marker.exists() or (destination / 'ACCESS_BLOCKED.json').exists():
        raise RuntimeError('Existing access-denial marker: stop; resolve authorization before any retry')
    if destination.exists() and any(destination.iterdir()):
        raise ValueError('Use a new empty private snapshot directory; existing snapshots are immutable')
    destination.mkdir(parents=True, exist_ok=True)
    source_root.mkdir(parents=True, exist_ok=True)
    def stop_source(reason, status=None):
        evidence = {'source':'tencent','http_status':status,'reason':reason,
                    'recorded_at':dt.datetime.now(dt.timezone.utc).isoformat(),
                    'action':'Stop this source across all snapshots. Resolve authorization/review first; no automatic unlock, bypass, or fallback.'}
        source_marker.write_text(json.dumps(evidence, ensure_ascii=False, indent=2)+'\n')
        (destination / 'ACCESS_BLOCKED.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2)+'\n')
    opener, receipts, merged = urllib.request.build_opener(NoRedirect), [], {}
    cursor = start_date
    while cursor <= end_date:
        window_end = min(end_date, dt.date(cursor.year, 12, 31))
        url = ENDPOINT + '?' + urllib.parse.urlencode({'param':f'{code},day,{cursor},{window_end},640,'})
        if receipts:
            time.sleep(1.1)
        try:
            with opener.open(urllib.request.Request(url, headers={'User-Agent':'quant-research-portable/1.0'}), timeout=30) as response:
                body = response.read(32*1024*1024 + 1)
                if len(body) > 32*1024*1024:
                    raise ValueError('Response exceeds 32 MiB cap')
        except urllib.error.HTTPError as exc:
            if exc.code in BLOCKED:
                stop_source('HTTP access restriction', exc.code)
            raise
        raw_name = f'raw-{cursor.year}.json'
        (destination / raw_name).write_bytes(body)
        receipt = {'url':url, 'file':raw_name, 'sha256':hashlib.sha256(body).hexdigest(),
                   'retrieved_at':dt.datetime.now(dt.timezone.utc).isoformat(), 'state':'received_unvalidated'}
        receipt_file = destination / f'receipt-{cursor.year}.json'
        receipt_file.write_text(json.dumps(receipt, indent=2)+'\n')
        try:
            rows = parse_rows(body, code, str(cursor), str(window_end))
        except (ValueError, TypeError, KeyError) as exc:
            receipt.update(state='rejected', reason=type(exc).__name__)
            receipt_file.write_text(json.dumps(receipt, indent=2)+'\n')
            if isinstance(exc, AccessRestricted):
                stop_source(str(exc), 200)
            raise
        for date, row in rows.items():
            if date in merged and merged[date] != row:
                raise ValueError('Cross-window duplicate conflict')
            merged[date] = row
        receipt.update(state='normalized', rows=len(rows))
        receipt_file.write_text(json.dumps(receipt, indent=2)+'\n')
        receipts.append(receipt)
        cursor = window_end + dt.timedelta(days=1)
    if not merged:
        raise ValueError('Empty response set, not successful acquisition')
    with (destination / 'prices.csv').open('w', newline='', encoding='utf-8') as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(merged[date] for date in sorted(merged))
    receipt_digest = hashlib.sha256(json.dumps([r['sha256'] for r in receipts]).encode()).hexdigest()
    meta = {'source':'tencent','source_revision':'response-set-sha256:'+receipt_digest,
            'retrieved_at':receipts[-1]['retrieved_at'], 'price_basis':'unadjusted','adjustment_id':'none',
            'volume_unit':'shares','amount_unit':'CNY','normalizer':'portable-tencent-v1-20261106',
            'instrument':code,'requested_start':start,'requested_end':end,
            'rights':'Public access is not data redistribution permission. Snapshot is not PIT-certified.',
            'receipts':receipts}
    (destination / 'metadata.json').write_text(json.dumps(meta, indent=2, ensure_ascii=False)+'\n')
    return {'rows':len(merged),'metadata_file':str(destination / 'metadata.json'), 'coverage':'not checked; import an explicit exchange calendar and lifecycle'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('instrument','start','end'):
        parser.add_argument('--'+name, required=True)
    parser.add_argument('--out', help='New snapshot directory under repository-root fin_data/')
    parser.add_argument('--source-access-reviewed', action='store_true', help='Confirm rights/access have been reviewed. Not a grant or acceptance of supplier terms.')
    args = parser.parse_args()
    if not args.source_access_reviewed:
        parser.error('Review source access/rights first, then explicitly pass --source-access-reviewed')
    destination = output_path(args.out or (FIN_DATA / 'tencent' / args.instrument / dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')))
    print(json.dumps(download(args.instrument, args.start, args.end, destination), ensure_ascii=False))


if __name__ == '__main__':
    main()
