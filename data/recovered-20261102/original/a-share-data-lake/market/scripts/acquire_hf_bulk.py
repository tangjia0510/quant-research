#!/usr/bin/env python3
import concurrent.futures as cf,datetime as dt,hashlib,json,os,shutil,threading,time
from pathlib import Path
import requests
R=Path(__file__).resolve().parents[1]/'hf_bulk';P=R.parent/'probes'; REV='94d41d1a0f8557682c6acfa829e9fc2c946b4605'
D=json.loads((P/'hf-parquet.txt').read_text());lock=threading.Lock();stop=threading.Event()
def now():return dt.datetime.now(dt.timezone.utc).isoformat()
def write(p,d):
 t=p.with_suffix(p.suffix+'.tmp');t.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n');os.replace(t,p)
def fetch(x):
 name=x['filename'];expected=x['size'];dest=R/'raw'/name;receipt=R/'metadata'/(name+'.json');url=f'https://huggingface.co/datasets/ellendan/a-share-prices/resolve/{REV}/main_data/train/{name}'
 if dest.exists() and receipt.exists():return json.loads(receipt.read_text())
 attempts=[]
 for attempt in range(1,4):
  if stop.is_set():return {'file':name,'state':'not_attempted_source_blocked'}
  if shutil.disk_usage(R).free<15*1024**3:stop.set();return {'file':name,'state':'disk_floor_blocked'}
  start=now();part=dest.with_suffix('.part');h=hashlib.sha256();size=0
  try:
   with requests.get(url,stream=True,timeout=(10,90)) as response:
    if response.status_code in (401,403,429,567):
     stop.set();result={'file':name,'state':'source_blocked','http_status':response.status_code,'url':url,'time':now()};write(receipt,result);return result
    response.raise_for_status()
    with part.open('wb') as f:
     for chunk in response.iter_content(1024*1024):
      if not chunk:continue
      size+=len(chunk)
      if size>expected+1024:raise ValueError('Response exceeds API-declared size')
      f.write(chunk);h.update(chunk)
    if size!=expected:raise ValueError(f'Downloaded bytes {size} != declared {expected}')
   os.replace(part,dest)
   result={'file':name,'state':'downloaded','url':url,'dataset_revision':REV,'bytes':size,'sha256':h.hexdigest(),'started_utc':start,'finished_utc':now(),'attempt':attempt,'declared_license':'MIT (publisher metadata; underlying vendor rights not independently verified)','not_latest_market_data':True}
   write(receipt,result);print(json.dumps(result),flush=True);return result
  except Exception as e:
   attempts.append({'attempt':attempt,'error':str(e),'bytes_before_error':size,'time':now()})
   if attempt==3:
    result={'file':name,'state':'retry_exhausted','url':url,'attempts':attempts};write(receipt,result);return result
   time.sleep(3*attempt)
 return None
for name in ['hf-readme.txt','hf-parquet.txt','hf-parquet-revision.json']:
 shutil.copy2(P/name,R/'metadata'/name)
write(R/'metadata/source.json',{'dataset':'ellendan/a-share-prices','main_revision':'c74a2d70361e8cae2a9093e1e293e31e6c421d62','parquet_revision':REV,'metadata_url':'https://datasets-server.huggingface.co/parquet?dataset=ellendan/a-share-prices','source_asof':'2026-03-03','declared_license':'mit','limitations':['Publisher license declaration is not independent verification of underlying data rights','Raw unadjusted source is separate from Tencent; do not merge by assumed equality','Missing paused sessions are excluded by publisher; is_st no longer available','Publisher historical coverage and units must be validated from actual values'],'units':{'volume':'lots','turnover':'thousand CNY','total_share':'10k shares','float_share':'10k shares','free_share':'10k shares','total_mv':'10k CNY','circ_mv':'10k CNY'}})
results=[]
with cf.ThreadPoolExecutor(max_workers=2) as pool:
 for fut in cf.as_completed([pool.submit(fetch,x) for x in D['parquet_files']]):
  results.append(fut.result());write(R/'progress.json',{'updated_utc':now(),'expected_files':len(D['parquet_files']),'terminal_files':len(results),'results':results,'state':'running'})
write(R/'progress.json',{'updated_utc':now(),'expected_files':len(D['parquet_files']),'terminal_files':len(results),'results':results,'state':'bounded_pass_finished','complete':all(x.get('state')=='downloaded' for x in results)})
