import requests,time,json,hashlib,datetime,pathlib,fcntl,calendar,gzip,shutil
import pandas as pd
import subprocess
import sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[2]/"catalog"))
from host_gate import host_gate, signal_backpressure
R=pathlib.Path(__file__).resolve().parents[1];O=R/'raw/margin_detail';O.mkdir(exist_ok=True);N=R/'normalized/margin_detail';N.mkdir(exist_ok=True);L=R.parent/'logs';S=requests.Session();receipts=R/'logs/margin-detail-receipts.jsonl';coverage=R/'logs/margin-detail-coverage.json';fails=R/'logs/margin-detail-failures.json';done=json.loads(coverage.read_text()) if coverage.exists() else [];errors=[]
trading_days=set((R.parent/'reference/normalized/trading-calendar-observed-2019-2026.txt').read_text().split())
cols='DATE,SCODE,MARKET,SECNAME,RZYE,RQYL,RZRQYE,RQYE,RQMCL,RZMRE,RZCHE,RZJME,RQCHL,RQJMG,SPJ,ZDF,SECUCODE'
def limit():
 with (L/'eastmoney-rate.lock').open('a+') as f:
  fcntl.flock(f,fcntl.LOCK_EX);p=L/'eastmoney-last-request.txt';last=float(p.read_text()) if p.exists() else 0;time.sleep(max(0,1.1-(time.time()-last)));p.write_text(str(time.time()));fcntl.flock(f,fcntl.LOCK_UN)
def fetch(ym,pg,a,b):
 p=O/f'{ym}-{pg:04}.json.gz'
 if p.exists():return json.loads(gzip.decompress(p.read_bytes()))
 if shutil.disk_usage(R).free<15*1024**3:raise PermissionError('diskfloor')
 params={'reportName':'RPTA_WEB_RZRQ_GGMX','columns':cols,'pageNumber':pg,'pageSize':500,'sortColumns':'DATE,SCODE','sortTypes':'-1,1','source':'WEB','client':'WEB','filter':f"(DATE>='{a}')(DATE<='{b}')"}
 for attempt in range(3):
  try:
   with host_gate('eastmoney'):
    r=S.get('https://datacenter-web.eastmoney.com/api/data/v1/get',params=params,timeout=45);body=r.content
   if r.status_code in [401,403,429]:raise PermissionError(f'access/rate_restriction_{r.status_code}')
   r.raise_for_status();d=r.json()
   if not d.get('success') or not d.get('result'):
    signal_backpressure();raise ValueError(str(d)[:250])
   p.write_bytes(gzip.compress(r.content));rec={'file':str(p.relative_to(R)),'source_url':r.url,'raw_sha256':hashlib.sha256(r.content).hexdigest(),'stored_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'raw_bytes':len(r.content),'retrieved_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'rows':len(d['result']['data']),'pages':d['result']['pages'],'expected_count':d['result']['count']}
   with receipts.open('a') as f:f.write(json.dumps(rec)+'\n')
   return d
  except PermissionError:raise
  except Exception:
   if attempt==2:raise
   time.sleep(3*(attempt+1))
months=[(y,m) for y in range(2019,2027) for m in range(1,13) if (y,m)<=(2026,10)]
try:
 for y,m in reversed(months):
  ym=f'{y}-{m:02}';a=ym+'-01';b=min(f'{ym}-{calendar.monthrange(y,m)[1]:02}','2026-10-30');out=N/(ym+'.parquet')
  if any(x['month']==ym and x['status']=='complete_api_response' for x in done) and out.exists():continue
  try:
   rs=[];expected=0;pages=0
   for day in [29,22,15,8,1]:
    if day>int(b[-2:]):continue
    sa=ym+f'-{day:02}';sb=ym+f'-{min(day+6,int(b[-2:])):02}';shard=ym+f'-d{day:02}'
    if not any(sa<=x<=sb for x in trading_days):
     print('SKIP_NONTRADING_SHARD',shard,flush=True);continue
    first=fetch(shard,1,sa,sb)['result'];npages=int(first['pages']);expected+=int(first['count']);pages+=npages;rs.extend(first['data']);print('START_SHARD',shard,npages,first['count'],flush=True)
    for pg in range(2,npages+1):
     d=fetch(shard,pg,sa,sb)['result'];rs.extend(d['data']);(R/'logs/margin-detail-progress.json').write_text(json.dumps({'state':'running','month':ym,'shard':shard,'page':pg,'shard_pages':npages,'month_rows_downloaded':len(rs),'completed_months':len(done),'completed_rows':sum(x['rows'] for x in done)},indent=2))
   df=pd.DataFrame(rs);dupes=int(df.duplicated(['DATE','SCODE']).sum());status='complete_api_response' if len(rs)==expected and dupes==0 else 'count_or_duplicate_error'
   if status!='complete_api_response':raise ValueError(f'count_or_duplicate_error rows={len(rs)} expected={expected} duplicates={dupes}')
   tmp=out.with_suffix('.tmp.parquet');df.to_parquet(tmp,index=False);tmp.replace(out);done.append({'month':ym,'rows':len(rs),'expected':expected,'pages':pages,'duplicates':dupes,'status':status,'min_date':str(df.DATE.min()),'max_date':str(df.DATE.max()),'file':str(out.relative_to(R)),'sha256':hashlib.sha256(out.read_bytes()).hexdigest()});coverage.write_text(json.dumps(done,indent=2));(R/'logs/margin-detail-progress.json').write_text(json.dumps({'state':'running','month_just_completed':ym,'completed_months':len(done),'target_months':len(months),'completed_rows':sum(x['rows'] for x in done)},indent=2));subprocess.run([sys.executable,str(R/'scripts/update_margin_status.py')],stdout=subprocess.DEVNULL,check=False);print('DONE_MONTH',ym,len(rs),status,flush=True)
  except PermissionError:raise
  except Exception as e:errors.append({'month':ym,'error':str(e)});fails.write_text(json.dumps(errors,indent=2));print('FAIL_MONTH',ym,str(e),flush=True)
except PermissionError as e:errors.append({'terminal':str(e)});print('STOP',str(e),flush=True)
finally:
 fails.write_text(json.dumps(errors,indent=2));(R/'logs/margin-detail-progress.json').write_text(json.dumps({'state':'first_pass_complete' if len(done)==len(months) else 'partial_terminal','completed_months':len(done),'target_months':len(months),'completed_rows':sum(x['rows'] for x in done),'errors':len(errors)},indent=2));print('FINISHED',len(done),len(errors),flush=True)
