#!/usr/bin/env python3
"""Reconstructed portable DuckDB importer and source-isolated retrieval. No network."""
from __future__ import annotations
import argparse
import csv
import datetime as dt
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import re
import sys
import uuid
import duckdb
try:
    from .paths import FIN_DATA, output_path
except ImportError:
    from paths import FIN_DATA, output_path

ROOT = Path(__file__).resolve().parents[1]
VERSION = 'portable-v1-20261106'
EXCHANGE = {'sh': 'SSE', 'sz': 'SZSE', 'bj': 'BSE'}


def utc(value):
    result = dt.datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('Timestamp must include timezone: ' + str(value))
    return result.astimezone(dt.timezone.utc)


def day(value):
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', str(value)):
        raise ValueError('Date must be YYYY-MM-DD: ' + str(value))
    return dt.date.fromisoformat(str(value))


def instrument(value):
    value = str(value).lower().replace('.', '')
    if not re.fullmatch(r'(sh|sz|bj)\d{6}', value):
        raise ValueError('Instrument must include sh/sz/bj prefix: ' + value)
    return value


def number(value):
    if value is None or value == '':
        return None
    result = float(value)
    if not math.isfinite(result):
        raise ValueError('Non-finite numeric value')
    return result


def initialize(db):
    has_version = db.execute("SELECT count(*) FROM information_schema.tables WHERE table_name='schema_version'").fetchone()[0]
    if has_version and db.execute('SELECT version FROM schema_version').fetchall() != [(1,)]:
        raise ValueError('Unsupported schema version; no changes made')
    db.execute((ROOT / 'sql/001_portable_duckdb_RECONSTRUCTED.sql').read_text())
    if db.execute('SELECT version FROM schema_version').fetchall() != [(1,)]:
        raise ValueError('Unsupported schema version')


def read_csv(path):
    payload = Path(path).read_bytes()
    decoded = gzip.decompress(payload) if str(path).endswith('.gz') else payload
    reader = csv.DictReader(io.StringIO(decoded.decode('utf-8-sig')))
    if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
        raise ValueError('Missing or duplicate CSV headers')
    rows = list(reader)
    if any(None in row for row in rows):
        raise ValueError('CSV has unexpected extra fields')
    return payload, rows


def metadata(meta):
    meta = dict(meta)
    for key in ('source', 'source_revision', 'retrieved_at'):
        if not isinstance(meta.get(key), str) or not meta[key].strip():
            raise ValueError('Metadata requires non-empty ' + key)
    retrieved = utc(meta['retrieved_at'])
    # A new local observation cannot claim to have been known in the past.
    available = utc(meta.get('available_at', meta['retrieved_at']))
    if available < retrieved:
        raise ValueError('available_at cannot predate retrieved_at')
    if retrieved > dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=5):
        raise ValueError('retrieved_at is in the future')
    meta['retrieved_at'], meta['available_at'] = retrieved.isoformat(), available.isoformat()
    return meta


def ingest(db, kind, path, meta):
    """Atomic append-only import. Identical bytes+metadata are idempotent."""
    meta = metadata(meta)
    payload, rows = read_csv(path)
    if not rows:
        raise ValueError('Empty files are not successful data batches')
    digest = hashlib.sha256(payload).hexdigest()
    serialized = json.dumps(meta, sort_keys=True, ensure_ascii=False)
    batch = hashlib.sha256((kind + '\n' + VERSION + '\n' + digest + '\n' + serialized).encode()).hexdigest()
    if db.execute('SELECT count(*) FROM ingestion_batch WHERE batch_id=?', [batch]).fetchone()[0]:
        return {'batch_id': batch, 'rows': len(rows), 'already_imported': True}
    normalized = []
    table = {'calendar': 'trading_calendar', 'instruments': 'instrument_lifecycle', 'prices': 'daily_price'}.get(kind)
    if not table:
        raise ValueError('Unknown import kind')
    for row in rows:
        if kind == 'calendar':
            if row['is_open'] not in ('0', '1'):
                raise ValueError('is_open must be 0 or 1; include closed dates to certify calendar coverage')
            normalized.append((batch, row['exchange'], day(row['date']), row['is_open'] == '1'))
        elif kind == 'instruments':
            code = instrument(row['instrument'])
            if row['exchange'] != EXCHANGE[code[:2]]:
                raise ValueError('Instrument and exchange mismatch')
            normalized.append((batch, code, row['exchange'], day(row['listed_on']), day(row['delisted_on']) if row.get('delisted_on') else None))
        else:
            observed_date = day(row['date'])
            retrieved_local_date = utc(meta['retrieved_at']).astimezone(dt.timezone(dt.timedelta(hours=8))).date()
            if observed_date >= retrieved_local_date:
                raise ValueError('Daily import requires completed prior Asia/Shanghai dates; no future/partial current-day bars')
            basis = meta.get('price_basis', 'unadjusted')
            adjustment = meta.get('adjustment_id', 'none')
            if basis != 'unadjusted':
                raise ValueError('This importer accepts raw prices/shares only; adjusted volumes need a separate reviewed mapping')
            if meta.get('volume_unit') != 'shares' or meta.get('amount_unit') != 'CNY':
                raise ValueError('Metadata must declare volume_unit=shares and amount_unit=CNY')
            for key in ('open', 'high', 'low', 'close', 'volume_shares', 'amount_cny'):
                if key not in row:
                    raise ValueError('Missing canonical column ' + key)
            normalized.append((batch, instrument(row['instrument']), day(row['date']), basis, adjustment,
                               *[number(row[k]) for k in ('open','high','low','close','volume_shares','amount_cny')],
                               number(row.get('prev_close_reported')), row.get('trade_status') or 'unknown'))
    db.execute('BEGIN TRANSACTION')
    try:
        db.execute('INSERT INTO ingestion_batch VALUES (?,?,?,?,?,?,?,?,?,?)',
                   [batch, kind, meta['source'], meta['source_revision'], utc(meta['retrieved_at']), utc(meta['available_at']),
                    digest, VERSION, len(rows), serialized])
        db.executemany('INSERT INTO ' + table + ' VALUES (' + ','.join('?' for _ in normalized[0]) + ')', normalized)
        db.execute('COMMIT')
    except BaseException:
        db.execute('ROLLBACK')
        raise
    return {'batch_id': batch, 'rows': len(rows), 'already_imported': False}


def fetch_series(db, *, code, start, end, calendar_batch, instruments_batch, sources, as_of, allow_gaps=False):
    """One vendor + one snapshot per result. Never blend numeric fields or forward-fill."""
    code, start, end, as_of = instrument(code), day(start), day(end), utc(as_of)
    if end >= as_of.astimezone(dt.timezone(dt.timedelta(hours=8))).date():
        raise ValueError('Query end must precede as-of Asia/Shanghai date; no future or partial daily bars')
    if start > end or not sources or len(sources) != len(set(sources)):
        raise ValueError('Invalid date range or source priority list')
    for batch, kind in ((calendar_batch, 'calendar'), (instruments_batch, 'instruments')):
        row = db.execute('SELECT kind,available_at FROM ingestion_batch WHERE batch_id=?', [batch]).fetchone()
        if row is None or row[0] != kind or row[1] > as_of:
            raise ValueError(kind + ' batch missing, wrong kind, or not known as of requested timestamp')
    life = db.execute('SELECT exchange,listed_on,delisted_on FROM instrument_lifecycle WHERE batch_id=? AND instrument=?', [instruments_batch, code]).fetchone()
    if not life:
        raise ValueError('Instrument is absent from explicit lifecycle snapshot; no inferred universe')
    lower, upper = max(start, life[1]), min(end, life[2] or end)
    if lower > upper:
        raise ValueError('Requested range is outside listing lifecycle')
    calendar = db.execute('SELECT date,is_open FROM trading_calendar WHERE batch_id=? AND exchange=? AND date BETWEEN ? AND ? ORDER BY date', [calendar_batch, life[0], lower, upper]).fetchall()
    if len(calendar) != (upper-lower).days + 1:
        raise ValueError('Calendar must cover every civil date (including weekends/holidays) in lifecycle-clipped range')
    expected = [row[0] for row in calendar if row[1]]
    if not expected:
        raise ValueError('No open sessions in requested range')
    expected_set, attempts, selected, observations = set(expected), [], None, {}
    for source in sources:
        # Latest eligible snapshot for this instrument, not a mix across snapshots.
        batches = db.execute('''SELECT DISTINCT b.batch_id,b.source_revision,b.available_at
            FROM ingestion_batch b JOIN daily_price p USING(batch_id)
            WHERE b.source=? AND b.kind='prices' AND b.available_at<=? AND p.instrument=?
              AND p.price_basis='unadjusted' AND p.adjustment_id='none'
            ORDER BY b.available_at DESC,b.batch_id DESC LIMIT 1''', [source, as_of, code]).fetchall()
        if not batches:
            attempts.append({'source': source, 'status': 'no_eligible_snapshot'})
            continue
        batch, revision, known = batches[0]
        rows = db.execute('''SELECT date,open,high,low,close,volume_shares,amount_cny,trade_status
            FROM daily_price WHERE batch_id=? AND instrument=? AND price_basis='unadjusted'
              AND date BETWEEN ? AND ? ORDER BY date''', [batch, code, lower, upper]).fetchall()
        off_calendar = [str(r[0]) for r in rows if r[0] not in expected_set]
        covered = {r[0] for r in rows} & expected_set
        missing = sorted(expected_set - covered)
        attempt = {'source': source, 'batch_id': batch, 'source_revision': revision,
                   'expected_sessions': len(expected), 'present_sessions': len(covered),
                   'missing_dates': [str(x) for x in missing], 'off_calendar_dates': off_calendar,
                   'available_at': known.isoformat()}
        if off_calendar or not covered or (missing and not allow_gaps):
            attempt['status'] = 'rejected_calendar' if off_calendar else 'rejected_incomplete'
            attempts.append(attempt)
            continue
        attempt['status'] = 'selected_with_gaps' if missing else 'selected_complete'
        attempts.append(attempt)
        selected = attempt
        observations = {r[0]: dict(zip(('open','high','low','close','volume_shares','amount_cny','trade_status'), r[1:])) for r in rows}
        break
    output = []
    if selected:
        for date in expected:
            item = observations.get(date)
            output.append({'date': str(date), **(item or {k: None for k in ('open','high','low','close','volume_shares','amount_cny')}),
                           'observation_state': 'observed' if item else 'missing_unknown'})
    decision = {'status': 'selected' if selected else 'unavailable', 'selection': selected,
                'attempts': attempts, 'rows': output,
                'warning': 'Coverage is not tradability, execution eligibility, original historical availability, or total-return certification.'}
    request = {'instrument': code, 'start': str(start), 'end': str(end), 'effective_start': str(lower), 'effective_end': str(upper),
               'calendar_batch': calendar_batch, 'instruments_batch': instruments_batch, 'sources': sources,
               'as_of': as_of.isoformat(), 'allow_gaps': allow_gaps, 'price_basis': 'unadjusted'}
    query_id = str(uuid.uuid4())
    # Audit records selection metadata, not another copy of prices.
    db.execute('INSERT INTO retrieval_audit VALUES (?,?,?,?)', [query_id, dt.datetime.now(dt.timezone.utc), json.dumps(request),
               json.dumps({k:v for k,v in decision.items() if k != 'rows'})])
    return {'query_id': query_id, 'request': request, **decision}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--db', default=str(FIN_DATA / 'research.duckdb'), help='Database path under repository-root fin_data/')
    sub = p.add_subparsers(dest='command', required=True)
    sub.add_parser('init')
    for kind in ('calendar','instruments','prices'):
        c = sub.add_parser('import-' + kind)
        c.add_argument('--csv', required=True)
        c.add_argument('--metadata', required=True)
    c = sub.add_parser('query')
    for arg in ('instrument','start','end','calendar-batch','instruments-batch','sources','as-of'):
        c.add_argument('--' + arg, required=True)
    c.add_argument('--allow-gaps', action='store_true')
    args = p.parse_args(argv)
    database_path = output_path(args.db)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(database_path)) as db:
        initialize(db)
        if args.command == 'init':
            result = {'schema_version': 1, 'status': 'empty_schema_ready'}
        elif args.command.startswith('import-'):
            result = ingest(db, args.command.removeprefix('import-'), args.csv, json.loads(Path(args.metadata).read_text()))
        else:
            result = fetch_series(db, code=args.instrument, start=args.start, end=args.end,
                                  calendar_batch=args.calendar_batch, instruments_batch=args.instruments_batch,
                                  sources=args.sources.split(','), as_of=args.as_of, allow_gaps=args.allow_gaps)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2 if result.get('status') == 'unavailable' else 0


if __name__ == '__main__':
    sys.exit(main())
