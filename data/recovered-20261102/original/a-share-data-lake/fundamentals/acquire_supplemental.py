#!/usr/bin/env python3
"""Read-only public report batch acquisition; no external project execution."""
import os,sys,json,time,gzip,hashlib,datetime,pathlib,shutil,fcntl,collections,traceback
import requests
from urllib.parse import urlparse,parse_qs
import sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/"catalog"))
from host_gate import host_gate,signal_backpressure
import pyarrow as pa
import pyarrow.parquet as pq
ROOT=pathlib.Path(__file__).resolve().parent/'supplemental';ROOT.mkdir(exist_ok=True)
LOGS=ROOT.parent.parent/'logs';LOGS.mkdir(exist_ok=True)
URL='https://datacenter-web.eastmoney.com/api/data/v1/get'
REPORTS={'forecast':'RPT_PUBLIC_OP_NEWPREDICT','express':'RPT_FCI_PERFORMANCEE','disclosure_schedule':'RPT_PUBLIC_BS_APPOIN'}
PERIODS=[f'{y}-{q}' for y in range(2019,2027) for q in ['03-31','06-30','09-30','12-31'] if f'{y}-{q}'<='2026-09-30']
SESSION=requests.Session();SESSION.headers['User-Agent']='Mozilla/5.0 (compatible; local financial research; rate limited)'
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def sha(b):return hashlib.sha256(b).hexdigest()
def write_json(p,x):
 p.parent.mkdir(parents=True,exist_ok=True); t=p.with_suffix(p.suffix+'.tmp');t.write_text(json.dumps(x,ensure_ascii=False,indent=2));os.replace(t,p)
def pace():
 with open(LOGS/'eastmoney-rate.lock','a+') as f:
  fcntl.flock(f,fcntl.LOCK_EX)
  p=LOGS/'eastmoney-last-request.txt'
  try:last=float(p.read_text())
  except:last=0
  time.sleep(max(0,1.1-(time.time()-last)));p.write_text(str(time.time()))
def fetch(name,date,page):
 dest=ROOT/'raw'/name/date/f'page-{page:04}.json.gz';rec=ROOT/'receipts'/name/date/f'page-{page:04}.json'
 if dest.exists() and rec.exists():
  data=dest.read_bytes();r=json.loads(rec.read_text())
  if sha(data)==r['stored_sha256']:return json.loads(gzip.decompress(data)),r
  raise RuntimeError('cache hash mismatch '+str(dest))
 if shutil.disk_usage(ROOT).free<15*1024**3:raise RuntimeError('global_disk_free_floor')
 params={'reportName':REPORTS[name],'columns':'ALL','filter':f"({'REPORTDATE' if name=='earnings' else 'REPORT_DATE'}='{date}')",'pageSize':500,'pageNumber':page,'sortColumns':'SECURITY_CODE','sortTypes':'1','source':'WEB','client':'WEB'}
 # Stable composite ordering for newly started forecast partitions only.
 # Existing first-page receipt fixes ordering for a partially cached partition;
 # never mix old/new sort orders within one immutable raw snapshot.
 if name=='forecast':
  first_receipt=ROOT/'receipts'/name/date/'page-0001.json'
  if first_receipt.exists():
   prior=json.loads(first_receipt.read_text());query=parse_qs(urlparse(prior['url']).query)
   params['sortColumns']=query.get('sortColumns',['SECURITY_CODE'])[0]
   params['sortTypes']=query.get('sortTypes',['1'])[0]
  else:
   params['sortColumns']='SECURITY_CODE,PREDICT_FINANCE_CODE,NOTICE_DATE'
   params['sortTypes']='1,1,1'
 attempts=[]
 for attempt in range(3):
  start=now()
  try:
   with host_gate("eastmoney"):
    response=SESSION.get(URL,params=params,timeout=(10,45)); body=response.content
   attempts.append({'at':start,'status':response.status_code,'bytes':len(body),'sha256':sha(body)})
   if response.status_code in (401,403):raise PermissionError(f'access_denied_{response.status_code}')
   if response.status_code==429:
    signal_backpressure()
    time.sleep(60*(attempt+1));continue
   response.raise_for_status();j=response.json()
   if not j.get('success') or not j.get('result'):
    raise ValueError('api_error: '+json.dumps(j,ensure_ascii=False)[:600])
   compressed=gzip.compress(body,mtime=0);dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(compressed)
   receipt={'source':'Eastmoney public datacenter','url':response.url,'acquired_at':now(),'report':name,'report_period':date,'page':page,'raw_sha256':sha(body),'stored_sha256':sha(compressed),'raw_bytes':len(body),'stored_bytes':len(compressed),'path':str(dest.relative_to(ROOT)),'attempts':attempts,'license':'public accessibility observed; redistribution rights not established','source_version':j.get('version')}
   write_json(rec,receipt);return j,receipt
  except PermissionError:raise
  except Exception as e:
   attempts.append({'at':now(),'error':str(e)[:600]});time.sleep(3*(attempt+1))
 write_json(rec.with_suffix('.failed.json'),{'url':URL,'params':params,'attempts':attempts,'status':'retry_exhausted'})
 raise RuntimeError('retry_exhausted '+name+' '+date+' '+str(page))
def run_period(name,date):
 rows=[];receipts=[];first,r=fetch(name,date,1);total=int(first['result']['count']);pages=int(first['result']['pages']);rows.extend(first['result']['data']);receipts.append(r)
 for page in range(2,pages+1):
  j,r=fetch(name,date,page)
  if int(j['result']['count'])!=total:raise RuntimeError('source_count_changed_during_pagination')
  rows.extend(j['result']['data']);receipts.append(r)
 keys=[(x.get('SECUCODE'),x.get('SECURITY_CODE'),x.get('REPORT_DATE',x.get('REPORTDATE')),x.get('REPORT_TYPE_CODE'),x.get('PREDICT_FINANCE_CODE'),x.get('NOTICE_DATE')) for x in rows]
 dup=len(keys)-len(set(keys))
 if len(rows)!=total or dup:raise RuntimeError(f'pagination_invalid count={len(rows)} expected={total} duplicate={dup}')
 normalized=[]
 for x in rows:
  x=dict(x);s=x.get('SECUCODE','');code=x.get('SECURITY_CODE','')
  x['_instrument']=(s.split('.')[-1].lower()+'.'+code) if '.'in s else None
  x['_acquired_at']=receipts[0]['acquired_at'];x['_source']='eastmoney_datacenter';x['_source_revision_history_available']=False
  x['_pit_ready']=False # NOTICE_DATE may be original date attached to a revised value
  notice=x.get('NOTICE_DATE') or x.get('ACTUAL_PUBLISH_DATE') or x.get('UPDATE_DATE'); cutoff=(datetime.datetime.fromisoformat(receipts[0]['acquired_at']).astimezone(datetime.timezone(datetime.timedelta(hours=8)))).date().isoformat()
  x['_notice_date_future_at_acquisition']=bool(notice and str(notice)[:10]>cutoff)
  x['_asof_eligible_by_date_only']=bool(notice and str(notice)[:10]<=cutoff) # NOT PIT safe: revisions unavailable
  normalized.append(x)
 table=pa.Table.from_pylist(normalized);out=ROOT/'normalized'/name/(date+'.parquet');out.parent.mkdir(parents=True,exist_ok=True);pq.write_table(table,out,compression='zstd')
 noticenull=sum(not x.get('NOTICE_DATE') for x in rows)
 report={'status':'success','report':name,'period':date,'rows':len(rows),'source_total':total,'pages':pages,'unique_securities':len(set(x.get('SECURITY_CODE') for x in rows)),'duplicate_keys':dup,'notice_date_missing':noticenull,'future_notice_dates':sum(x['_notice_date_future_at_acquisition'] for x in normalized),'asof_date_eligible_rows':sum(x['_asof_eligible_by_date_only'] for x in normalized),'notice_date_min':min((x['NOTICE_DATE'] for x in rows if x.get('NOTICE_DATE')),default=None),'notice_date_max':max((x['NOTICE_DATE'] for x in rows if x.get('NOTICE_DATE')),default=None),'periods_observed':sorted(set(str(x.get('REPORT_DATE',x.get('REPORTDATE'))) for x in rows)),'parquet_path':str(out.relative_to(ROOT)),'parquet_sha256':sha(out.read_bytes()),'fields':table.column_names,'pit_ready':False,'limitations':['Latest vendor snapshot; historic revision vintages unavailable. NOTICE_DATE does not establish first availability of every revised value.','Vendor financial statement summaries, not full original filings; preserve all returned fields.','No current-stock universe filtering; compare with independent security master before use.'],'completed_at':now()}
 write_json(ROOT/'catalog'/name/(date+'.json'),report);return report
def main():
 kinds=sys.argv[1:] or list(REPORTS)
 progress={'started_at':now(),'expected_periods':PERIODS,'reports':kinds,'expected_tasks':len(PERIODS)*len(kinds),'tasks':[],'status':'running'}
 for date in reversed(PERIODS):
  for name in kinds:
   try: item=run_period(name,date)
   except PermissionError as e:
    item={'report':name,'period':date,'status':'access_denied','error':str(e)};progress['tasks'].append(item);progress['status']='host_access_denied';write_json(ROOT/'catalog/progress.json',progress);return 2
   except Exception as e:item={'report':name,'period':date,'status':'failed','error':str(e)};traceback.print_exc()
   progress['tasks'].append(item);progress['updated_at']=now();progress['success']=sum(x['status']=='success' for x in progress['tasks']);progress['failed']=len(progress['tasks'])-progress['success'];progress['rows']=sum(x.get('rows',0) for x in progress['tasks']);write_json(ROOT/'catalog/progress.json',progress)
   print(name,date,item['status'],item.get('rows'),flush=True)
 progress['status']='complete_with_gaps' if progress['failed'] else 'complete';progress['completed_at']=now();write_json(ROOT/'catalog/progress.json',progress)
if __name__=='__main__':sys.exit(main())
