#!/usr/bin/env python3
import csv,datetime as dt,hashlib,json
from pathlib import Path
import numpy as np,pandas as pd,pyarrow.parquet as pq
R=Path(__file__).resolve().parents[1]/'hf_features';p=json.loads((R/'progress.json').read_text());assert p['complete']
files=sorted((R/'raw').glob('*.parquet'));stats={};bitmaps={};nulls={};flags={};exchanges={};boards={};rows=0;dups=0;invalid_dates=0;bad_ohlc=0;schema=None
for f in files:
 receipt=json.loads((R/'metadata'/(f.name+'.json')).read_text());h=hashlib.sha256()
 with f.open('rb') as z:
  for b in iter(lambda:z.read(8*1024*1024),b''):h.update(b)
 assert h.hexdigest()==receipt['sha256']
 pf=pq.ParquetFile(f);schema={str(x.name):str(x.type) for x in pf.schema_arrow}
 for batch in pf.iter_batches(batch_size=100000):
  d=batch.to_pandas();rows+=len(d)
  for col in d:nulls[col]=nulls.get(col,0)+int(d[col].isna().sum())
  val=d[['open','high','low','close']].to_numpy();ok=np.isfinite(val).all(1)&(val>0).all(1)&(val[:,2]<=np.minimum(val[:,0],val[:,3])+1e-7)&(val[:,1]>=np.maximum(val[:,0],val[:,3])-1e-7);bad_ohlc+=int((~ok).sum())
  for name in ['is_st','is_paused']:
   if name in d:
    dest=flags.setdefault(name,{})
    for v,n in d[name].fillna('<NULL>').value_counts().items():dest[str(v)]=dest.get(str(v),0)+int(n)
  for name,dest in [('exchange',exchanges),('market',boards)]:
   if name in d:
    for v,n in d[name].fillna('<NULL>').value_counts().items():dest[str(v)]=dest.get(str(v),0)+int(n)
  for code,g in d.groupby('code',sort=False,dropna=False):
   code=str(code);dates=pd.to_datetime(g.date,errors='coerce');days=dates.to_numpy(dtype='datetime64[D]').astype('int64');valid=(days>=0)&(days<65536);invalid_dates+=int((~valid).sum());days=days[valid];u=np.unique(days);bitmap=bitmaps.setdefault(code,np.zeros(8192,dtype=np.uint8));idx=u//8;mask=(1<<(u%8)).astype(np.uint8);old=(bitmap[idx]&mask)!=0;dup=int(len(days)-len(u)+old.sum());dups+=dup;np.bitwise_or.at(bitmap,idx,mask)
   s=stats.setdefault(code,{'rows':0,'unique_dates':0,'duplicate_dates':0,'first_date':'9999','last_date':'0000'});s['rows']+=len(g);s['unique_dates']+=len(u)-int(old.sum());s['duplicate_dates']+=dup
   if valid.any():s['first_date']=min(s['first_date'],dates.min().date().isoformat());s['last_date']=max(s['last_date'],dates.max().date().isoformat())
 print(json.dumps({'file':f.name,'rows':rows,'codes':len(stats),'duplicates':dups}),flush=True)
with (R/'coverage.csv').open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=['code','rows','unique_dates','duplicate_dates','first_date','last_date']);w.writeheader();w.writerows({'code':c,**s} for c,s in sorted(stats.items()))
a={'state':'structurally_audited_raw_feature_snapshot','time_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'rows':rows,'unique_codes':len(stats),'first_date':min(x['first_date'] for x in stats.values()),'last_date':max(x['last_date'] for x in stats.values()),'duplicate_code_dates':dups,'invalid_dates':invalid_dates,'nonpositive_nonfinite_or_outofbounds_ohlc_rows':bad_ohlc,'schema':schema,'null_counts':nulls,'flag_counts':flags,'exchange_rows':exchanges,'board_rows':boards,'price_basis':'QFQ, source snapshot-specific; not raw or PIT','field_units':'Not specified by source card. Kept unconverted. Sibling dataset unit declarations do not transfer automatically.','limitations':['Not latest data; date endpoint is actual audited observation','ST and suspension are vendor flags, not independently exchange-certified or PIT','Corporate actions/limits may use a different price basis; do not join or use for simulation without validation','Flow/valuation/share fields have undocumented units in current card; no derived money/volume normalization claimed','Parquet hashes/row structure do not establish economic correctness or source licensing rights']}
(R/'audit.json').write_text(json.dumps(a,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in a.items() if k not in ['schema','null_counts']},ensure_ascii=False),flush=True)
