"""Project status fields only after exhaustive duplicate-key consistency audit."""
import pandas as pd, pyarrow.parquet as pq, json, hashlib,datetime,gc
from pathlib import Path
B=Path(__file__).resolve().parents[1];S=B.parent/'market/hf_features';O=B/'normalized/hf_status';O.mkdir(exist_ok=True)
frames=[];inputs=[]
for p in sorted((S/'raw').glob('*.parquet')):
 t=pq.read_table(p,columns=['code','date','is_st','is_paused']);f=t.to_pandas(strings_to_categorical=True);frames.append(f);h=hashlib.sha256()
 with p.open('rb') as r:
  for b in iter(lambda:r.read(4*1024*1024),b''):h.update(b)
 inputs.append({'path':str(p.relative_to(B.parent)),'sha256':h.hexdigest(),'rows':len(f)})
 print(p.name,len(f),flush=True)
f=pd.concat(frames,ignore_index=True);del frames;gc.collect()
# Equal categorical codebooks are not assumed across independent source shards.
f['code']=f['code'].astype('category');f['date']=f['date'].astype('category')
invalid=~f['is_st'].isin([0,1])|~f['is_paused'].isin([0,1])|~f['code'].astype(str).str.match(r'^\d{6}\.(SH|SZ|BJ)$')
f.loc[invalid].to_parquet(O/'invalid-status-rows.parquet',index=False)
g=f.groupby(['code','date'],observed=True,dropna=False).agg(st_min=('is_st','min'),st_max=('is_st','max'),st_count=('is_st','count'),paused_min=('is_paused','min'),paused_max=('is_paused','max'),paused_count=('is_paused','count'),raw_rows=('is_st','size')).reset_index()
conflict=(g.st_min!=g.st_max)|(g.paused_min!=g.paused_max)|(g.st_count!=g.raw_rows)|(g.paused_count!=g.raw_rows)
g.loc[conflict].to_parquet(O/'conflicting-status-keys.parquet',index=False)
valid=~conflict & g.st_min.isin([0,1]) & g.paused_min.isin([0,1]) & g.code.astype(str).str.match(r'^\d{6}\.(SH|SZ|BJ)$')
out=g.loc[valid,['code','date','st_min','paused_min','raw_rows']].rename(columns={'st_min':'vendor_is_st','paused_min':'vendor_is_paused'})
out['instrument']=out.code.astype(str).str[7:].str.lower()+'.'+out.code.astype(str).str[:6];out.to_parquet(O/'vendor-daily-status.parquet',index=False,compression='zstd')
r={'audit_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'inputs':inputs,'raw_rows':len(f),'unique_keys':len(g),'duplicate_rows':len(f)-len(g),'invalid_raw_rows':int(invalid.sum()),'conflicting_keys':int(conflict.sum()),'accepted_keys':len(out),'securities':out.code.nunique(),'first_date':str(out.date.astype(str).min()),'last_date':str(out.date.astype(str).max()),'st_flagged_days':int((out.vendor_is_st==1).sum()),'paused_flagged_days':int((out.vendor_is_paused==1).sum()),'limitations':['Third-party vendor flags; not exchange verified and not PIT certified.','All-zero pause flag does not establish absence of historical suspensions.','No forward fill to latest date or before source coverage.','Full feature table remains quarantined; this audit certifies only flag structural consistency.','Underlying source rights unverified; public publisher license does not certify upstream rights.'],'outputs':[]}
for p in O.glob('*.parquet'):r['outputs'].append({'path':str(p.relative_to(B)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
(B/'catalog/hf-status-audit.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));print(json.dumps({k:v for k,v in r.items() if k not in ['inputs','outputs','limitations']}),flush=True)
