# PUBLIC SANITIZED COPY (2026-11-06): machine paths generalized; see provenance/publication_transformations.json.
"""Checkpointed two-worker Sina factor API acquisition with host-wide shared gates."""
import argparse,csv,datetime,hashlib,json,os,re,shutil,sys,threading,time,urllib.request,urllib.error
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
BASE=Path(__file__).resolve().parents[1];LAKE=BASE.parent
sys.path.insert(0,str(BASE/'scripts'));sys.path.insert(0,str(LAKE/'catalog'))
from fetch_factors import parse,write_rows,sha,now,atomic,RAW,NORM,STATUS,RECEIPTS
from host_gate import host_gate,signal_backpressure
stop=threading.Event();receipt_lock=threading.Lock();reason_lock=threading.Lock();stop_reason=None

def halt(reason):
 global stop_reason
 with reason_lock:
  if stop_reason is None:stop_reason=reason
 stop.set()
def receipt(row):
 with receipt_lock:
  with RECEIPTS.open('a') as f:f.write(json.dumps({'at':now(),**row},ensure_ascii=False)+'\n');f.flush();os.fsync(f.fileno())

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--universe',required=True);args=ap.parse_args();src=Path(args.universe);payload=src.read_bytes();universe=list(csv.DictReader(payload.decode('utf-8-sig').splitlines()))
 assert len({x['instrument'] for x in universe})==len(universe)
 assert all(re.fullmatch(r'(sh|sz|bj)\.\d{6}',x['instrument']) for x in universe)
 state=json.loads(STATUS.read_text()) if STATUS.exists() else {'schema_version':1,'items':{},'started_at':now()}
 state.update(status='running',stop_reason=None,target_count=len(universe),target_instruments=[r['instrument'] for r in universe],universe_sha256=sha(payload),max_workers=2,host_max_inflight=2,min_start_interval=1.05,resumed_at=now())
 atomic(BASE/'catalog/universe-input.json',{'source_path':str(src),'sha256':sha(payload),'count':len(universe),'captured_at':now()});(BASE/'catalog/universe-input.csv').write_bytes(payload);atomic(STATUS,state)
 verified_receipts={}
 if RECEIPTS.exists():
  for line in RECEIPTS.read_text().splitlines():
   try:r=json.loads(line)
   except json.JSONDecodeError:continue
   if r.get('instrument') and r.get('sha256'):verified_receipts[r['instrument']]=r['sha256']
 old=Path('fin_data/legacy-inputs/mixed-source');old_receipts={}
 for line in (old/'receipts.jsonl').read_text().splitlines():
  r=json.loads(line)
  if r.get('sha256'):old_receipts[r['file']]=r
 def task(item):
  code=item['instrument'];symbol=code.replace('.','');url=f'https://finance.sina.com.cn/realstock/company/{symbol}/hfq.js';dest=RAW/(symbol+'.js');norm=NORM/(symbol+'.csv');prior=state['items'].get(code)
  if prior and prior['status']=='complete' and dest.exists() and norm.exists() and sha(dest.read_bytes())==prior['raw_sha256'] and sha(norm.read_bytes())==prior['normalized_sha256']:return code,None
  if prior and prior['status']=='unavailable':return code,None
  if stop.is_set():return code,None
  if shutil.disk_usage(BASE).free<15*1024**3:halt('disk_free_floor');return code,None
  b=None;origin='network';cached=old/(symbol+'-factor.js');r=old_receipts.get(cached.name)
  if dest.exists() and verified_receipts.get(code)==sha(dest.read_bytes()):b=dest.read_bytes();origin='verified_checkpoint_payload'
  elif cached.exists() and r and sha(cached.read_bytes())==r['sha256']:b=cached.read_bytes();origin='verified_prior_30_stock_cache';receipt({'instrument':code,'url':url,'status':'cache_reused','prior_receipt':r,'sha256':sha(b)})
  if b is None:
   for attempt in range(1,4):
    if stop.is_set():return code,None
    try:
     with host_gate('sina',max_inflight=2,interval=1.05):
      if stop.is_set():return code,None
      req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'})
      with urllib.request.urlopen(req,timeout=20) as resp:b=resp.read(2*1024*1024);http=resp.status
     if not b:raise ValueError('Empty response')
     receipt({'instrument':code,'url':url,'http_status':http,'attempt':attempt,'bytes':len(b),'sha256':sha(b)});break
    except Exception as e:
     receipt({'instrument':code,'url':url,'attempt':attempt,'error_type':type(e).__name__,'error':str(e)})
     if isinstance(e,urllib.error.HTTPError) and e.code in (401,403,429,567):
      if e.code==429:signal_backpressure('sina',300)
      halt('access_or_rate_limit_'+str(e.code));return code,{'status':'blocked','reason':str(e),'source_url':url,'updated_at':now()}
     if isinstance(e,urllib.error.HTTPError) and e.code in (404,410):break
     if attempt<3:stop.wait(2**attempt)
  try:
   if b is None:raise ValueError('Acquisition exhausted')
   dest.write_bytes(b);rows=parse(b,code);write_rows(code,rows)
   return code,{'status':'complete','events':len(rows),'first_event':rows[0]['effective_date'],'last_event':rows[-1]['effective_date'],'raw_sha256':sha(b),'normalized_sha256':sha(norm.read_bytes()),'source_url':url,'origin':origin,'updated_at':now()}
  except Exception as e:return code,{'status':'unavailable','reason':str(e),'source_url':url,'raw_sha256':sha(b) if b else None,'updated_at':now()}
 pending=[r for r in universe if state['items'].get(r['instrument'],{}).get('status') not in ('complete','unavailable')];print(json.dumps({'targets':len(universe),'pending':len(pending),'workers':2}),flush=True);done=0;consecutive=0
 with ThreadPoolExecutor(max_workers=2) as pool:
  futs=[pool.submit(task,r) for r in pending]
  for fut in as_completed(futs):
   try:code,result=fut.result()
   except Exception as e:halt('unexpected_worker_error_'+type(e).__name__);receipt({'error':str(e),'error_type':type(e).__name__});continue
   if result is None:continue
   state['items'][code]=result;done+=1;consecutive=consecutive+1 if result['status']=='unavailable' else 0
   state['updated_at']=now();atomic(STATUS,state)
   if consecutive>=8:halt('eight_consecutive_unavailable_circuit_break')
   if done%25==0:print(json.dumps({'new_completed':done,'attempted':len(state['items']),'target':len(universe),'complete':sum(v['status']=='complete' for v in state['items'].values()),'unavailable':sum(v['status']=='unavailable' for v in state['items'].values())}),flush=True)
 state.update(status='blocked' if stop_reason else 'complete',stop_reason=stop_reason or 'pass_finished',updated_at=now());atomic(STATUS,state);print(json.dumps({'status':state['status'],'stop_reason':state['stop_reason'],'attempted':len(state['items']),'target':len(universe)}),flush=True)
if __name__=='__main__':main()
