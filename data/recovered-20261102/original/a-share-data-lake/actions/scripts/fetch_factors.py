# PUBLIC SANITIZED COPY (2026-11-06): machine paths generalized; see provenance/publication_transformations.json.
"""Auditable public Sina factor acquisition. Parses JSON; never evaluates response JS."""
import argparse,csv,datetime,fcntl,hashlib,json,math,os,re,shutil,time,urllib.request,urllib.error
from pathlib import Path
BASE=Path(__file__).resolve().parents[1]; LAKE=BASE.parent
RAW=BASE/'raw/sina_factors'; NORM=BASE/'normalized/factors'; STATUS=BASE/'catalog/factor-status.json'; RECEIPTS=BASE/'logs/factor-receipts.jsonl'
def now(): return datetime.datetime.now(datetime.timezone.utc).isoformat()
def sha(b): return hashlib.sha256(b).hexdigest()
def atomic(path,obj):
 t=path.with_suffix(path.suffix+'.tmp');t.write_text(json.dumps(obj,ensure_ascii=False,indent=2));os.replace(t,path)
def receipt(obj):
 with RECEIPTS.open('a') as f:f.write(json.dumps({'at':now(),**obj},ensure_ascii=False)+'\n');f.flush();os.fsync(f.fileno())
def rate():
 # All Sina subdomains share one advisory lock. See catalog/rate-contract.json.
 lock=LAKE/'logs/sina-rate.lock'; stamp=LAKE/'logs/sina-last-request.txt'
 with lock.open('a') as f:
  fcntl.flock(f,fcntl.LOCK_EX)
  try:last=float(stamp.read_text())
  except (FileNotFoundError,ValueError):last=0
  time.sleep(max(0,1.05-(time.time()-last)));stamp.write_text(str(time.time()))
def parse(b,code):
 text=b.decode('utf-8-sig');i=text.find('{')
 if i<0:raise ValueError('No factor JSON object')
 data=json.JSONDecoder().raw_decode(text[i:])[0];rows=data.get('data')
 if not isinstance(rows,list) or not rows:raise ValueError('No factor event rows')
 out=[];seen=set()
 for r in rows:
  day=r.get('d');v=r.get('f');datetime.date.fromisoformat(day);num=float(v)
  if day in seen or not math.isfinite(num) or num<=0:raise ValueError('Duplicate/invalid factor')
  seen.add(day);out.append({'instrument':code,'effective_date':day,'factor':str(v),'source':'sina_hfq','retrieved_at':now()})
 if data.get('total') is not None and int(data['total'])!=len(rows):raise ValueError('Declared count mismatch')
 return sorted(out,key=lambda r:r['effective_date'])
def write_rows(code,rows):
 with (NORM/(code.replace('.','')+'.csv')).open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--universe',required=True);args=ap.parse_args();input=Path(args.universe);payload=input.read_bytes()
 universe=list(csv.DictReader(payload.decode('utf-8-sig').splitlines()));atomic(BASE/'catalog/universe-input.json',{'source_path':str(input),'sha256':sha(payload),'count':len(universe),'captured_at':now()});(BASE/'catalog/universe-input.csv').write_bytes(payload)
 state=json.loads(STATUS.read_text()) if STATUS.exists() else {'schema_version':1,'items':{},'started_at':now()};consecutive=0;stopped=None
 prior_targets=set(state.get('target_instruments',state['items']))
 state['target_instruments']=sorted(prior_targets | {r['instrument'] for r in universe})
 state['batch_target_count']=len(universe);state['status']='running';state['stop_reason']=None
 old=Path('fin_data/legacy-inputs/mixed-source');oldreceipts={}
 for ln in (old/'receipts.jsonl').read_text().splitlines():
  r=json.loads(ln)
  if 'sha256' in r:oldreceipts[r['file']]=r
 for n,item in enumerate(universe,1):
  code=item['instrument'];
  if not re.fullmatch(r'(sh|sz|bj)\.\d{6}',code):raise ValueError('Unsafe instrument identity')
  symbol=code.replace('.','');url=f'https://finance.sina.com.cn/realstock/company/{symbol}/hfq.js';dest=RAW/(symbol+'.js')
  prior=state['items'].get(code)
  if prior and prior['status'] in ('complete','unavailable'):
   if prior['status']=='unavailable':continue
   if dest.exists() and sha(dest.read_bytes())==prior['raw_sha256']:continue
  if shutil.disk_usage(BASE).free<15*1024**3:stopped='disk_free_floor';break
  cache=old/(symbol+'-factor.js');r=oldreceipts.get(cache.name);b=None;origin='network'
  if cache.exists() and r and sha(cache.read_bytes())==r['sha256']:
   b=cache.read_bytes();origin='verified_prior_30_stock_cache';receipt({'instrument':code,'url':url,'status':'cache_reused','prior_receipt':r,'sha256':sha(b)})
  if b is None:
   for attempt in range(1,4):
    try:
     rate();req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'})
     with urllib.request.urlopen(req,timeout=20) as resp:b=resp.read(2*1024*1024);http=resp.status
     if not b:raise ValueError('Empty response')
     receipt({'instrument':code,'url':url,'http_status':http,'attempt':attempt,'bytes':len(b),'sha256':sha(b)});break
    except Exception as e:
     err={'instrument':code,'url':url,'attempt':attempt,'error_type':type(e).__name__,'error':str(e)};receipt(err)
     if isinstance(e,urllib.error.HTTPError) and e.code in (401,403,429,567):stopped='access_or_rate_limit_'+str(e.code);break
     if isinstance(e,urllib.error.HTTPError) and e.code in (404,410):break
     if attempt<3:time.sleep(2**attempt)
   if stopped:break
  try:
   if b is None:raise ValueError('Acquisition exhausted')
   dest.write_bytes(b);rows=parse(b,code);write_rows(code,rows);state['items'][code]={'status':'complete','events':len(rows),'first_event':rows[0]['effective_date'],'last_event':rows[-1]['effective_date'],'raw_sha256':sha(b),'normalized_sha256':sha((NORM/(symbol+'.csv')).read_bytes()),'source_url':url,'origin':origin,'updated_at':now()};consecutive=0
  except Exception as e:
   state['items'][code]={'status':'unavailable','reason':str(e),'source_url':url,'raw_sha256':sha(b) if b else None,'updated_at':now()};consecutive+=1
  state['updated_at']=now();state['target_count']=len(state['target_instruments']);atomic(STATUS,state)
  if n%25==0:print(json.dumps({'position':n,'target':len(universe),'completed':sum(v['status']=='complete' for v in state['items'].values()),'unavailable':sum(v['status']=='unavailable' for v in state['items'].values())}),flush=True)
  if consecutive>=8:stopped='eight_consecutive_unavailable_circuit_break';break
 state['updated_at']=now();state['stop_reason']=stopped or 'pass_finished';state['status']='blocked' if stopped else 'complete';state['target_count']=len(state['target_instruments']);atomic(STATUS,state);print(json.dumps({'stop_reason':state['stop_reason'],'attempted':len(state['items']),'target':len(universe)}),flush=True)
if __name__=='__main__':main()
