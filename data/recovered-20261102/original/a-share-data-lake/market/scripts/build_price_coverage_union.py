# PUBLIC SANITIZED COPY (2026-11-06): machine paths generalized; see provenance/publication_transformations.json.
"""Observed key union only, not a canonical mixed-provider price series."""
import csv,gzip,json,datetime as dt,hashlib
from pathlib import Path
import numpy as np,pandas as pd,pyarrow.parquet as pq
M=Path(__file__).resolve().parents[1];rows=list(csv.DictReader((M/'manifests/universe-sharded-with-bse.csv').open()));master={r['instrument'].replace('.',''):r for r in rows};seen={};calendar=(M.parents[1]/'fin_data/legacy-inputs/mixed-source/calendar.txt').read_text().splitlines();epoch=np.datetime64('1970-01-01')
def add(code,dates):
 if code not in master:return
 a=np.array(dates,dtype='datetime64[D]');a=a[(a>=np.datetime64('2019-01-01'))&(a<=np.datetime64('2026-10-30'))].astype('int64');a=np.unique(a);bm=seen.setdefault(code,np.zeros(8192,dtype=np.uint8));np.bitwise_or.at(bm,a//8,(1<<(a%8)).astype(np.uint8))
for p in (M/'hf_bulk/normalized_prices').glob('*.parquet'):
 for batch in pq.ParquetFile(p).iter_batches(batch_size=100000,columns=['instrument','date']):
  d=batch.to_pandas()
  for code,g in d.groupby('instrument'):add(code,g.date)
for code in master:
 p=M/'normalized'/(code+'.csv.gz')
 with gzip.open(p,'rt') as f:add(code,[r['date'] for r in csv.DictReader(f)])
d=pd.read_parquet(M/'historical_supplement/tencent_hf_missing.parquet',columns=['instrument','date'])
for code,g in d.groupby('instrument'):add(code,g.date)
counts=[];gaps=[];total=0
for code,r in master.items():
 bm=seen.get(code,np.zeros(8192,dtype=np.uint8));idx=np.flatnonzero(np.unpackbits(bm,bitorder='little'));dates=[str(epoch+np.timedelta64(int(v),'D')) for v in idx];total+=len(dates);lo=max('2019-01-01',r['ipo_date']) if r.get('ipo_date') else (dates[0] if dates else '2026-10-30');hi=min('2026-10-30',r['delist_date']) if r.get('delist_date') else ('2026-10-30' if r.get('status')=='active' else (dates[-1] if dates else '2019-01-01'));missing=sorted(set(x for x in calendar if lo<=x<=hi)-set(dates));counts.append({'instrument':code,'observed_unique_rows':len(dates),'first_observed':dates[0] if dates else None,'last_observed':dates[-1] if dates else None,'calendar_scope_start':lo,'calendar_scope_end':hi,'missing_sessions':len(missing),'missingness_scope':'lifecycle' if r.get('ipo_date') and (r.get('delist_date') or r.get('status')=='active') else 'observed_span_lifecycle_unknown'});gaps.append({'instrument':code,'missing_dates':missing})
out={'generated_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'universe':len(master),'observed_unique_code_dates':total,'codes_with_rows':sum(x['observed_unique_rows']>0 for x in counts),'codes_observed_target_date':sum(x['last_observed']=='2026-10-30' for x in counts),'within_scope_missing_code_dates':sum(x['missing_sessions'] for x in counts),'gap_free_codes_with_rows':sum(x['observed_unique_rows']>0 and not x['missing_sessions'] for x in counts),'limitations':['Key union only, not mixed OHLC materialization','Includes needs-review vendor rows; observed is not validated tradability','Calendar observed SSEComposite, not certified exchange calendar','Unknown listing boundaries not assigned synthetic dates','Missing days can be suspensions or provider omissions, not filled'],'sources':['hf_bulk/normalized_prices','normalized Tencent raw','historical_supplement/tencent_hf_missing.parquet']}
(M/'observed-coverage-union.json').write_text(json.dumps(out,indent=2)+'\n');(M/'observed-coverage-gaps.json').write_text(json.dumps(gaps)+'\n')
with (M/'observed-coverage-union.csv').open('w') as f:w=csv.DictWriter(f,fieldnames=list(counts[0]));w.writeheader();w.writerows(counts)
print(json.dumps(out))
