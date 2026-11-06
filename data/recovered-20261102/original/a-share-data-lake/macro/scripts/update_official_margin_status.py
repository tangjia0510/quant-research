import pathlib,json,datetime
R=pathlib.Path(__file__).resolve().parents[1];reports=[];cal=(R.parent/'reference/normalized/trading-calendar-observed-2019-2026.txt').read_text().split()
for market,cutoff in [('sse','2026-10-30'),('szse','2026-10-29')]:
 p=R/f'logs/{market}-margin-bulk-receipts.jsonl';rr={}
 if p.exists():
  for l in p.read_text().splitlines():
   x=json.loads(l);rr[x['date']]=x
 bulk=len(rr);gap=R/'logs/sse-margin-official-api-gapfill.json'
 if market=='sse' and gap.exists():
  x=json.loads(gap.read_text());rr.setdefault(x['date'],x)
 late=R/'logs/szse-oct30-export-direct-refresh.json';late_dates=0
 if market=='szse' and late.exists():
  x=json.loads(late.read_text())
  if x.get('state')=='downloaded_pure_data_parsed' and x.get('rows')==2118:
   rr.setdefault('2026-10-30',x);late_dates=1;cutoff='2026-10-30'
 target=[x for x in cal if '2019-01-01'<=x<=cutoff];missing=sorted(set(target)-rr.keys());reports.append({'exchange':market.upper(),'state':'complete_requested_core_fields' if not missing else 'running_or_partial','official_export_dates':bulk,'official_API_gapfill_dates':len(rr)-bulk-late_dates,'official_late_export_dates':late_dates,'completed_dates_total':len(rr),'target_dates':len(target),'rows':sum(x['rows'] for x in rr.values()),'latest_date':max(rr,default=None),'earliest_date':min(rr,default=None),'missing_dates':missing,'note':'Source core fields only; not identical to vendor extra fields. Original static404 archived; successful officialAPI fallback separately documented.'})
(R/'logs/official-margin-combined-status.json').write_text(json.dumps({'generated_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'sources':reports,'deduplication_rule':'At most one official source per exchange,date; add API gapfills only when daily export absent'},indent=2));print([{k:v for k,v in x.items() if k!='missing_dates'} for x in reports])
