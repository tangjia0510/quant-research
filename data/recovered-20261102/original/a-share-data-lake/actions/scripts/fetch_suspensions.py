"""Public suspension-event query; NOT a historical point-in-time daily status panel."""
import csv,datetime,fcntl,hashlib,json,os,shutil,time,urllib.parse,urllib.request,urllib.error
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"catalog"))
from host_gate import host_gate,signal_backpressure
BASE=Path(__file__).resolve().parents[1];LAKE=BASE.parent;RAW=BASE/'raw/eastmoney_suspensions';RAW.mkdir(exist_ok=True)
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def sha(b):return hashlib.sha256(b).hexdigest()
def atom(p,d):t=p.with_suffix(p.suffix+'.tmp');t.write_text(json.dumps(d,ensure_ascii=False,indent=2));os.replace(t,p)
def rate():
 with (LAKE/'logs/eastmoney-rate.lock').open('a') as f:
  fcntl.flock(f,fcntl.LOCK_EX);p=LAKE/'logs/eastmoney-last-request.txt'
  try:last=float(p.read_text())
  except:last=0
  time.sleep(max(0,1.1-(time.time()-last)));p.write_text(str(time.time()))
def get(page):
 params={'sortColumns':'SUSPEND_START_DATE,SECURITY_CODE','sortTypes':'-1,1','pageSize':'500','pageNumber':str(page),'reportName':'RPT_CUSTOM_SUSPEND_DATA_INTERFACE','columns':'ALL','source':'WEB','client':'WEB',"filter":"(MARKET=\"全部\")(DATETIME='2019-01-02')"}
 url='https://datacenter-web.eastmoney.com/api/data/v1/get?'+urllib.parse.urlencode(params);path=RAW/f'page-{page:04d}.json';meta=path.with_suffix('.receipt.json')
 if path.exists() and meta.exists() and sha(path.read_bytes())==json.loads(meta.read_text())['sha256']:return json.loads(path.read_bytes())
 for attempt in range(1,4):
  try:
   with host_gate('eastmoney'):
    with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'}),timeout=25) as r:b=r.read(8*1024*1024);status=r.status
   d=json.loads(b)
   if not d.get('success') or not isinstance(d.get('result',{}).get('data'),list):raise ValueError('Unexpected response '+str(d)[:200])
   path.write_bytes(b);atom(meta,{'url':url,'retrieved_at':now(),'attempt':attempt,'status':status,'sha256':sha(b),'bytes':len(b)});return d
  except Exception as e:
   with (BASE/'logs/suspensions-errors.jsonl').open('a') as f:f.write(json.dumps({'page':page,'at':now(),'attempt':attempt,'url':url,'error':str(e)})+'\n')
   if isinstance(e,urllib.error.HTTPError) and e.code==429:signal_backpressure('eastmoney',300)
   if isinstance(e,urllib.error.HTTPError) and e.code in (401,403,429,567):raise
   if attempt==3:raise
   time.sleep(2**attempt)
def main():
 first=get(1);pages=int(first['result']['pages']);expected=int(first['result']['count']);rows=[];counts=[];state={'started_at':now(),'target_pages':pages,'declared_rows':expected,'status':'running'}
 atom(BASE/'catalog/suspensions-status.json',state)
 for page in range(1,pages+1):
  if shutil.disk_usage(BASE).free<15*1024**3:raise RuntimeError('Disk free floor')
  d=first if page==1 else get(page)
  if int(d['result']['pages'])!=pages or int(d['result']['count'])!=expected:raise ValueError('Source pagination changed during collection')
  part=d['result']['data'];rows.extend(part);counts.append(len(part));state.update(pages_complete=page,rows_downloaded=len(rows),updated_at=now());atom(BASE/'catalog/suspensions-status.json',state)
  if page%10==0:print(json.dumps(state),flush=True)
 if len(rows)!=expected:raise ValueError(f'Row count mismatch {len(rows)} != {expected}')
 keys=sorted({k for r in rows for k in r});out=BASE/'normalized/suspensions-all.csv'
 with out.open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(rows)
 exact=len({json.dumps(r,sort_keys=True) for r in rows});dates=[r['SUSPEND_START_DATE'][:10] for r in rows if r.get('SUSPEND_START_DATE')]
 state.update(status='complete',complete_at=now(),source_rows=len(rows),exact_unique_rows=exact,duplicate_rows=len(rows)-exact,securities=len({r.get('SECUCODE') for r in rows}),first_report_date=min(dates),last_report_date=max(dates),normalized_sha256=sha(out.read_bytes()),column_names=keys,limitations=['Source query DATETIME=2019-01-02 returns events up to future announced dates; not historical daily as-of state','Future announced suspensions retained; never use before start or known announcement time','Repeated event windows and expected resume dates retained; expected resume is not observed resume','Coverage is vendor response only, not exchange-certified complete history','Historical ST designation and exact price-limit rules are not included'])
 atom(BASE/'catalog/suspensions-status.json',state);print(json.dumps(state,ensure_ascii=False),flush=True)
if __name__=='__main__':
 try:main()
 except Exception as e:
  p=BASE/'catalog/suspensions-status.json';s=json.loads(p.read_text()) if p.exists() else {};s.update(status='blocked',error_type=type(e).__name__,error=str(e),updated_at=now());atom(p,s);raise
