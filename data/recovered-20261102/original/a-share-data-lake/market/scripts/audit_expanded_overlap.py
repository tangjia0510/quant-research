#!/usr/bin/env python3
"""Read-only local overlap audit; frozen completed status list; no source repair."""
import datetime as dt,gzip,hashlib,json
from pathlib import Path
import numpy as np,pandas as pd,pyarrow.parquet as pq
M=Path(__file__).resolve().parents[1]; H=M/'hf_bulk'
statuses=[];raws=[];records=[]
for f in sorted((M/'status').glob('*.json')):
 s=json.loads(f.read_text())
 if not s.get('historical_partition') or s.get('state') not in ['available','needs_review']:continue
 statuses.append({'file':str(f.relative_to(M)),'sha256':hashlib.sha256(f.read_bytes()).hexdigest()})
 for r in s.get('raw_receipts',[]):
  p=M/r['raw_file'];b=gzip.open(p,'rb').read();assert hashlib.sha256(b).hexdigest()==r['sha256']
  raws.append({'file':r['raw_file'],'sha256':r['sha256']})
  for x in json.loads(b).get('data',{}).get(s['instrument'],{}).get('day',[]):
   if '2019-01-01'<=x[0]<='2026-03-03': records.append([s['instrument'],x[0],*map(float,[x[1],x[3],x[4],x[2],x[5],x[8]])])
cols=['open','high','low','close','volume_lots','amount_cny']
t=pd.DataFrame(records,columns=['instrument','date',*cols]);t.amount_cny*=10000
assert not t.duplicated(['instrument','date']).any()
matched_keys=set();bycode={};examples=[];matches=0;counts=dict.fromkeys(cols,0)
for p in sorted((H/'normalized_prices').glob('*.parquet')):
 for batch in pq.ParquetFile(p).iter_batches(batch_size=100000,columns=['instrument','date',*cols]):
  d=batch.to_pandas();d=d[d.instrument.isin(t.instrument.unique())];d['date']=d.date.astype(str)
  j=d.merge(t,on=['instrument','date'],suffixes=('_hf','_tencent'));matches+=len(j);matched_keys.update(zip(j.instrument,j.date))
  diffs={}
  for c in cols:
   tol=.011 if c!='amount_cny' else np.maximum(100,abs(j[c+'_tencent'])*1e-5)
   diffs[c]=abs(j[c+'_hf']-j[c+'_tencent'])>tol;counts[c]+=int(diffs[c].sum())
  price_diff=diffs['open']|diffs['high']|diffs['low']|diffs['close']; amount_diff=diffs['amount_cny']
  j['price_diff']=price_diff;j['amount_diff']=amount_diff;j['volume_diff']=diffs['volume_lots']
  for code,g in j.groupby('instrument'):
   a=bycode.setdefault(code,{'matched_rows':0,'ohlc_disagreements':0,'amount_disagreements':0,'volume_disagreements':0})
   a['matched_rows']+=len(g)
   for c,o in [('price_diff','ohlc_disagreements'),('amount_diff','amount_disagreements'),('volume_diff','volume_disagreements')]:a[o]+=int(g[c].sum())
  if len(examples)<100:examples+=j[price_diff|amount_diff].head(100-len(examples)).to_dict('records')
 print(p.name,matches,counts,flush=True)
missing=t[[k not in matched_keys for k in zip(t.instrument,t.date)]]
cov=pd.read_csv(H/'coverage.csv');cov['instrument']=cov.code.str[-2:].str.lower()+cov.code.str[:6]
missing=missing.merge(cov[['instrument','min_date','max_date']],on='instrument',how='left')
missing['within_hf_observed_span']=(missing.date>=missing.min_date)&(missing.date<=missing.max_date)
missing['volume_shares']=missing.volume_lots*100
missing['source']='Tencent unadjusted daily OHLCV historical supplement'
missing['price_basis']='unadjusted'
missing['date']=pd.to_datetime(missing.date).dt.date
outdir=M/'historical_supplement';outdir.mkdir(exist_ok=True)
part=outdir/'tencent_hf_missing.parquet';tmp=part.with_suffix('.tmp');missing.to_parquet(tmp,index=False,compression='zstd');tmp.replace(part)
unmatched={'date_counts':{str(k):int(v) for k,v in missing.date.value_counts().sort_index().items()},'within_hf_observed_span_rows':int(missing.within_hf_observed_span.sum()),'supplement_file':str(part.relative_to(M)),'supplement_sha256':hashlib.sha256(part.read_bytes()).hexdigest(),'rows':len(missing),'codes':int(missing.instrument.nunique()),'zero_volume_rows':int((missing.volume_lots==0).sum()),'examples':missing.head(30).to_dict('records'),'meaning':'Real observed Tencent whole-row supplement for keys absent from HF; original HF untouched, no fabricated values'}
out={'unmatched_tencent_overlap':unmatched,'generated_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'snapshot_status_count':len(statuses),'raw_overlap_rows':len(t),'matched_rows':matches,'matched_codes':len(bycode),'field_disagreements':counts,'per_code':bycode,'ohlc_or_amount_examples':examples,'status_lineage':statuses,'raw_lineage':raws,'hf_normalized_manifest_sha256':hashlib.sha256((H/'normalized-manifest.json').read_bytes()).hexdigest(),'tolerance':{'ohlc_cny':.011,'volume_lots':.011,'amount_cny':'max(100, tencent_amount*1e-5)'},'limitations':['Only completed sharded stocks at audit start, not all universe','Tencent tail responses include earlier padded history; no additional network requested','Source-specific volume rounding differences preserved','No data modified or missing dates filled; equality within tolerance not proof of official correctness']}
p=M/'expanded-overlap-audit.json';tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(out,ensure_ascii=False,indent=2,default=str)+'\n');tmp.replace(p)
print(json.dumps({k:v for k,v in out.items() if k not in ['per_code','status_lineage','raw_lineage','ohlc_or_amount_examples']},ensure_ascii=False,default=str),flush=True)
