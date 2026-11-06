"""Offline audit of an immutable checkpoint snapshot; never changes acquisition files."""
import csv,json,hashlib,datetime,collections,math
from pathlib import Path
B=Path(__file__).resolve().parents[1]
snapshot=(B/'catalog/factor-status.json').read_bytes();s=json.loads(snapshot)
counts=collections.Counter();exchanges={};problems=[];sentinels=[];events=0;future=0;retrieval=[];effective=[]
for code,item in s['items'].items():
 counts[item['status']]+=1;exchanges.setdefault(code[:2],collections.Counter())[item['status']]+=1
 if item['status']!='complete':continue
 symbol=code.replace('.','');raw=B/'raw/sina_factors'/f'{symbol}.js';norm=B/'normalized/factors'/f'{symbol}.csv'
 try:
  rb=raw.read_bytes();nb=norm.read_bytes()
  for key,payload in [('raw_sha256',rb),('normalized_sha256',nb)]:
   if hashlib.sha256(payload).hexdigest()!=item[key]:problems.append([code,key,'hash_mismatch'])
  obj=json.JSONDecoder().raw_decode(rb.decode('utf-8-sig')[rb.decode('utf-8-sig').find('{'):])[0]
  rows=list(csv.DictReader(nb.decode().splitlines()))
  expected=sorted([(r['d'],str(r['f'])) for r in obj['data']])
  actual=[(r['effective_date'],r['factor']) for r in rows]
  if actual!=expected:problems.append([code,'payload_normalization_mismatch'])
  if len(rows)!=item['events']:problems.append([code,'count_mismatch'])
  if len({r[0] for r in actual})!=len(actual):problems.append([code,'duplicate_date'])
  if any(not math.isfinite(float(v)) or float(v)<=0 for _,v in actual):problems.append([code,'invalid_factor'])
  for day,v in actual:
   datetime.date.fromisoformat(day)
   if day<'1990-01-01':sentinels.append({'instrument':code,'date':day,'factor':v})
   if day>'2026-10-30':future+=1
  events+=len(rows);retrieval.extend(r['retrieved_at'] for r in rows);effective.extend(r['effective_date'] for r in rows)
 except Exception as e:problems.append([code,type(e).__name__,str(e)])
out={'audit_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'checkpoint_sha256':hashlib.sha256(snapshot).hexdigest(),'checkpoint_updated_at':s.get('updated_at'),'acquisition_status':s['status'],'target':s['target_count'],'status_counts':dict(counts),'exchange_status_counts':exchanges,'not_attempted':s['target_count']-len(s['items']),'events_checked':events,'retrieval_min':min(retrieval) if retrieval else None,'retrieval_max':max(retrieval) if retrieval else None,'effective_max':max(effective) if effective else None,'integrity_problems':problems,'pre1990_sentinel_count':len(sentinels),'pre1990_sentinel_examples':sentinels[:20],'events_after_requested_cutoff':future,'caveats':['Integrity audit is not market truth verification.','Pre-1990 rows are vendor basis sentinels, not real corporate actions.','Current cumulative factors are not historical factor vintages or PIT data.','Price adjustment uses factor as-of date; never forward-fill from a future event. Volume/factor is synthetic adjusted volume, not actual traded volume.']}
p=B/'catalog/factor-integrity-audit.json';p.write_text(json.dumps(out,ensure_ascii=False,indent=2));print(json.dumps({k:v for k,v in out.items() if k not in ['pre1990_sentinel_examples','caveats']}))
