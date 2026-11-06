#!/usr/bin/env python3
# PUBLIC SANITIZED COPY (2026-11-06): machine paths generalized; see provenance/publication_transformations.json.
import csv,datetime as dt,gzip,hashlib,json,math
from pathlib import Path
import numpy as np,pandas as pd,pyarrow.parquet as pq
R=Path(__file__).resolve().parents[1]/'hf_bulk';M=R.parent;C=M.parents[1]/'fin_data/legacy-inputs/mixed-source'
files=sorted((R/'raw').glob('*.parquet'));progress=json.loads((R/'progress.json').read_text());assert progress['complete'] and len(files)==7
stats={};bitmaps={};field_nulls={};exchanges={};boards={};rows=0;duplicates=0;bad_prices=0;bad_volume=0;amount_anomaly=0;dateinvalid=0
sample_codes=json.loads((C.parent/'selection.json').read_text())['instruments'];sample_codes={c[3:]+'.'+c[:2].upper() for c in sample_codes};truth={}
for code in sample_codes:
 inst=code[-2:].lower()+code[:6]
 for p in C.glob(inst+'-20*.json'):
  data=json.loads(p.read_text()).get('data',{}).get(inst,{}).get('day',[])
  for r in data:
   if '2019-01-01'<=r[0]<='2026-10-30':truth[(code,r[0])]=tuple(map(float,[r[1],r[3],r[4],r[2],r[5],r[8]]))
compared=0;compcounts={k:0 for k in ['open','high','low','close','volume_lots','amount_cny']};examples=[]
for p in files:
 receipt=json.loads((R/'metadata'/(p.name+'.json')).read_text());h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
 assert h.hexdigest()==receipt['sha256']
 pf=pq.ParquetFile(p)
 for batch in pf.iter_batches(batch_size=100000):
  d=batch.to_pandas();rows+=len(d)
  for col in d:field_nulls[col]=field_nulls.get(col,0)+int(d[col].isna().sum())
  vals=d[['open','high','low','close']].to_numpy();v=d.volume.to_numpy();a=d.turnover.to_numpy()
  valid=np.isfinite(vals).all(axis=1)&(vals>0).all(axis=1)&(vals[:,2]<=np.minimum(vals[:,0],vals[:,3])+1e-7)&(vals[:,1]>=np.maximum(vals[:,0],vals[:,3])-1e-7)
  bad_prices+=int((~valid).sum());bad_volume+=int((~np.isfinite(v)|(v<0)).sum())
  with np.errstate(divide='ignore',invalid='ignore'):vw=a*1000/(v*100)
  amount_anomaly+=int(((v>0)&(a>0)&np.isfinite(vw)&((vw<vals[:,2]*.98)|(vw>vals[:,1]*1.02))).sum())
  for key,target in [('exchange',exchanges),('market',boards)]:
   for k,n in d[key].fillna('<null>').value_counts().items():target[str(k)]=target.get(str(k),0)+int(n)
  for code,g in d.groupby('code',sort=False,dropna=False):
   code=str(code);dates=g.date.astype(str);st=stats.setdefault(code,{'rows':0,'min_date':'9999','max_date':'0000','unique_dates':0,'duplicate_dates':0})
   st['rows']+=len(g);st['min_date']=min(st['min_date'],dates.min());st['max_date']=max(st['max_date'],dates.max())
   dtv=pd.to_datetime(dates,errors='coerce').to_numpy(dtype='datetime64[D]').astype('int64');ok=(dtv>=0)&(dtv<65536);dateinvalid+=int((~ok).sum());dtv=dtv[ok]
   unique=np.unique(dtv);bitmap=bitmaps.setdefault(code,np.zeros(8192,dtype=np.uint8));idx=unique//8;masks=(1<<(unique%8)).astype(np.uint8)
   old=(bitmap[idx]&masks)!=0;dups=int(len(dtv)-len(unique)+old.sum());duplicates+=dups;st['duplicate_dates']+=dups;st['unique_dates']+=int(len(unique)-old.sum());np.bitwise_or.at(bitmap,idx,masks)
  for r in d[d.code.isin(sample_codes)].itertuples(index=False):
   key=(r.code,r.date)
   if key not in truth:continue
   t=truth[key];x=(r.open,r.high,r.low,r.close,r.volume,r.turnover*1000);base=(*t[:5],t[5]*10000);compared+=1
   diff=[]
   for i,k in enumerate(compcounts):
    tol=.011 if i<5 else max(100,abs(base[i])*1e-5)
    if not math.isfinite(x[i]) or abs(x[i]-base[i])>tol:compcounts[k]+=1;diff.append(k)
   if diff and len(examples)<30:examples.append({'code':r.code,'date':r.date,'fields':diff,'hf':x,'tencent':base})
 print(json.dumps({'file':p.name,'rows_scanned':rows,'codes':len(stats),'duplicates':duplicates,'comparison_rows':compared}),flush=True)
with (R/'coverage.csv').open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=['code','rows','unique_dates','duplicate_dates','min_date','max_date']);w.writeheader();w.writerows({'code':c,**s} for c,s in sorted(stats.items()))
result={'state':'audited_source_snapshot','asof_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'files':len(files),'rows':rows,'unique_codes':len(stats),'date_min':min(x['min_date'] for x in stats.values()),'date_max':max(x['max_date'] for x in stats.values()),'duplicate_code_dates':duplicates,'invalid_dates':dateinvalid,'invalid_ohlc_rows':bad_prices,'invalid_volume_rows':bad_volume,'amount_volume_vwap_outside_2pct_range':amount_anomaly,'field_null_counts':field_nulls,'exchange_row_counts':exchanges,'board_row_counts':boards,'cross_source_check':{'sample':'Prior frozen30 code-stratified pre2019 research sample; not random representative','matched_rows':compared,'disagreement_counts':compcounts,'examples':examples,'does_not_authorize_automatic_merge':True},'limitations':['Data source updated through observed max date only, not 2026-10-30','MIT is publisher claim, not underlying vendor rights verification','Historical source changes and missing ST field; no PIT certification','No absent date filled; vendor missing/suspended records cannot be distinguished','Reported numerical anomalies remain in original parquet; quarantine for research validation, do not silently repair']}
(R/'audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n');print(json.dumps({k:v for k,v in result.items() if k not in ['field_null_counts','cross_source_check']},ensure_ascii=False),flush=True)
