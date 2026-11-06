import csv,json,re,hashlib,datetime
from pathlib import Path
BASE=Path(__file__).resolve().parents[1];reports={}
for name in ['sharebonus','equity','suspensions','rights','seasoned_offerings','repurchases','unlock_events']:
 p=BASE/'catalog'/f'{name}-status.json'
 if not p.exists():continue
 cat=json.loads(p.read_text())
 if cat.get('status')!='complete':continue
 file=BASE/'normalized'/f'{name}-all.csv';rows=list(csv.DictReader(file.open()));d={'rows':len(rows),'sha256':hashlib.sha256(file.read_bytes()).hexdigest(),'date_fields':{}}
 fields=[k for k in rows[0] if any(v in k for v in ['DATE','TIME'])]
 for field in fields:
  vals=[r[field][:10] for r in rows if re.match(r'^\d{4}-\d{2}-\d{2}',r.get(field,''))]
  d['date_fields'][field]={'nonempty_iso_dates':len(vals),'min':min(vals) if vals else None,'max':max(vals) if vals else None,'after_market_cutoff_2026_10_30':sum(v>'2026-10-30' for v in vals),'after_collection_date_2026_11_01':sum(v>'2026-11-01' for v in vals)}
 if name=='sharebonus':
  tested=0;bad=[]
  for r in rows:
   m=re.search(r'10派\s*([\d.]+)',r.get('IMPL_PLAN_PROFILE',''))
   if m and r.get('PRETAX_BONUS_RMB'):
    tested+=1
    if abs(float(m.group(1))-float(r['PRETAX_BONUS_RMB']))>.0001:bad.append({k:r.get(k) for k in ['SECUCODE','REPORT_DATE','IMPL_PLAN_PROFILE','PRETAX_BONUS_RMB']})
  d['cash_per_ten_profile_check']={'tested':tested,'mismatches':len(bad),'examples':bad[:10]};d['payment_date_field_present']=any('PAY' in k for k in rows[0]);d['stage_counts']={s:sum(r['ASSIGN_PROGRESS']==s for r in rows) for s in set(r['ASSIGN_PROGRESS'] for r in rows)}
 reports[name]=d
out={'generated_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'reports':reports,'policy':'Future scheduled/notice fields are preserved with counts; never auto-treated as historically available; no as-of or completeness certification'}
(BASE/'catalog/event-field-quality.json').write_text(json.dumps(out,ensure_ascii=False,indent=2));print(json.dumps({k:{x:v for x,v in d.items() if x!='date_fields'} for k,d in reports.items()},ensure_ascii=False))
