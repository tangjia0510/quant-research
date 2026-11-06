"""Read-only final per-security valuation catalog/hash/row/freshness audit."""
import pathlib,json,hashlib,collections,datetime
import pyarrow.parquet as pq
ROOT=pathlib.Path(__file__).resolve().parent/'valuations';j=json.loads((ROOT/'catalog/progress.json').read_text());problems=[];dates=collections.Counter();statuses=collections.Counter();rows=0;receipts=0;rawbytes=0;storedbytes=0;timestamps=[];units=set();afters=0;missing_dates=[]
for x in j['tasks']:
 statuses[x['status']]+=1
 if x['status']=='success':
  p=ROOT/x['parquet_path']
  if hashlib.sha256(p.read_bytes()).hexdigest()!=x['parquet_sha256']:problems.append({'instrument':x['instrument'],'error':'normalized_hash_mismatch'})
  if pq.read_metadata(p).num_rows!=x['rows']:problems.append({'instrument':x['instrument'],'error':'normalized_row_mismatch'})
  rows+=x['rows'];dates[str(x['max_date'])[:10]]+=1;afters+=x.get('after_cutoff_rows',0)
  if not x.get('max_date'):missing_dates.append(x['instrument'])
for p in (ROOT/'receipts').glob('**/*.json'):
 r=json.loads(p.read_text())
 if not r.get('path')or not r.get('stored_sha256'):continue
 f=ROOT/r['path']
 if not f.exists()or hashlib.sha256(f.read_bytes()).hexdigest()!=r['stored_sha256']:problems.append({'receipt':str(p.relative_to(ROOT)),'error':'raw_hash_mismatch'})
 receipts+=1;rawbytes+=r.get('raw_bytes',0);storedbytes+=r.get('stored_bytes',0)
 if r.get('acquired_at'):timestamps.append(r['acquired_at'])
out={'generated_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source_status':j['status'],'expected_securities':j['expected_tasks'],'attempted':len(j['tasks']),'unattempted':j['expected_tasks']-len(j['tasks']),'status_counts':dict(statuses),'rows_verified':rows,'per_security_last_date_distribution':dict(sorted(dates.items())),'target_last_complete_market_day':'2026-10-30','after_target_date_rows':afters,'missing_last_date_successes':missing_dates,'raw_receipts_verified':receipts,'raw_response_bytes':rawbytes,'stored_raw_bytes':storedbytes,'retrieval_utc_min':min(timestamps,default=None),'retrieval_utc_max':max(timestamps,default=None),'integrity_problems':problems,'pit_ready':False,'limitations':['API no-data is not zero valuation; unavailable histories remain gaps.','A latest date does not prove every stock-date or field is populated. Suspensions, listing/delisting and source coverage affect histories.','Source financial-definition and historical-revision differences prevent automatic cross-vendor stitching.']}
(ROOT/'catalog/final-audit.json').write_text(json.dumps(out,ensure_ascii=False,indent=2));print({k:v for k,v in out.items()if k!='per_security_last_date_distribution'})
