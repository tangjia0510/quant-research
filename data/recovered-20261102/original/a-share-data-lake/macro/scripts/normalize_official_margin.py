import pathlib,json,datetime,hashlib
import pandas as pd
R=pathlib.Path(__file__).resolve().parents[1];O=R/'normalized/official_margin_monthly';O.mkdir(exist_ok=True);calendar=(R.parent/'reference/normalized/trading-calendar-observed-2019-2026.txt').read_text().split();reports=[]
for market,cutoff in [('sse','2026-10-30'),('szse','2026-10-29')]:
 recp=R/f'logs/{market}-margin-bulk-receipts.jsonl'
 if not recp.exists():continue
 recs={}
 for l in recp.read_text().splitlines():
  x=json.loads(l);recs[x['date']]=x
 gap=R/'logs/sse-margin-official-api-gapfill.json'
 if market=='sse' and gap.exists():
  g=json.loads(gap.read_text());recs.setdefault(g['date'],g)
 months=sorted({x[:7] for x in recs})
 for month in months:
  expected=[x for x in calendar if x.startswith(month) and x<=cutoff];found=[x for x in expected if x in recs]
  if len(found)!=len(expected):continue
  out=O/(market+'-'+month+'.parquet');rows=[]
  for day in found:
   p=R/recs[day]['normalized_file'];d=pd.read_csv(p,dtype=str);outd=pd.DataFrame({'date':d['date'],'exchange':market.upper(),'code':d['标的证券代码'] if market=='sse' else d['证券代码'],'name':d['标的证券简称'] if market=='sse' else d['证券简称']})
   mappings=({'本日融资余额(元)':'financing_balance_cny','本日融资买入额(元)':'financing_buy_cny','本日融资偿还额(元)':'financing_repay_cny','本日融券余量':'lending_quantity','本日融券卖出量':'lending_sell_quantity','本日融券偿还量':'lending_repay_quantity'} if market=='sse' else {'融资余额(元)':'financing_balance_cny','融资买入额(元)':'financing_buy_cny','融券卖出量(股/份)':'lending_sell_quantity','融券余量(股/份)':'lending_quantity','融券余额(元)':'lending_balance_cny','融资融券余额(元)':'combined_margin_balance_cny'})
   for src,dst in mappings.items():outd[dst]=pd.to_numeric(d[src].str.replace(',','',regex=False),errors='coerce')
   outd['source_file']=recs[day]['raw_file'];outd['retrieved_at_utc']=recs[day]['retrieved_at_utc'];outd['date_basis']=recs[day].get('date_basis','official_export_request_date');rows.append(outd)
  df=pd.concat(rows,ignore_index=True);dup=int(df.duplicated(['date','exchange','code']).sum())
  if dup:raise ValueError(f'duplicate keys {market} {month}')
  tmp=out.with_suffix('.tmp.parquet');df.to_parquet(tmp,index=False);tmp.replace(out);reports.append({'exchange':market.upper(),'month':month,'state':'all_observed_calendar_dates_acquired_through_source_cutoff','rows':len(df),'dates':len(found),'expected_dates':len(expected),'min_date':df.date.min(),'max_date':df.date.max(),'duplicate_keys':dup,'file':str(out.relative_to(R)),'sha256':hashlib.sha256(out.read_bytes()).hexdigest()})
obj={'generated_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'partitions':reports,'note':'Official SSE/SZSE fields differ, absent fields stay absent. Quantities are shares/fund units according to instrument. Do not concatenate with overlapping vendor records or daily source CSVs; choose explicitly by source.'};(R/'logs/official-margin-monthly-coverage.json').write_text(json.dumps(obj,indent=2));print(len(reports),sum(x['rows'] for x in reports))
