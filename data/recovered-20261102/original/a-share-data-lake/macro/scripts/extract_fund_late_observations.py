"""Preserve source observations beyond initial trading-day cutoff, never execute JS."""
import pathlib,json,re,csv,datetime,hashlib
R=pathlib.Path(__file__).resolve().parents[1];today=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).date().isoformat();recs={};out=[]
for line in (R/'logs/fund-receipts.jsonl').read_text().splitlines():
 x=json.loads(line);recs[x['code']]=x
for code,rec in recs.items():
 text=(R/rec['file']).read_text();rows=[]
 for key in ['Data_netWorthTrend','Data_millionCopiesIncome','Data_sevenDaysYearIncome']:
  m=re.search(r'\b'+re.escape(key)+r'\s*=\s*',text)
  if not m:continue
  try:a=json.JSONDecoder().raw_decode(text[m.end():])[0]
  except ValueError:continue
  if not isinstance(a,list):continue
  for x in a:
   ts=x.get('x') if isinstance(x,dict) else x[0];value=x.get('y') if isinstance(x,dict) else x[1]
   day=datetime.datetime.fromtimestamp(ts/1000,datetime.timezone(datetime.timedelta(hours=8))).date().isoformat()
   if '2026-10-30'<day<=today:rows.append({'date':day,'source_field':key,'as_published_value':value})
 if rows:
  p=R/'normalized/fund_late_observations'/f'{code}.csv';p.parent.mkdir(exist_ok=True)
  with p.open('w') as f:w=csv.DictWriter(f,fieldnames=['date','source_field','as_published_value']);w.writeheader();w.writerows(rows)
  out.append({'code':code,'rows':len(rows),'max_date':max(x['date'] for x in rows),'file':str(p.relative_to(R)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'raw_file':rec['file'],'retrieved_at_utc':rec['retrieved_at_utc']})
obj={'generated_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'local_date':today,'initial_cutoff':'2026-10-30','direct_sources_checked':len(recs),'funds_with_later_observations':len(out),'rows':sum(x['rows'] for x in out),'files':out,'note':'Read existing raw JSON literals only. Source-field-specific values, not combined NAV/income. Weekend money income may exist beyond last A-share trading day. Do not infer new market trading day.'}
p=R/'logs/fund-late-observations.json';p.write_text(json.dumps(obj,indent=2));print({k:v for k,v in obj.items() if k!='files'})
