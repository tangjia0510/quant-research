from pathlib import Path
import json,hashlib,datetime
import pandas as pd,numpy as np
from formulas import illiq20,seas_scores
P=Path(__file__).resolve().parents[1];O=P/'outputs';BASE=P.parents[2];plan=json.loads((P/'protocol.json').read_text());D=BASE/plan['data']['root']
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def main():
 manifest_path=D/plan['data']['manifest'];assert sha(manifest_path)==plan['data']['manifest_sha256'];manifest=json.loads(manifest_path.read_text())['files'];masterpath=D/'dataset/universe-frozen.csv';assert sha(masterpath)==manifest['dataset/universe-frozen.csv']['sha256'];master=pd.read_csv(masterpath);parts=[];inputs={};exclusions=[];calendar=None
 for n,r in enumerate(master.itertuples(),1):
  path=D/f'dataset/{r.symbol}.parquet'
  if not path.exists():exclusions.append({'instrument':r.symbol,'reason':'No frozen panel'});continue
  h=sha(path);assert h==manifest[str(path.relative_to(D))]['sha256'];inputs[r.symbol]=h
  f=pd.read_parquet(path).set_index('date').sort_index();dates=pd.DatetimeIndex(f.index)
  if calendar is None:
   calendar=dates;month_period=dates.to_period('M');ends=np.flatnonzero(np.r_[month_period[:-1]!=month_period[1:],True]);months=month_period[ends];(O/'calendar.txt').write_text('\n'.join(dates.strftime('%Y-%m-%d'))+'\n')
  else:assert calendar.equals(dates),'Frozen full-calendar contract violated'
  ipo=pd.to_datetime(r.ipo_date,errors='coerce');good=f.bar_good & ~f.extreme_adjusted_move & f.lifecycle
  adj=(f.raw_close*f.factor).where(good);op=(f.raw_open*f.factor).where(good);current=good & ((dates>=ipo+pd.DateOffset(months=6)) if pd.notna(ipo) else False)
  obs=dates[f.observed & f.lifecycle];first=obs.min() if len(obs) else pd.NaT
  age5=(dates>=ipo+pd.DateOffset(years=5)) & (dates>=first+pd.DateOffset(years=5)) if pd.notna(ipo) and pd.notna(first) else np.zeros(len(dates),dtype=bool)
  il=illiq20(adj,f.raw_close,f.volume_shares).where(current)
  mclose=adj.iloc[ends].to_numpy();mopen=np.array([op.iloc[j+1] if j+1<len(op) else np.nan for j in ends]);mreturn=pd.Series(mclose).pct_change(fill_method=None).to_numpy()
  m=pd.DataFrame({'instrument':r.symbol,'month':months.astype('int64'),'formation_month':months.astype(str),'signal_date':dates[ends],'target_month':(months+1).astype(str),'current_eligible':np.asarray(current)[ends],'seas_history_eligible':np.asarray(age5)[ends],'status_at_snapshot':r.status,'adj_close':mclose,'next_open':mopen,'month_return':mreturn,'illiq20':il.iloc[ends].to_numpy(),'observed_days':f.observed.groupby(month_period).sum().to_numpy(),'good_days':good.groupby(month_period).sum().to_numpy()})
  m['label_close']=pd.Series(mclose).shift(-1).to_numpy()/mclose-1;m['label_open']=pd.Series(mopen).shift(-1).to_numpy()/mopen-1;m['close_mature']=m.month<months[-1].ordinal;m['open_mature']=m.month<months[-1].ordinal-1
  parts.append(m)
  if n%500==0:print('verified/build',n,'/',len(master),flush=True)
 frame=pd.concat(parts,ignore_index=True);frame=seas_scores(frame);frame.to_parquet(O/'monthly-panel.parquet',index=False,compression='zstd')
 signals=[]
 for cid in ['illiq20','seas']:
  gate=frame.current_eligible & np.isfinite(frame[cid]) & (frame.target_month>='2020-01') & (frame.target_month<='2026-10')
  q=frame.loc[gate,['instrument','signal_date','target_month','month','status_at_snapshot','label_close','label_open','close_mature','open_mature','seas_history_n']].copy();q['candidate']=cid;q['score']=frame.loc[gate,cid];signals.append(q)
 signal=pd.concat(signals,ignore_index=True);signal.to_parquet(O/'signals.parquet',index=False,compression='zstd')
 counts=signal.groupby(['candidate','target_month']).agg(signals=('instrument','size'),label_close_available=('label_close','count'),label_open_available=('label_open','count')).reset_index();counts.to_csv(O/'signal-coverage.csv',index=False)
 pd.DataFrame(exclusions).to_csv(O/'source-exclusions.csv',index=False)
 (O/'input-verification.json').write_text(json.dumps({'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'protocol_sha256':sha(P/'protocol.json'),'source_manifest_sha256':sha(manifest_path),'frozen_panels_verified':len(inputs),'target_master':len(master),'verified_panel_sha256':inputs,'monthly_panel_sha256':sha(O/'monthly-panel.parquet'),'signals_sha256':sha(O/'signals.parquet'),'new_data_not_included':True,'monthly_rows':len(frame),'signals':len(signal),'source_count':len(parts),'no_label_used_for_signal_or_group_membership':True},indent=2))
 print(counts.groupby('candidate').agg(months=('target_month','size'),signals=('signals','sum')).to_string(),flush=True)
if __name__=='__main__':main()
