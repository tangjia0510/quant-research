#!/usr/bin/env python3
"""Public JSON endpoint documented by AKShare stock_value_em; local authored downloader."""
import os,csv,json,time,gzip,hashlib,datetime,pathlib,shutil,fcntl,sys,traceback
import requests
import sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/"catalog"))
from host_gate import host_gate,signal_backpressure
import pyarrow as pa
import pyarrow.parquet as pq
ROOT=pathlib.Path(__file__).resolve().parent/'valuations';ROOT.mkdir(exist_ok=True)
LOGS=ROOT.parent.parent/'logs';URL='https://datacenter-web.eastmoney.com/api/data/v1/get'
SRC=ROOT.parent.parent/'reference/normalized/price-universe.csv';UNIVERSE=ROOT/'universe-frozen.csv'
if not UNIVERSE.exists():shutil.copyfile(SRC,UNIVERSE)
S=requests.Session();S.headers['User-Agent']='Mozilla/5.0 (compatible; local financial research; rate limited)'
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def sha(b):return hashlib.sha256(b).hexdigest()
def write(p,j):
 p.parent.mkdir(parents=True,exist_ok=True);t=p.with_suffix(p.suffix+'.tmp');t.write_text(json.dumps(j,ensure_ascii=False,indent=2));os.replace(t,p)
def pace():
 with open(LOGS/'eastmoney-rate.lock','a+')as f:
  fcntl.flock(f,fcntl.LOCK_EX);p=LOGS/'eastmoney-last-request.txt'
  try:last=float(p.read_text())
  except:last=0
  time.sleep(max(0,1.1-(time.time()-last)));p.write_text(str(time.time()))
def fetch(code,page=1):
 dest=ROOT/'raw'/code/f'page-{page:04}.json.gz';rec=ROOT/'receipts'/code/f'page-{page:04}.json'
 if dest.exists() and rec.exists():
  z=dest.read_bytes();r=json.loads(rec.read_text())
  if sha(z)!=r['stored_sha256']:raise RuntimeError('cache_hash_mismatch')
  return json.loads(gzip.decompress(z)),r
 if shutil.disk_usage(ROOT).free<15*1024**3:raise RuntimeError('disk_floor')
 params={'reportName':'RPT_VALUEANALYSIS_DET','columns':'ALL','sortColumns':'TRADE_DATE','sortTypes':'-1','pageSize':'5000','pageNumber':str(page),'source':'WEB','client':'WEB','quoteColumns':'','filter':f'(SECURITY_CODE="{code}")'}
 attempts=[]
 for n in range(3):
  try:
   with host_gate("eastmoney"):
    r=S.get(URL,params=params,timeout=(10,45));b=r.content
   attempts.append({'at':now(),'status':r.status_code,'bytes':len(b),'sha256':sha(b)})
   if r.status_code in(401,403):raise PermissionError('access_denied_'+str(r.status_code))
   if r.status_code==429:signal_backpressure();time.sleep(60*(n+1));continue
   r.raise_for_status();j=r.json()
   if not j.get('success') and j.get('code')not in(9201,):raise ValueError('api_error '+str(j)[:500])
   z=gzip.compress(b,mtime=0);dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(z)
   receipt={'url':r.url,'acquired_at':now(),'raw_sha256':sha(b),'stored_sha256':sha(z),'raw_bytes':len(b),'stored_bytes':len(z),'path':str(dest.relative_to(ROOT)),'attempts':attempts,'source_version':j.get('version'),'license':'public accessibility observed; redistribution rights not established'};write(rec,receipt);return j,receipt
  except PermissionError:raise
  except Exception as e:attempts.append({'at':now(),'error':str(e)[:500]});time.sleep(3*(n+1))
 write(rec.with_suffix('.failed.json'),{'status':'retry_exhausted','query':params,'attempts':attempts});raise RuntimeError('retry_exhausted')
def acquire(item):
 code=item['code'];j,receipt=fetch(code);res=j.get('result')or{};rows=list(res.get('data')or[]);total=int(res.get('count')or 0);pages=int(res.get('pages')or 0)
 for page in range(2,pages+1):
  nxt,r=fetch(code,page);rows.extend((nxt.get('result')or{}).get('data')or[])
 dates=[x.get('TRADE_DATE')for x in rows];dups=len(dates)-len(set(dates));future=sum(str(d)[:10]>'2026-10-30'for d in dates);status='success'if len(rows)==total and dups==0 else'pagination_mismatch'
 if not rows:status='unavailable'
 normalized=[]
 for x in rows:
  x=dict(x);x['_instrument_requested']=item['instrument'];x['_source']='eastmoney_valueanalysis';x['_acquired_at']=receipt['acquired_at'];x['_pit_ready']=False;x['_after_market_cutoff']=str(x.get('TRADE_DATE',''))[:10]>'2026-10-30';normalized.append(x)
 out=ROOT/'normalized'/(item['instrument']+'.parquet');out.parent.mkdir(parents=True,exist_ok=True)
 if normalized:pq.write_table(pa.Table.from_pylist(normalized),out,compression='zstd')
 result={'instrument':item['instrument'],'code':code,'status':status,'rows':len(rows),'rows_2019_to_cutoff':sum('2019-01-01'<=str(d)[:10]<='2026-10-30'for d in dates),'source_total':total,'pages':pages,'duplicate_dates':dups,'after_cutoff_rows':future,'min_date':min(dates,default=None),'max_date':max(dates,default=None),'parquet_path':str(out.relative_to(ROOT))if normalized else None,'parquet_sha256':sha(out.read_bytes())if normalized else None,'pit_ready':False,'identity_status':item.get('status'),'completed_at':now()}
 write(ROOT/'catalog'/(item['instrument']+'.json'),result);return result
def main():
 items=list(csv.DictReader(open(UNIVERSE)));progress={'started_at':now(),'status':'running','universe_sha256':sha(UNIVERSE.read_bytes()),'expected_tasks':len(items),'tasks':[]}
 for item in items:
  try:r=acquire(item)
  except PermissionError as e:
   r={'instrument':item['instrument'],'status':'access_denied','error':str(e)};progress['tasks'].append(r);progress['status']='host_access_denied';write(ROOT/'catalog/progress.json',progress);return
  except Exception as e:r={'instrument':item['instrument'],'status':'failed','error':str(e)};traceback.print_exc()
  progress['tasks'].append(r);progress['updated_at']=now();progress['success']=sum(x['status']=='success'for x in progress['tasks']);progress['unavailable']=sum(x['status']=='unavailable'for x in progress['tasks']);progress['failed']=sum(x['status']not in('success','unavailable')for x in progress['tasks']);progress['rows']=sum(x.get('rows',0)for x in progress['tasks']);write(ROOT/'catalog/progress.json',progress);print(item['instrument'],r['status'],r.get('rows'),flush=True)
 progress['status']='complete_with_gaps'if progress['unavailable']or progress['failed']else'complete';write(ROOT/'catalog/progress.json',progress)
if __name__=='__main__':main()
