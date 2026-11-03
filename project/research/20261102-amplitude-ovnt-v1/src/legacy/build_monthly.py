from pathlib import Path
import json,hashlib,datetime,gc
import numpy as np,pandas as pd
from formulas import amplitude_window,overnight_daily,full_month_overnight,ovnt_scores
P=Path(__file__).resolve().parents[1];BASE=P.parents[2];O=P/'outputs';plan=json.loads((P/'protocol.json').read_text())
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def main():
 bp=BASE/plan['data']['prepared_bars'];mp=BASE/plan['data']['prior_monthly_panel'];old=mp.parents[1];assert sha(bp)==plan['data']['bars_sha256'];assert sha(mp)==plan['data']['monthly_panel_sha256'];assert sha(old/'final-artifact-manifest.json')==plan['data']['prior_seal_sha256'];oldfiles={x['path']:x['sha256'] for x in json.loads((old/'final-artifact-manifest.json').read_text())['files']};calpath=old/'outputs/calendar.txt';assert sha(calpath)==oldfiles['outputs/calendar.txt'];cal=pd.DatetimeIndex(pd.to_datetime(calpath.read_text().splitlines()));(O/'calendar.txt').write_text(calpath.read_text())
 diag=BASE/'quant-research-library/diagnostics/20261102-price-volume-quality-v1';dm=diag/'artifacts/artifact-manifest.json';assert sha(dm)==plan['data']['original_manifest_sha256'];masterpath=BASE/plan['data']['master'];assert sha(masterpath)==json.loads(dm.read_text())['files']['dataset/universe-frozen.csv']['sha256'];master=pd.read_csv(masterpath).set_index('symbol');ipo=pd.to_datetime(master.ipo_date,errors='coerce');assert ipo.notna().all()
 base=pd.read_parquet(mp,columns=['instrument','month','formation_month','signal_date','target_month','status_at_snapshot','adj_close','next_open','month_return','label_close','label_open','close_mature','open_mature']);records=[]
 for year in range(2019,2027):
  ydates=cal[cal.year==year]
  if not len(ydates):continue
  first=cal.get_loc(ydates[0]);start=cal[max(0,first-20)];end=ydates[-1];ext=cal[(cal>=start)&(cal<=end)];period=ext.to_period('M');months=ydates.to_period('M').unique();defs=[]
  for m in months:
   pos=np.flatnonzero(period==m);j=pos[-1];defs.append((m,pos,j,ext[j]))
  bars=pd.read_parquet(bp,filters=[('datetime','>=',start),('datetime','<=',end)],columns=['open','high','low','close']).sort_index()
  for sym,g in bars.groupby(level='instrument',sort=False):
   g=g.droplevel('instrument').sort_index();gi=g.index
   assert gi.equals(cal[(cal>=gi.min())&(cal<=gi.max())]),'Source internal missing dates must remain explicit'
   g=g.reindex(ext);c=g.close.to_numpy();o=g.open.to_numpy();h=g.high.to_numpy();l=g.low.to_numpy();on=overnight_daily(o,c);ip=ipo.loc[sym];ipo_position=cal.searchsorted(ip);age60_positions=cal.get_indexer(ext)-ipo_position+1
   for m,pos,j,date in defs:
    # Keep fixed global20-day window; do not compress missing/flat days before slicing.
    amp=amplitude_window(h[j-19:j+1],l[j-19:j+1],c[j-19:j+1]) if j>=19 else {'score':np.nan,'high_amp':np.nan,'low_amp':np.nan,'valid_days':0,'k':0}
    current_good=bool(np.isfinite(c[j]) and c[j]>0);aok=current_good and age60_positions[j]>=60;ook=current_good and date>=ip+pd.DateOffset(months=3)
    records.append({'instrument':sym,'month':m.ordinal,'amplitude_high':amp['high_amp'],'amplitude_low':amp['low_amp'],'amplitude_valid_days':amp['valid_days'],'amplitude_k':amp['k'],'ideal_amplitude20':amp['score'] if aok else np.nan,'amplitude_current_eligible':aok,'ovnt_current_eligible':ook,'current_source_close':c[j],'overnight_month':full_month_overnight(on[pos],len(pos)),'overnight_expected_days':len(pos),'overnight_valid_days':int(np.isfinite(on[pos]).sum())})
  print('computed monthly components',year,len(records),flush=True);del bars;gc.collect()
 components=pd.DataFrame(records);assert not components.duplicated(['instrument','month']).any();frame=base.merge(components,on=['instrument','month'],how='left',validate='one_to_one');both=frame.current_source_close.notna();np.testing.assert_allclose(frame.loc[both,'current_source_close'],frame.loc[both,'adj_close'],rtol=0,atol=1e-8)
 frame=ovnt_scores(frame);frame['ovnt12']=frame.ovnt12.where(frame.ovnt_current_eligible.fillna(False)&~frame.last3_months_zero);frame.to_parquet(O/'monthly-panel.parquet',index=False,compression='zstd');signals=[]
 for cid in ['ideal_amplitude20','ovnt12']:
  gate=np.isfinite(frame[cid]) & frame.target_month.between('2020-01','2026-10');q=frame.loc[gate,['instrument','signal_date','target_month','month','status_at_snapshot','label_close','label_open','close_mature','open_mature']].copy();q['candidate']=cid;q['score']=frame.loc[gate,cid];signals.append(q)
 signal=pd.concat(signals,ignore_index=True);assert not np.isinf(signal[['score','label_close','label_open']].to_numpy()).any();signal.to_parquet(O/'signals.parquet',index=False,compression='zstd');coverage=signal.groupby(['candidate','target_month']).agg(signals=('instrument','size'),label_close_available=('label_close','count'),label_open_available=('label_open','count')).reset_index();coverage.to_csv(O/'signal-coverage.csv',index=False)
 checks={'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'protocol_sha256':sha(P/'protocol.json'),'bars_sha256':sha(bp),'old_monthly_panel_sha256':sha(mp),'old_seal_sha256':sha(old/'final-artifact-manifest.json'),'calendar_sha256':sha(calpath),'master_sha256':sha(masterpath),'component_instruments':int(components.instrument.nunique()),'monthly_rows':len(frame),'signals':len(signal),'new_monthly_panel_sha256':sha(O/'monthly-panel.parquet'),'new_signals_sha256':sha(O/'signals.parquet'),'source_endpoint_prices_match_old_frozen_labels':True,'old_factors_not_used':True,'no_labels_used_for_new_scores':True};(O/'input-verification.json').write_text(json.dumps(checks,indent=2));print(coverage.groupby('candidate').agg(months=('target_month','size'),signals=('signals','sum')).to_string(),flush=True)
if __name__=='__main__':main()
