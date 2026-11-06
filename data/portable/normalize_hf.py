#!/usr/bin/env python3
"""Convert a locally held, audited HF normalized Parquet into canonical CSV.

This accepts the historical normalizer's output, NOT arbitrary raw vendor files.
No downloads, duplicate repairs, unit guessing, or historical PIT claims.
"""
import argparse
import csv
import datetime as dt
import hashlib
import json
from pathlib import Path
import duckdb
try:
    from .paths import FIN_DATA, output_path
except ImportError:
    from paths import FIN_DATA, output_path


def normalize(path, out, revision, retrieved_at):
    path, out = Path(path), Path(out)
    timestamp = dt.datetime.fromisoformat(retrieved_at.replace('Z','+00:00'))
    if timestamp.tzinfo is None:
        raise ValueError('retrieved_at must contain timezone')
    if not revision.strip():
        raise ValueError('Pinned source revision is required')
    if out.exists() and any(out.iterdir()):
        raise ValueError('Use a new empty output directory')
    with duckdb.connect(':memory:') as db:
        db.read_parquet(str(path)).create_view('input')
        columns = {row[0] for row in db.execute('DESCRIBE input').fetchall()}
        required = {'date','instrument','open','high','low','close','prev_close_reported','volume_shares','amount_cny','source_revision'}
        if not required <= columns:
            raise ValueError('Require historical normalized HF schema, not raw vendor schema; missing '+str(sorted(required-columns)))
        revisions = db.execute('SELECT DISTINCT source_revision FROM input').fetchall()
        if revisions != [(revision,)]:
            raise ValueError('Declared revision does not match every row in Parquet')
        if db.execute('SELECT count(*) FROM (SELECT instrument,date,count(*) AS n FROM input GROUP BY ALL HAVING count(*)>1)').fetchone()[0]:
            raise ValueError('Duplicate keys require explicit audit; never silently drop conflicts')
        out.mkdir(parents=True,exist_ok=True)
        columns = ['date','instrument','open','high','low','close','prev_close_reported','volume_shares','amount_cny']
        reader = db.execute('SELECT '+','.join(columns)+' FROM input ORDER BY instrument,date')
        count = 0
        with (out/'prices.csv').open('w', newline='', encoding='utf-8') as file:
            writer = csv.writer(file);writer.writerow(columns)
            while rows := reader.fetchmany(10000):
                writer.writerows(rows);count += len(rows)
        if not count:
            raise ValueError('Empty input is not a successful snapshot')
    digest = hashlib.sha256()
    with path.open('rb') as file:
        for chunk in iter(lambda:file.read(1024*1024),b''):
            digest.update(chunk)
    meta = {'source':'hf:ellendan/a-share-prices','source_revision':revision,'retrieved_at':retrieved_at,
            'price_basis':'unadjusted','adjustment_id':'none','volume_unit':'shares','amount_unit':'CNY',
            'input_parquet_sha256':digest.hexdigest(),'normalizer':'portable-hf-csv-v1-20261106',
            'note':'No duplicate repair or PIT certification. Upstream normalized schema and units must be audited.'}
    (out/'metadata.json').write_text(json.dumps(meta, indent=2)+'\n')
    return count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('parquet','revision','retrieved-at'):
        parser.add_argument('--'+name, required=True)
    parser.add_argument('--out', help='New snapshot directory under repository-root fin_data/')
    args = parser.parse_args()
    destination = output_path(args.out or (FIN_DATA / 'hf-normalized' / dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')))
    print(json.dumps({'rows':normalize(args.parquet,destination,args.revision,args.retrieved_at)}))


if __name__ == '__main__':
    main()
