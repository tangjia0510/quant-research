import json,hashlib
from pathlib import Path
import numpy as np,pandas as pd
p=Path(__file__).parent;q=p/'mixed-source';out=p/'normalized';out.mkdir(exist_ok=True)
sel=json.loads((p/'selection.json').read_text())['selected'];calendar=pd.DatetimeIndex(pd.to_datetime((q/'calendar.txt').read_text().splitlines()));end=str(calendar[-1].date())
allbars=[];allraw=[];quality=[];events=[];failures=[];universe=[];return_outliers=[]
receipts=[json.loads(line) for line in (q/'receipts.jsonl').read_text().splitlines()]
for receipt in receipts:
 if 'sha256' in receipt:
  if hashlib.sha256((q/receipt['file']).read_bytes()).hexdigest()!=receipt['sha256']:raise ValueError('Source receipt checksum mismatch '+receipt['file'])
for item in sel:
 code=item['code'].replace('.','');rows={}
 for f in sorted(q.glob(code+'-20*.json')):
  d=json.loads(f.read_bytes());part=d['data'][code]
  for row in part['day']:
   date=row[0]
   if not ('2019-01-01'<=date<=end) or (item['outDate'] and date>item['outDate']):continue
   values=[float(row[i]) for i in [1,2,3,4,5,8]]
   if date in rows and rows[date]!=values:raise ValueError('Conflicting raw duplicate '+code+' '+date)
   rows[date]=values
 if not rows:raise ValueError('No history '+code)
 raw=pd.DataFrame.from_dict(rows,orient='index',columns=['open','close','high','low','lots','amount_10k']).sort_index();raw.index=pd.to_datetime(raw.index);raw.index.name='datetime'
 if not raw.index.isin(calendar).all():raise ValueError('Stock dates outside indexcalendar '+code)
 if not np.isfinite(raw.to_numpy()).all() or (raw[['open','close','high','low']]<=0).any().any() or (raw[['lots','amount_10k']]<0).any().any():raise ValueError('Invalid raw '+code)
 if ((raw.high<raw[['open','close','low']].max(axis=1)) | (raw.low>raw[['open','close','high']].min(axis=1))).any():raise ValueError('OHLC bounds '+code)
 raw['raw_shares']=raw.lots*100;raw['amount_cny']=raw.amount_10k*10000
 vwap=raw.amount_cny/raw.raw_shares.replace(0,np.nan)
 bad=(vwap<raw.low-.02) | (vwap>raw.high+.02)
 inconsistent_zero=raw.lots.eq(0) & raw.amount_10k.ne(0)
 if inconsistent_zero.any():failures.append({'instrument':item['code'],'reason':'zero volume but positive amount','dates':[str(d.date()) for d in raw.index[inconsistent_zero]]})
 if bad.any():failures.append({'instrument':item['code'],'reason':'volume-unit/VWAP inconsistent','rows':raw[bad].reset_index().astype(str).to_dict('records')})
 text=(q/(code+'-factor.js')).read_text();f=json.JSONDecoder().raw_decode(text[text.index('{'):])[0]
 if int(f['total'])!=len(f['data']):raise ValueError('Factor count mismatch '+code)
 factors=pd.DataFrame(f['data']).rename(columns={'d':'date','f':'factor'});factors['date']=pd.to_datetime(factors.date);factors['factor']=pd.to_numeric(factors.factor)
 if factors.date.duplicated().any() or not np.isfinite(factors.factor).all() or (factors.factor<=0).any():raise ValueError('Invalid factor '+code)
 factors=factors.sort_values('date').set_index('date')['factor']
 aligned=factors.reindex(raw.index,method='ffill')
 if aligned.isna().any():raise ValueError('Missing past factor '+code)
 frame=raw[['open','high','low','close']].mul(aligned,axis=0);frame['volume']=raw.raw_shares/aligned;frame['factor']=aligned
 zero=raw.lots.eq(0);frame.loc[zero,['open','high','low','close']]=np.nan
 frame['instrument']=item['code'];allbars.append(frame.reset_index())
 raw['instrument']=item['code'];raw['factor']=aligned;raw['vwap']=vwap;allraw.append(raw.reset_index())
 expected=calendar[(calendar>='2019-01-01')&(calendar<=min(end,item['outDate'] or end))];missing=expected.difference(raw.index)
 quality.append({'instrument':item['code'],'first':str(raw.index[0].date()),'last':str(raw.index[-1].date()),'observed_rows':len(raw),'expected_lifecycle_sessions':len(expected),'unknown_missing_sessions':len(missing),'unknown_missing_dates':[str(d.date()) for d in missing],'zero_volume_rows':int(zero.sum()),'factor_events_total':len(factors),'vwap_unit_bad_rows':int(bad.sum())})
 raw_returns=raw.close.pct_change(fill_method=None);adjusted_returns=(raw.close*aligned).pct_change(fill_method=None)
 for date in raw.index[(raw_returns.abs()>.25)|(adjusted_returns.abs()>.25)]:
  i=raw.index.get_loc(date);return_outliers.append({'instrument':item['code'],'date':str(date.date()),'previous_observed_date':str(raw.index[i-1].date()),'raw_close_return':float(raw_returns.loc[date]),'adjusted_close_return':float(adjusted_returns.loc[date]),'factor_changed':bool(not np.isclose(aligned.loc[date],aligned.iloc[i-1]))})
 ratio=aligned/aligned.shift(1);changes=ratio.notna() & ~np.isclose(ratio,1,rtol=1e-10,atol=1e-12)
 for date in raw.index[changes]:
  idx=raw.index.get_loc(date);prev=raw.iloc[idx-1];row=raw.loc[date];mult=float(ratio.loc[date]);adjclose=float(row.close/prev.close*mult-1);adjopen=float(row.open/prev.close*mult-1)
  event={'instrument':item['code'],'date':str(date.date()),'previous_observed_date':str(raw.index[idx-1].date()),'factor_ratio':mult,'raw_close_return':float(row.close/prev.close-1),'adjusted_close_return':adjclose,'adjusted_open_gap':adjopen,'extreme':abs(adjclose)>.25 or abs(adjopen)>.25}
  events.append(event)
  if event['extreme']:failures.append({'reason':'material factor-event discontinuity needs independent review',**event})
 universe.append({'instrument':item['code'],'start':'2019-01-01','end':min(end,item['outDate'] or end)})
report={'source':'Tencent raw + Sina hfq factors + official exchange listing union','calendar_source':'Tencent observed SSE Composite, not exchange-certified','first':str(calendar[0].date()),'last':end,'calendar_sessions':len(calendar),'instruments':len(sel),'checks':quality,'factor_events':events,'all_series_return_outliers':return_outliers,'blocking_findings':failures,'limitations':['Unknown missing-session cause is preserved, not called verified suspension','Factors retrospectively obtained; no independently certified event-time/PIT correctness','Delisting liquidation not fully modeled by engine','Unified price-limit proxy does not implement historical ST and board limits']}
(out/'quality.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
pd.concat(allraw).sort_values(['datetime','instrument']).to_csv(out/'raw-with-factor-audit.csv',index=False)
pd.DataFrame(events).to_csv(out/'factor-events.csv',index=False)
pd.DataFrame(universe).to_csv(out/'universe.csv',index=False)
if failures:print(json.dumps({'status':'blocked','findings':failures},ensure_ascii=False));raise SystemExit(2)
bars=pd.concat(allbars).sort_values(['datetime','instrument']);bars.to_csv(out/'bars.csv',index=False)
metadata={'source':'Tencent raw daily + Sina hfq multiplicative factors; official SSE/SZSE listing histories','source_version':'fresh-public-snapshot-2026-11-01','synthetic':False,'region':'cn','currency':'CNY','frequency':'day','price_basis':'adjusted','volume_unit':'units','price_unit':'CNY_per_adjusted_unit','adjustment_identity':'tencent-raw-sina-hfq-multiplicative-v1','factor_definition':'Sina dated hfq multiplier; last known effective date only','volume_basis':'Tencent raw lots*100/Sina factor','universe_scope':'30 predeclared code-stratified pre2019 listings including selected delisted stocks; not CSI300/fullA','limitations':report['limitations']+['Small code-stratified sample not market-representative','Vendor data may be revised; snapshot not point-in-time certified','Calendar is observed SSE Composite sessions, not official holiday calendar'], 'quality_summary':{'unknown_missing_sessions':sum(r['unknown_missing_sessions'] for r in quality),'zero_volume_rows':sum(r['zero_volume_rows'] for r in quality),'factor_events_reviewed':len(events)},'selection_sha256':hashlib.sha256((p/'selection.json').read_bytes()).hexdigest(),'source_amendment_sha256':hashlib.sha256((p/'source-amendment-2.json').read_bytes()).hexdigest(),'quality_sha256':hashlib.sha256((out/'quality.json').read_bytes()).hexdigest()}
(out/'metadata.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'status':'normalized','rows':len(bars),'first':str(bars.datetime.min().date()),'last':str(bars.datetime.max().date()),'factor_events':len(events),'unknown_missing_sessions':metadata['quality_summary']['unknown_missing_sessions']},ensure_ascii=False))
