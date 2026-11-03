from pathlib import Path
import json, hashlib, datetime, sys, gc
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

ROOT=Path(__file__).resolve().parents[1]; WORK=ROOT.parents[2]; LAKE=WORK/'a-share-data-lake'
ART=ROOT/'artifacts'; DATA=ROOT/'dataset'; P=json.loads((ROOT/'protocol.json').read_text())
COLS=['date','instrument','open','high','low','close','volume_shares','amount_cny']
INPUTS={}
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def track(p):
 p=Path(p); INPUTS[str(p.relative_to(WORK))]={'sha256':sha(p),'bytes':p.stat().st_size};return p
def save(name,obj): (ART/name).write_text(json.dumps(obj,indent=2,ensure_ascii=False,default=str,allow_nan=False))
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def stock_signals(d,calendar,ipo,delist,start=None,end=None):
 d=d.set_index('date').reindex(calendar)
 observed=d['close'].notna()
 vals=d[['open','high','low','close','volume_shares','amount_cny']]
 finite=np.isfinite(vals).all(axis=1)
 ordering=(d.low<=d[['open','close']].min(axis=1))&(d.high>=d[['open','close']].max(axis=1))&(d.low<=d.high)
 positive=(vals>0).all(axis=1)
 vwap=d.amount_cny/d.volume_shares
 volume_ok=(vwap>=d.low*.98)&(vwap<=d.high*1.02)
 factor_ok=np.isfinite(d.factor)&(d.factor>0)
 lifecycle=pd.Series(True,index=calendar)
 if pd.notna(ipo):lifecycle &=calendar>=ipo
 if pd.notna(delist):lifecycle &=calendar<delist
 if start is not None:lifecycle &=calendar>=pd.Timestamp(start)
 if end is not None:lifecycle &=calendar<pd.Timestamp(end)
 good=finite&ordering&positive&volume_ok&factor_ok&lifecycle
 adj=d.close*d.factor; adjopen=d.open*d.factor
 ret=adj/adj.shift(1)-1
 extreme=(ret.abs()>.5)&observed&observed.shift(1,fill_value=False)
 safe=good&~extreme
 signal_history=safe.rolling(21,min_periods=21).sum().eq(21)
 age=np.arange(len(calendar))-calendar.searchsorted(ipo) if pd.notna(ipo) else np.full(len(calendar),-1)
 signal=signal_history&(age>=60)
 future=pd.concat([safe.shift(-k,fill_value=False) for k in range(1,7)],axis=1).all(axis=1)
 momentum=adj/adj.shift(20)-1
 label=adjopen.shift(-6)/adjopen.shift(-1)-1
 label_ok=future&np.isfinite(label)
 out=pd.DataFrame({'date':calendar,'raw_close':d.close.to_numpy(),'raw_open':d.open.to_numpy(),'factor':d.factor.to_numpy(),'volume_shares':d.volume_shares.to_numpy(),'amount_cny':d.amount_cny.to_numpy(),'source':d.source.to_numpy(),'observed':observed.to_numpy(),'bar_good':good.to_numpy(),'extreme_adjusted_move':extreme.to_numpy(),'signal_eligible':signal.to_numpy(),'label_available':label_ok.to_numpy(),'momentum20':momentum.to_numpy(),'forward5':label.to_numpy(),'lifecycle':lifecycle.to_numpy(),'ipo_seasoned':age>=60})
 out['label_entry_date']=pd.Series(calendar,index=calendar).shift(-1).to_numpy();out['label_exit_date']=pd.Series(calendar,index=calendar).shift(-6).to_numpy()
 q={'observed_rows':int(observed.sum()),'missing_within_lifecycle':int((lifecycle&~observed).sum()),'outside_lifecycle_observed':int((observed&~lifecycle).sum()),'invalid_numeric':int((observed&~finite).sum()),'ohlc_ordering_fail':int((observed&~ordering).sum()),'nonpositive_ohlcv_amount':int((observed&~positive).sum()),'vwap_outside_2pct':int((observed&~volume_ok).sum()),'factor_missing_or_invalid':int((observed&~factor_ok).sum()),'adjusted_move_over_50pct':int(extreme.sum()),'good_bars':int(good.sum()),'signal_rows':int(signal.sum()),'signal_with_missing_outcome':int((signal&~label_ok).sum()),'signal_labeled':int((signal&label_ok).sum())}
 return out,q

def main():
 calendar=pd.DatetimeIndex(pd.to_datetime(track(LAKE/'reference/normalized/trading-calendar-observed-2019-2026.txt').read_text().splitlines()))
 master=pd.read_csv(track(LAKE/'market/manifests/universe-sharded-with-bse.csv'),dtype={'code':str})
 master['symbol']=master.instrument.str.replace('.','',regex=False)
 master=master[master.exchange.isin(['SSE','SZSE'])].copy()
 master.to_csv(DATA/'universe-frozen.csv',index=False)
 spans=pd.read_csv(track(LAKE/'reference/core-gap-supplement/normalized/verified-trading-code-spans.csv'))
 spanmap={r.instrument.replace('.',''):(r.start_inclusive,None if pd.isna(r.end_exclusive) else r.end_exclusive) for r in spans.itertuples()}
 # HF normalized whole rows, filtered before pandas. No columns drawn across providers.
 chunks=[]
 for f in sorted((LAKE/'market/hf_bulk/normalized_prices').glob('*.parquet')):
  track(f); t=pq.read_table(f,columns=COLS,filters=[('date','>=',datetime.date(2019,1,1)),('date','<=',datetime.date(2026,10,30))]);chunks.append(t.to_pandas(date_as_object=False));print('HF',f.name,len(chunks[-1]),flush=True)
 hf=pd.concat(chunks,ignore_index=True);del chunks;gc.collect(); hf['source']='hf_unadjusted';hf=hf.sort_values(['instrument','date']).reset_index(drop=True); hf_indices=hf.groupby('instrument',sort=False).indices
 sf=track(LAKE/'market/historical_supplement/tencent_hf_missing.parquet');supp=pd.read_parquet(sf,columns=COLS);supp['date']=pd.to_datetime(supp.date);supp['source']='tencent_supplement'
 qrows=[]; sample_parts=[]; dailycounts=[];badparts=[];dups=[];factorstats=[]
 for i,r in enumerate(master.itertuples(),1):
  sym=r.symbol; pieces=[]
  if sym in hf_indices:pieces.append(hf.iloc[hf_indices[sym]].copy().assign(priority=2))
  ss=supp[supp.instrument.eq(sym)]
  if len(ss):pieces.append(ss.assign(priority=1))
  tp=LAKE/f'market/normalized/{sym}.csv.gz'
  if tp.exists():
   z=pd.read_csv(track(tp),usecols=COLS);z['date']=pd.to_datetime(z.date);z['source']='tencent';z['priority']=0;pieces.append(z)
  if not pieces:
   qrows.append({'instrument':sym,'status':r.status,'master_board':r.board,'reason':'no_raw_bars'});continue
  z=pd.concat(pieces,ignore_index=True).sort_values(['date','priority']);z=z[z.date.between(calendar.min(),calendar.max())]
  if z.empty:
   qrows.append({'instrument':sym,'status':r.status,'master_board':r.board,'reason':'no_raw_bars'});continue
  dup=z[z.duplicated('date',False)]
  if len(dup):
   groups=dup.groupby('date');conf=(groups[['open','high','low','close']].max()-groups[['open','high','low','close']].min()).max(axis=1)>.011
   dups.append({'instrument':sym,'overlapping_dates':len(groups),'ohlc_conflicts_gt_0_011':int(conf.sum())})
  z=z.drop_duplicates('date',keep='first').drop(columns='priority')
  fp=LAKE/f'actions/normalized/factors/{sym}.csv'
  if fp.exists():
   fac=pd.read_csv(track(fp));fac['effective_date']=pd.to_datetime(fac.effective_date);fac=fac.sort_values('effective_date')
   assert not fac.effective_date.duplicated().any()
   z=pd.merge_asof(z,fac[['effective_date','factor']],left_on='date',right_on='effective_date',direction='backward')
   factorstats.append({'instrument':sym,'events':len(fac),'events_2019plus':int((fac.effective_date>=calendar.min()).sum()),'source_sentinel_present':bool((fac.effective_date==pd.Timestamp('1900-01-01')).any())})
  else:z['factor']=np.nan
  ipo=pd.to_datetime(r.ipo_date,errors='coerce');delist=pd.to_datetime(r.delist_date,errors='coerce');start,end=spanmap.get(sym,(None,None))
  o,q=stock_signals(z,calendar,ipo,delist,start,end);o['instrument']=sym
  o['status_at_snapshot']=r.status;o['board']=r.board
  q.update(instrument=sym,status=r.status,master_board=r.board,first_observation=str(z.date.min().date()),last_observation=str(z.date.max().date()),ipo_date=str(ipo),delist_date=str(delist),selected_sources=z.source.value_counts().to_dict())
  qrows.append(q)
  # Preserve full per-security calendar, including NaN missing records, as an explicit diagnostic panel.
  o.to_parquet(DATA/f'{sym}.parquet',index=False)
  bad=o[o.observed & (~o.bar_good|o.extreme_adjusted_move)]
  if len(bad):badparts.append(bad)
  dd=o[['date','observed','lifecycle','bar_good','signal_eligible','label_available']].copy();dd['signal_labeled']=o.signal_eligible&o.label_available;dailycounts.append(dd.set_index('date').astype('int32'))
  sm=o[o.signal_eligible].copy()
  if len(sm):sample_parts.append(sm[['date','instrument','momentum20','forward5','label_available','label_entry_date','label_exit_date','status_at_snapshot','source','board']])
  if i%100==0:
   print('BUILD',i,'/',len(master),flush=True);save('progress.json',{'stage':'build','processed':i,'total':len(master),'at':now()})
  if i%500==0:
   # Reduce accumulated count frames periodically.
   dailycounts=[sum(dailycounts)]
 pd.DataFrame(qrows).to_json(ART/'per-security-quality.json',orient='records',indent=2,force_ascii=False)
 pd.DataFrame(qrows).drop(columns=['selected_sources'],errors='ignore').to_csv(ART/'per-security-quality.csv',index=False)
 pd.DataFrame(dups).to_csv(ART/'source-overlap.csv',index=False);pd.DataFrame(factorstats).to_csv(ART/'factor-coverage.csv',index=False)
 daily=sum(dailycounts);daily.to_csv(ART/'daily-quality-coverage.csv')
 samples=pd.concat(sample_parts,ignore_index=True);samples.to_parquet(ART/'signal-samples.parquet',index=False)
 if badparts:pd.concat(badparts,ignore_index=True).to_parquet(ART/'flagged-observations.parquet',index=False)
 save('input-manifest.json',{'generated_at':now(),'protocol_sha256':sha(ROOT/'protocol.json'),'inputs':INPUTS})
 summary={'generated_at':now(),'universe':len(master),'source_priority':P['source_priority'],'quality_totals':pd.DataFrame(qrows).select_dtypes('number').sum().astype(int).to_dict(),'statuses':master.status.value_counts().to_dict(),'source_overlap_dates':int(pd.DataFrame(dups).overlapping_dates.sum()),'source_ohlc_conflicts':int(pd.DataFrame(dups).ohlc_conflicts_gt_0_011.sum()),'signal_samples':len(samples)}
 save('quality-summary.json',summary);save('progress.json',{'stage':'build_complete','at':now(),'universe':len(master)});print(json.dumps(summary,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
