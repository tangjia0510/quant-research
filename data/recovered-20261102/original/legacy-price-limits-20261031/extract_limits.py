# PUBLIC SANITIZED COPY (2026-11-06): machine paths generalized; see provenance/publication_transformations.json.
from pathlib import Path
import duckdb,csv,json
B=Path(__file__).parent
inst=[r['instrument'] for r in csv.DictReader(open(B.parents[1]/'enrichment/trading_status/listing_delisting.csv'))]
codes=[x[2:]+'.'+x[:2] for x in inst]
c=duckdb.connect();c.execute('SET threads=4');c.execute('SET memory_limit=\'1GB\'')
c.execute('CREATE TEMP TABLE target(code VARCHAR)');c.executemany('INSERT INTO target VALUES (?)',[(s,) for s in codes])
c.execute("CREATE TEMP TABLE raw AS SELECT code,date,open,high,low,close,prev_close,high_limit,low_limit FROM read_parquet('fin_data/legacy-inputs/hf_limits_raw/*.parquet') WHERE date>='2021-06-01' AND date<='2026-10-30' AND code IN (select code from target)")
print(c.execute('select count(*),count(distinct code),min(date),max(date) from raw').fetchall(),flush=True)
out=B/'reported_daily_limits.parquet';c.execute(f"COPY (SELECT right(code,2)||left(code,6) AS instrument, date, high_limit AS upper_limit, low_limit AS lower_limit, open, high, low, close, prev_close, CASE WHEN high_limit IS NULL OR low_limit IS NULL THEN 'missing' WHEN high_limit>=100000 THEN 'sentinel_or_unbounded_unverified' WHEN high_limit<=low_limit OR low_limit<=0 THEN 'invalid' WHEN high>high_limit+0.011 OR low<low_limit-0.011 THEN 'ohlc_outside_limits_review' ELSE 'source_reported_numeric' END AS quality FROM raw ORDER BY code,date) TO '{out}' (FORMAT parquet)")
checks={
 'counts':c.execute('select count(*),count(distinct code),min(date),max(date) from raw').fetchall(),
 'duplicates':c.execute('select count(*) from (select code,date,count(*) n from raw group by code,date having count(*)>1)').fetchone()[0],
 'quality':c.execute('select quality,count(*) from read_parquet(?) group by quality',[str(out)]).fetchall(),
 'definition':'Limits reported by public dataset publisher, attributed to Tushare stk_limit in publisher pipeline. Not reconstructed by us, not exchange-certified. Dataset mainboard-only; source actual max date may be stale. Name column not used for historical ST because current metadata may be backfilled.'}
(B/'limits_checks.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2));print(checks,flush=True)
c.execute(f"COPY (SELECT * FROM read_parquet('{out}') WHERE quality<>'source_reported_numeric') TO '{B/'limit_anomalies.csv'}' (HEADER,DELIMITER ',')")
