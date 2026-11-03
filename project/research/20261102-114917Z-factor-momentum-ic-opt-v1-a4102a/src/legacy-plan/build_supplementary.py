from pathlib import Path
import json,hashlib,datetime
import numpy as np,pandas as pd,pyarrow as pa,pyarrow.parquet as pq
from factor_family import all_factors
P=Path(__file__).resolve().parents[1];W=P.parents[2];D=W/'quant-research-library/diagnostics/20261102-price-volume-quality-v1';O=P/'outputs';plan=json.loads((P/'research-plan.json').read_text());names=[x['id'] for x in plan['candidates']]
def main():
 writers={};counts=[];diag_manifest=json.loads((D/'artifacts/artifact-manifest.json').read_text());verified=0
 for i,p in enumerate(sorted((D/'dataset').glob('*.parquet')),1):
  rel=str(p.relative_to(D));h=hashlib.sha256(p.read_bytes()).hexdigest();assert diag_manifest['files'][rel]['sha256']==h,rel;verified+=1
  a=pd.read_parquet(p);sym=a.instrument.iloc[0];a=a.set_index('date');allowed=a.bar_good & ~a.extreme_adjusted_move
  base=pd.DataFrame({'close':(a.raw_close*a.factor).where(allowed),'volume':(a.volume_shares/a.factor).where(allowed)},index=a.index);base['instrument']=sym;base.index.name='datetime';base=base.reset_index().set_index(['datetime','instrument'])
  factors=all_factors(base).droplevel('instrument');eligible=allowed.rolling(61,min_periods=61).sum().eq(61)&a.ipo_seasoned&factors.notna().all(axis=1)
  out=factors.loc[eligible].copy();out['instrument']=sym;out['status_at_snapshot']=a.status_at_snapshot.loc[eligible];out['source']=a.source.loc[eligible]
  ap=(a.raw_open*a.factor).where(allowed);calendar=pd.Series(a.index,index=a.index)
  for horizon in [1,5,10]:
   out[f'label_{horizon}']=(ap.shift(-horizon-1)/ap.shift(-1)-1).loc[eligible];out[f'label_end_{horizon}']=calendar.shift(-horizon-1).loc[eligible]
  out.index.name='date';out=out.reset_index()
  for year,g in out.groupby(out.date.dt.year):
   key=int(year);tab=pa.Table.from_pandas(g,preserve_index=False)
   if key not in writers:writers[key]=pq.ParquetWriter(O/f'factor-observations-{key}.parquet',tab.schema,compression='zstd')
   writers[key].write_table(tab)
  counts.append({'instrument':sym,'status_at_snapshot':a.status_at_snapshot.iloc[0],'signal_rows':len(out),'label5_missing':int(out.label_5.isna().sum())})
  if i%500==0:print('supplement',i,flush=True)
 for writer in writers.values():writer.close()
 pd.DataFrame(counts).to_csv(O/'supplementary-coverage.csv',index=False)
 (O/'frozen-panel-verification.json').write_text(json.dumps({'verified_panels':verified,'original_manifest_sha256':hashlib.sha256((D/'artifacts/artifact-manifest.json').read_bytes()).hexdigest(),'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'signal_gate_does_not_require_future_label':True,'files':{f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in O.glob('factor-observations-*.parquet')}},indent=2))
 print('DONE',verified,flush=True)
if __name__=='__main__':main()
