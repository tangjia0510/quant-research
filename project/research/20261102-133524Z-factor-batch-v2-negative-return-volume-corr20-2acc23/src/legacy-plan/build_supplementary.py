from pathlib import Path
import json,hashlib,datetime
import numpy as np,pandas as pd
from factor_family import compute
P=Path(__file__).resolve().parents[1];W=P.parents[2];O=P/'outputs';plan=json.loads((P/'research-plan.json').read_text());REF=W/'quant-research-library/studies/20261102-114917Z-factor-momentum-ic-opt-v1-a4102a';names=[x['id'] for x in plan['candidates']]
def digest(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def main():
 assert digest(REF/'data/bars.parquet')==plan['dataset']['reference_prepared_bars_sha256'];assert digest(REF/'data/eligibility.parquet')==plan['dataset']['reference_eligibility_sha256']
 frozen=json.loads((REF/'supplementary/final-artifact-manifest.json').read_text());statuspath=REF/'supplementary/development/supplementary-coverage.csv';expected=next(x['sha256'] for x in frozen['files'] if x['path']==str(statuspath.relative_to(REF)));assert digest(statuspath)==expected;status=pd.read_csv(statuspath).set_index('instrument').status_at_snapshot
 calendar=pd.DatetimeIndex(pd.to_datetime((REF/'data/provider/calendars/day.txt').read_text().splitlines()));counts=[]
 for year in range(2019,2027):
  dates=calendar[calendar.year==year]
  if not len(dates):continue
  first=calendar.get_loc(dates[0]);last=calendar.get_loc(dates[-1]);start=calendar[max(first-20,0)];end=calendar[min(last+11,len(calendar)-1)];filters=[('datetime','>=',start),('datetime','<=',end)]
  bars=pd.read_parquet(REF/'data/bars.parquet',filters=filters).sort_index();eligible=pd.read_parquet(REF/'data/eligibility.parquet',filters=filters).eligible.reindex(bars.index).fillna(False);factor=pd.concat([compute(bars,{'candidate_id':n}).rename(columns={'x_'+n.replace('-','_'):n}) for n in names],axis=1)
  good=np.isfinite(bars[['open','high','low','close','volume']]).all(axis=1)&bars[['open','high','low','close','volume']].gt(0).all(axis=1);past=good.groupby(level='instrument',sort=False).transform(lambda s:s.rolling(21,min_periods=21).sum().eq(21));target=bars.index.get_level_values('datetime').year==year;gate=target&eligible&past&factor.notna().all(axis=1)
  out=factor.loc[gate].copy();out['status_at_snapshot']=out.index.get_level_values('instrument').map(status);assert out.status_at_snapshot.notna().all();price=bars.open.where(good);g=price.groupby(level='instrument',sort=False)
  for h in [1,5,10]:
   out[f'label_{h}']=(g.shift(-h-1)/g.shift(-1)-1).loc[gate];global_end=pd.Series(calendar,index=calendar).shift(-h-1);out[f'label_end_{h}']=out.index.get_level_values('datetime').map(global_end)
  out.index=out.index.set_names(['date','instrument']);out.reset_index().to_parquet(O/f'factor-observations-{year}.parquet',index=False,compression='zstd')
  count_frame=pd.DataFrame({'native_eligible_rows':eligible,'common_signal_rows':gate,**{n+'_finite_rows':factor[n].notna() for n in names}},index=bars.index);aggregated=count_frame.loc[target].groupby(level='instrument',sort=False).sum().reset_index();aggregated['year']=year;counts.extend(aggregated.to_dict('records'))
  print('built',year,'common_signals',len(out),flush=True)
 pd.DataFrame(counts).to_csv(O/'supplementary-coverage.csv',index=False);(O/'input-verification.json').write_text(json.dumps({'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'prepared_bars_sha256':digest(REF/'data/bars.parquet'),'eligible_sha256':digest(REF/'data/eligibility.parquet'),'snapshot_status_sha256':expected,'files':{p.name:digest(p) for p in O.glob('factor-observations-*.parquet')},'no_future_label_in_gate':True},indent=2))
if __name__=='__main__':main()
