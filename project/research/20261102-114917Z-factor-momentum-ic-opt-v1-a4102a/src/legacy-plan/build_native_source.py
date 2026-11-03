from pathlib import Path
import json,hashlib,datetime,sys,gc
import pandas as pd,numpy as np,pyarrow as pa,pyarrow.parquet as pq
P=Path(__file__).resolve().parents[1];W=P.parents[2];L=W/'a-share-data-lake';D=W/'quant-research-library/diagnostics/20261102-price-volume-quality-v1';OUT=P/'native-source'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(p,o):p.write_text(json.dumps(o,ensure_ascii=False,indent=2,default=str,allow_nan=False))
def main():
 manifest=json.loads((D/'artifacts/input-manifest.json').read_text());used={}
 def verify(p):
  rel=str(p.relative_to(W));h=sha(p);assert manifest['inputs'][rel]['sha256']==h,(rel,'changed');used[rel]=h;return p
 cols=['date','instrument','open','high','low','close','volume_shares','amount_cny'];chunks=[]
 for f in sorted((L/'market/hf_bulk/normalized_prices').glob('*.parquet')):
  verify(f);chunks.append(pq.read_table(f,columns=cols,filters=[('date','>=',datetime.date(2019,1,1))]).to_pandas(date_as_object=False))
 hf=pd.concat(chunks,ignore_index=True);del chunks;gc.collect();hf=hf.sort_values(['instrument','date']).reset_index(drop=True);ix=hf.groupby('instrument',sort=False).indices
 sup=pd.read_parquet(verify(L/'market/historical_supplement/tencent_hf_missing.parquet'),columns=cols);sup['date']=pd.to_datetime(sup.date)
 cal=pd.DatetimeIndex(pd.to_datetime(verify(L/'reference/normalized/trading-calendar-observed-2019-2026.txt').read_text().splitlines()));(OUT/'calendar.txt').write_text('\n'.join(cal.strftime('%Y-%m-%d'))+'\n')
 master=pd.read_csv(D/'dataset/universe-frozen.csv');intervals=[];counts=[];writer=None
 for n,r in enumerate(master.itertuples(),1):
  sym=r.symbol;panelpath=D/f'dataset/{sym}.parquet'
  if not panelpath.exists():counts.append({'instrument':sym,'reason':'no_frozen_panel'});continue
  panel=pd.read_parquet(panelpath).set_index('date');parts=[]
  if sym in ix:parts.append(hf.iloc[ix[sym]].copy().assign(source='hf_unadjusted',priority=2))
  if (sup.instrument==sym).any():parts.append(sup[sup.instrument.eq(sym)].assign(source='tencent_supplement',priority=1))
  tp=L/f'market/normalized/{sym}.csv.gz'
  if tp.exists():
   t=pd.read_csv(verify(tp),usecols=cols);t['date']=pd.to_datetime(t.date);parts.append(t.assign(source='tencent',priority=0))
  raw=pd.concat(parts,ignore_index=True).sort_values(['date','priority']).drop_duplicates('date').set_index('date').reindex(cal)
  for a,b in [('open','raw_open'),('close','raw_close'),('volume_shares','volume_shares'),('amount_cny','amount_cny')]:np.testing.assert_allclose(raw[a],panel[b],rtol=0,atol=1e-8,equal_nan=True,err_msg=sym+a)
  obs=panel.observed;first=panel.index[obs].min();inside=panel.lifecycle & (panel.index>=first)
  allowed=panel.bar_good & ~panel.extreme_adjusted_move
  if not allowed.any():counts.append({'instrument':sym,'reason':'no_valid_adjusted_bars','observed':int(obs.sum())});continue
  # These gates only depend on information at the current/past date, not future labels.
  source=pd.DataFrame(index=cal)
  for c in ['open','high','low','close']:source[c]=(raw[c]*panel.factor).where(allowed)
  source['volume']=(panel.volume_shares/panel.factor).where(allowed)
  source['factor']=panel.factor.where(allowed)
  eligible=inside & panel.ipo_seasoned
  if not eligible.any():counts.append({'instrument':sym,'reason':'not_yet_60_sessions_seasoned','observed':int(obs.sum())});continue
  source=source.loc[inside];source.index.name='datetime';source['instrument']=sym
  frame=source.reset_index()[['datetime','instrument','open','high','low','close','volume','factor']]
  table=pa.Table.from_pandas(frame,preserve_index=False)
  if writer is None:writer=pq.ParquetWriter(OUT/'bars.parquet',table.schema,compression='zstd')
  writer.write_table(table)
  intervals.append({'instrument':sym,'start':str(panel.index[eligible].min().date()),'end':str(panel.index[eligible].max().date())})
  counts.append({'instrument':sym,'source_rows':len(frame),'finite_price_rows':int(frame.close.notna().sum()),'masked_rows':int(frame.close.isna().sum()),'status_at_snapshot':r.status})
  if n%200==0:print('source',n,'/',len(master),flush=True)
 writer.close();pd.DataFrame(intervals).to_csv(OUT/'universe.csv',index=False);pd.DataFrame(counts).to_csv(OUT/'coverage.csv',index=False)
 metadata={'source':'Frozen audited Tencent whole rows + HF whole rows + Tencent supplement; Sina effective-date factors','synthetic':False,'region':'cn','currency':'CNY','frequency':'day','price_basis':'adjusted','volume_unit':'units','adjustment_identity':'audited-shsz-multiplicative-v1','volume_basis':'raw volume_shares / asof Sina factor','universe_scope':'Frozen SH/SZ master including delisted, lifecycle/code boundaries and IPO>=60 observed calendar sessions; not complete historical entire A-share identity universe','limitations':['All input snapshots retrospective, not independently certified PIT/vintage','No future-label condition used in source eligibility; missing current bars remain NaN','Native train-median factor imputation differs from supplementary matched61 complete history sample','Historical ST/board-specific limits/suspensions not fully available','No complete terminal delisting returns or forced liquidation','302132 pre-switch mapped history excluded; old300114 not independently covered','sh689009 excluded for missing factor; sh600680 no period bars','Calendar observed SSE composite, not exchange certified','2026 previously exposed; final means retrospective robustness not untouched holdout','Daily simulator not calibrated slippage/capacity and benchmark synthetic'], 'diagnostic_manifest_sha256':sha(D/'artifacts/artifact-manifest.json'),'research_plan_sha256':sha(P/'research-plan.json')}
 dump(OUT/'metadata.json',metadata);dump(OUT/'provenance.json',{'used_inputs_sha256':used,'immutable_diagnostic_root':str(D.relative_to(W)),'counts':{'target':len(master),'included':len(intervals),'excluded':len(master)-len(intervals)}})
 print('DONE',len(intervals),flush=True)
if __name__=='__main__':main()
