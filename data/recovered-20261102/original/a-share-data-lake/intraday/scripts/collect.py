"""Own authored, bounded public Sina recent 1-minute collector. No JavaScript execution."""
from __future__ import annotations
import csv,datetime as dt,gzip,hashlib,io,json,math,os,pathlib,queue,re,shutil,sys,threading,time,traceback
import requests
ROOT=pathlib.Path(__file__).resolve().parents[1]
LAKE=ROOT.parent
sys.path.insert(0,str(LAKE/'catalog'))
from host_gate import host_gate,signal_backpressure
ENDPOINT='https://quotes.sina.cn/cn/api/jsonp_v2.php/=/CN_MarketDataService.getKLineData'
TARGET='2026-10-30'
SCHEMA=1
LOCK=threading.Lock();STOP=threading.Event();STOP_REASON=[]

def now():return dt.datetime.now(dt.timezone.utc).isoformat()
def sha(b):return hashlib.sha256(b).hexdigest()
def js(p,x):
 p.parent.mkdir(parents=True,exist_ok=True);t=p.with_suffix(p.suffix+'.tmp');t.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False));os.replace(t,p)
def parse(b):
 s=b.decode('utf-8-sig');a=s.index('=(')+2;z=s.rindex(');');x=json.loads(s[a:z])
 if x is None:return []
 if not isinstance(x,list):raise ValueError('source_not_list')
 return x

def norm(data,sym):
 out=[];warnings={};seen=set();last=None
 def warn(k):warnings[k]=warnings.get(k,0)+1
 for x in data:
  day=str(x.get('day',''));stamp=dt.datetime.strptime(day,'%Y-%m-%d %H:%M:%S')
  if day in seen:raise ValueError('duplicate_timestamp')
  if last and day<last:raise ValueError('nonascending_timestamp')
  seen.add(day);last=day
  vals={k:float(x[k]) for k in ['open','high','low','close','volume','amount']}
  if not all(math.isfinite(v) for v in vals.values()):raise ValueError('nonfinite')
  if min(vals[k] for k in ['open','high','low','close'])<=0:warn('nonpositive_price')
  if not vals['low']<=min(vals['open'],vals['close'])<=max(vals['open'],vals['close'])<=vals['high']:warn('ohlc_order')
  if vals['volume']<0 or vals['amount']<0:warn('negative_volume_amount')
  if vals['volume']>0:
   vwap=vals['amount']/vals['volume']
   # One yuan rounding allowance for amount; preserve all source values.
   tol=max(.02,1.0/vals['volume'])
   if not vals['low']-tol<=vwap<=vals['high']+tol:warn('amount_volume_price_disagreement')
  elif vals['amount']!=0:warn('amount_without_volume')
  if stamp.second!=0:warn('nonminute_boundary')
  if stamp.strftime('%H:%M:%S')<'09:25:00' or stamp.strftime('%H:%M:%S')>'15:00:00' or '11:30:00'<stamp.strftime('%H:%M:%S')<'13:00:00':warn('outside_regular_session')
  if day[:10]>TARGET:warn('after_frozen_complete_day')
  out.append({'instrument':sym,'timestamp_local':day,'timezone':'Asia/Shanghai','bar_minutes':1,'open':vals['open'],'high':vals['high'],'low':vals['low'],'close':vals['close'],'volume_shares':vals['volume'],'amount_cny':vals['amount']})
 return out,warnings

def store_raw(sym,b,receipt,attempt):
 p=ROOT/'raw'/f'{sym}.attempt-{attempt}.jsonp.gz';z=gzip.compress(b,mtime=0);p.write_bytes(z)
 receipt.update(raw_file=str(p.relative_to(ROOT)),raw_sha256=sha(b),stored_sha256=sha(z),raw_bytes=len(b),stored_bytes=len(z))
 js(p.with_suffix('.receipt.json'),receipt);return receipt

def collect(row):
 sym=row['instrument'].replace('.','');sp=ROOT/'catalog/status'/f'{sym}.json'
 if sp.exists():
  try:
   old=json.loads(sp.read_text());np=ROOT/old.get('normalized_file','missing')
   if old.get('terminal') and ((old.get('status') in ['unavailable','retry_exhausted'] or old.get('reason')=='normalization_rejected') or (np.is_file() and sha(np.read_bytes())==old.get('normalized_sha256'))):return old
  except Exception:pass
 if STOP.is_set():return None
 if shutil.disk_usage(ROOT).free<15*1024**3:
  STOP_REASON.append('global_disk_free_below_15GiB');STOP.set();return None
 params={'symbol':sym,'scale':'1','ma':'no','datalen':'1970'}
 data=None;receipt=None;last_err=None
 # Already verified probes are copied with their original retrieval time, not re-requested.
 probe=ROOT/'probes'/f'{sym}-1m.jsonp';pr=probe.with_suffix('.receipt.json')
 if probe.exists() and pr.exists():
  old=json.loads(pr.read_text());b=probe.read_bytes()
  if old.get('http_status')==200 and sha(b)==old['sha256']:
   data=parse(b);receipt=store_raw(sym,b,{'source_url':old['url'],'retrieved_at_utc':old['retrieved_at_utc'],'http_status':200,'cache_from_probe':True},0)
 if data is None:
  for attempt in range(1,4):
   if STOP.is_set():return None
   try:
    with host_gate('sina',2,1.05):
     r=requests.get(ENDPOINT,params=params,timeout=(10,35))
    receipt=store_raw(sym,r.content,{'source_url':r.url,'retrieved_at_utc':now(),'http_status':r.status_code,'attempt':attempt},attempt)
    if r.status_code in [401,403,567]:
     STOP_REASON.append(f'http_access_stop_{r.status_code}_{sym}');STOP.set();return None
    if r.status_code==429:
     cooldown=min(900,max(60,int(r.headers.get('Retry-After','300'))));signal_backpressure('sina',cooldown)
     last_err='http_429';time.sleep(cooldown);continue
    r.raise_for_status();data=parse(r.content);break
   except Exception as e:
    last_err=f'{type(e).__name__}: {str(e)[:150]}'
    with LOCK:
     with (ROOT/'logs/errors.jsonl').open('a') as f:f.write(json.dumps({'symbol':sym,'attempt':attempt,'at':now(),'error':last_err})+'\n')
    if attempt<3:time.sleep(3*2**attempt)
  if data is None:
   status={'schema_version':SCHEMA,'instrument':sym,'terminal':True,'status':'retry_exhausted','error':last_err,'retrieved_at_utc':now(),'receipt':receipt}
   js(sp,status);return status
 status={'schema_version':SCHEMA,'instrument':sym,'terminal':True,'source':'Sina public getKLineData','adjustment':'unadjusted per SDK documented empty-adjust route; not qfq/hfq','timezone':'Asia/Shanghai','bar_minutes':1,'requested_max_bars':1970,'target_complete_day':TARGET,'retrieved_at_utc':receipt['retrieved_at_utc'],'receipt':receipt,'lifecycle_status':row.get('status'),'ipo_date':row.get('ipo_date'),'delist_date':row.get('delist_date'),'board':row.get('board')}
 if not data:
  status.update(status='unavailable',rows=0,reason='source_empty_list_or_null');js(sp,status);return status
 try:out,warnings=norm(data,sym)
 except Exception as e:
  status.update(status='needs_review',rows=0,reason='normalization_rejected',error=str(e));js(sp,status);return status
 if len(out)>1970:warnings['source_exceeded_requested_window']=len(out)-1970
 s=io.StringIO();w=csv.DictWriter(s,fieldnames=list(out[0]));w.writeheader();w.writerows(out)
 b=s.getvalue().encode();z=gzip.compress(b,mtime=0);p=ROOT/'normalized'/f'{sym}.csv.gz';p.write_bytes(z)
 days={x['timestamp_local'][:10] for x in out};last_day=out[-1]['timestamp_local'][:10]
 status.update(status='needs_review' if warnings else 'available',rows=len(out),first_timestamp=out[0]['timestamp_local'],last_timestamp=out[-1]['timestamp_local'],observed_days=len(days),latest_day=last_day,target_day_reached=last_day==TARGET,warnings=warnings,normalized_file=str(p.relative_to(ROOT)),normalized_sha256=sha(z),normalized_bytes=len(z),volume_unit='shares',volume_unit_basis='amount/volume validation and independent daily-volume magnitude checks; no multiplier copied from daily APIs',amount_unit='CNY',raw_sha256=receipt['raw_sha256'])
 js(sp,status);return status

def main():
 for d in ['raw','normalized','catalog/status','logs']: (ROOT/d).mkdir(parents=True,exist_ok=True)
 uni=ROOT/'catalog/universe.csv'
 if not uni.exists():shutil.copyfile(LAKE/'reference/normalized/price-universe.csv',uni)
 rows=list(csv.DictReader(uni.open()));unique={r['instrument']:r for r in rows}
 if len(unique)!=len(rows):raise ValueError('duplicate_universe')
 js(ROOT/'catalog/run-contract.json',{'schema_version':SCHEMA,'created_or_resumed_at_utc':now(),'universe_count':len(rows),'universe_sha256':sha(uni.read_bytes()),'endpoint':ENDPOINT,'target_complete_day':TARGET,'request_parameters':{'scale':1,'datalen':1970,'ma':'no'},'scope':'provider-returned recent 1-minute window only; not full intraday history, tick or order book','limits':{'max_inflight':2,'minimum_request_start_seconds':1.05,'max_attempts_per_security':3,'branch_budget_bytes':3*1024**3,'global_min_free_bytes':15*1024**3}})
 q=queue.Queue()
 for row in rows:q.put(row)
 totals={};done=[0]
 def progress():
  counts={};n=0;latest=0
  for v in totals.values():counts[v['status']]=counts.get(v['status'],0)+1;n+=v.get('rows',0);latest+=int(v.get('target_day_reached',False))
  js(ROOT/'catalog/progress.json',{'schema_version':1,'generated_at_utc':now(),'state':'blocked' if STOP.is_set() else ('complete_first_pass' if len(totals)==len(rows) else 'running'),'expected_instruments':len(rows),'attempted_terminal':len(totals),'pending':len(rows)-len(totals),'counts':counts,'normalized_rows':n,'observed_target_day_instruments':latest,'target_complete_day':TARGET,'stop_reasons':STOP_REASON,'scope':'recent 1970-bar 1-minute API window, not 2019 intraday history'})
 def worker():
  while not STOP.is_set():
   try:row=q.get_nowait()
   except queue.Empty:return
   try:v=collect(row)
   except Exception as e:
    with LOCK:
     STOP_REASON.append(f'unhandled_{row["instrument"]}_{type(e).__name__}_{e}');STOP.set();progress()
    return
   with LOCK:
    if v:totals[row['instrument']]=v
    done[0]+=1
    if done[0]%10==0:progress();print(now(),len(totals),'/',len(rows),flush=True)
    if done[0]%100==0:
     size=sum(p.stat().st_size for base in ['raw','normalized'] for p in (ROOT/base).glob('*') if p.is_file())
     if size>3*1024**3:STOP_REASON.append('branch_budget_exceeded');STOP.set();progress()
   q.task_done()
 ts=[threading.Thread(target=worker) for _ in range(2)]
 for t in ts:t.start()
 for t in ts:t.join()
 with LOCK:progress()
 print('DONE',json.dumps(json.loads((ROOT/'catalog/progress.json').read_text())),flush=True)
if __name__=='__main__':main()
