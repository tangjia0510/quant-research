#!/usr/bin/env python3
# PUBLIC SANITIZED COPY (2026-11-06): machine paths generalized; see provenance/publication_transformations.json.
"""Serial, resumable public daily prices. Never imports external downloaded code."""
import argparse,csv,datetime as dt,gzip,hashlib,io,json,math,os,shutil,sys,time,urllib.parse
from pathlib import Path
import requests
import threading,concurrent.futures as cf
ROOT=Path(__file__).resolve().parents[1]
CACHE=ROOT.parents[1]/'fin_data/legacy-inputs/mixed-source'
WINDOWS=[('2019-01-01','2020-12-31'),('2021-01-01','2022-12-31'),('2023-01-01','2024-12-31'),('2025-01-01','2026-10-30')]
END='2026-10-30'; START='2019-01-01'
HOST='https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get'
LEDGER_LOCK=threading.Lock()
FIELDS=['date','instrument','open','high','low','close','volume_lots','volume_shares','amount_10k_cny','amount_cny']
def now():return dt.datetime.now(dt.timezone.utc).isoformat()
def sha(b):return hashlib.sha256(b).hexdigest()
def atomic(path,obj):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n');os.replace(tmp,path)
def branch_bytes():
 total=0
 for p in ROOT.rglob('*'):
  try:
   if p.is_file():total+=p.stat().st_size
  except FileNotFoundError:pass
 return total
def ledger(obj):
 with LEDGER_LOCK:
  with (ROOT/'receipts/requests.jsonl').open('a') as f:f.write(json.dumps(obj,ensure_ascii=False)+'\n');f.flush()
class Blocked(Exception):pass
class SourceFailure(Exception):pass
class Collector:
 def __init__(self):
  self.local=threading.local();self.rate_lock=threading.Lock();self.stop=threading.Event();self.last=0;self.network_requests=0;self.cache_reused=0
  self.cache_receipts={}
  if (CACHE/'receipts.jsonl').exists():
   for line in (CACHE/'receipts.jsonl').read_text().splitlines():
    r=json.loads(line)
    if r.get('status')==200:self.cache_receipts[r['file']]=r
 def get(self,code,start,end):
  dest=ROOT/'raw'/code/(start[:4]+'.json.gz');meta=dest.with_suffix('.receipt.json')
  if dest.exists() and meta.exists():
   m=json.loads(meta.read_text());b=gzip.decompress(dest.read_bytes())
   if sha(b)!=m['sha256']:raise SourceFailure('Cached raw digest mismatch')
   return b,m
  params={'param':f'{code},day,{start},{end},640,'};url=HOST+'?'+urllib.parse.urlencode(params)
  cname=code+'-'+start[:4]+'.json';c=CACHE/cname;r=self.cache_receipts.get(cname)
  if c.exists() and r and r['url']==url:
   b=c.read_bytes()
   if sha(b)!=r['sha256']:raise SourceFailure('Prior research raw cache digest mismatch')
   m={'source':'Tencent public daily endpoint','url':url,'sha256':sha(b),'bytes':len(b),'acquired_utc':None,'reused_utc':now(),'reused_from':str(c.relative_to(ROOT.parents[1])),'original_receipt':r,'cache_reused':True}
   self.cache_reused+=1
  else:
   b=None
   for attempt in range(1,4):
    if shutil.disk_usage(ROOT).free<15*1024**3:raise Blocked('Global free disk below 15GiB floor')
    with self.rate_lock:
     if self.stop.is_set():raise Blocked('Source worker stopped after another request access restriction')
     time.sleep(max(0,1.05-(time.monotonic()-self.last)));self.last=time.monotonic();self.network_requests+=1
     if self.network_requests%100==0 and branch_bytes()>15*1024**3:
      self.stop.set();raise Blocked('Market branch exceeds15GiB allocation')
    if not hasattr(self.local,'session'):self.local.session=requests.Session()
    started=now()
    try:
     res=self.local.session.get(url,timeout=(10,25));body=res.content
     entry={'requested_utc':started,'url':url,'instrument':code,'window':[start,end],'http_status':res.status_code,'attempt':attempt,'sha256':sha(body),'bytes':len(body)}
     ledger(entry)
     if res.status_code in (401,403,429,567):
      self.stop.set();error=ROOT/'raw'/code/(start[:4]+f'.blocked-{res.status_code}.txt');error.parent.mkdir(exist_ok=True,parents=True);error.write_bytes(body[:65536]);raise Blocked(f'HTTP {res.status_code}; stopped source, no bypass')
     res.raise_for_status()
     if not body:raise ValueError('Empty body')
     d=json.loads(body)
     if d.get('code')!=0:raise ValueError('Source response code '+str(d.get('code')))
     b=body;m={**entry,'source':'Tencent public daily endpoint','acquired_utc':now(),'cache_reused':False};break
    except Blocked:raise
    except Exception as e:
     ledger({'requested_utc':started,'url':url,'attempt':attempt,'error_type':type(e).__name__,'error':str(e)[:350]})
     if attempt==3:raise SourceFailure(f'{type(e).__name__}: {e}')
     time.sleep(3*attempt)
  dest.parent.mkdir(parents=True,exist_ok=True);temp=dest.with_suffix('.tmp');temp.write_bytes(gzip.compress(b,compresslevel=6,mtime=0));os.replace(temp,dest);atomic(meta,m)
  return b,m
 def stock(self,rec,calendar):
  code=rec['instrument'].replace('.','');ipo=rec.get('ipo_date','') or START;out=rec.get('delist_date','') or END;quote_start=rec.get('tencent_requested_start') or START
  volume_multiplier=1 if code.startswith(('sh688','sh689')) else 100
  base={'instrument':rec['instrument'],'source':'Tencent unadjusted daily OHLCV','price_basis':'unadjusted','volume_unit':'shares','source_volume_unit':'shares' if volume_multiplier==1 else 'lots','source_volume_to_shares_multiplier':volume_multiplier,'normalizer_version':'v4-star-volume-units','amount_unit':'CNY (source 10kCNY multiplied by10000)','source_list_record':rec,'requested_start':quote_start,'requested_end':END,'historical_partition':rec.get('historical_partition',''),'started_utc':now(),'windows':[],'limitations':['Free public vendor snapshot; no point-in-time certification or redistribution license granted','Missing dates may be suspension or vendor omission; not filled','ST status, price limits, auction and intraday information absent','Code changes/reuse require reference mapping; current code history may be incomplete']}
  rows={};bad=[];receipts=[];window_failures=[]
  windows=[('2026-03-04',END)] if quote_start=='2026-03-04' else WINDOWS
  for start,end in windows:
   if out<start or ipo>end:continue
   stop=min(end,out);lo=max(start,ipo)
   try:
    b,m=self.get(code,start,stop);d=json.loads(b);part=d.get('data',{}).get(code,{})
    source_rows=part.get('day',[])
    if not isinstance(source_rows,list):raise SourceFailure('Daily key is not list')
    rct=ROOT/'raw'/code/(start[:4]+'.json.receipt.json')
    receipts.append({'sha256':m['sha256'],'url':m['url'],'window':[start,stop],'raw_file':str((ROOT/'raw'/code/(start[:4]+'.json.gz')).relative_to(ROOT)),'returned_rows':len(source_rows)})
    accepted=0
    for row in source_rows:
     if not isinstance(row,list) or len(row)<6:bad.append({'kind':'malformed_row','window':start});continue
     date=str(row[0])
     if not (max(quote_start,ipo)<=date<=min(END,out)):continue
     try:
      op,cl,hi,low,vol=map(float,row[1:6]);amt=float(row[8]) if len(row)>8 and row[8] not in ('',None) else None
      if not all(math.isfinite(v) and v>0 for v in (op,cl,hi,low)):raise ValueError('nonpositive/nonfinite price')
      if not math.isfinite(vol) or vol<0:raise ValueError('invalid volume')
      if low>min(op,cl)+1e-8 or hi<max(op,cl)-1e-8 or low>hi:raise ValueError('OHLC bounds')
      if amt is not None and (not math.isfinite(amt) or amt<0):raise ValueError('invalid amount')
      if amt and vol and not low*.98<=amt*10000/(vol*volume_multiplier)<=hi*1.02:bad.append({'date':date,'kind':'amount_volume_unit_crosscheck','vwap':amt*10000/(vol*volume_multiplier),'low':low,'high':hi})
      val=[date,rec['instrument'],op,hi,low,cl,vol*volume_multiplier/100,vol*volume_multiplier,amt,amt*10000 if amt is not None else None]
      if date in rows and rows[date]!=val:bad.append({'date':date,'kind':'overlap_value_conflict'})
      else:rows[date]=val
      accepted+=1
     except (ValueError,TypeError) as e:bad.append({'date':date,'kind':'invalid_row','error':str(e)})
    base['windows'].append({'start':start,'end':stop,'returned_rows':len(source_rows),'accepted_rows':accepted,'state':'downloaded'})
   except SourceFailure as e:
    window_failures.append({'start':start,'end':stop,'error':str(e)});base['windows'].append({'start':start,'end':stop,'state':'retry_exhausted','error':str(e)})
  output=ROOT/'normalized'/(code+'.csv.gz');buf=io.StringIO();writer=csv.writer(buf);writer.writerow(FIELDS);writer.writerows(rows[k] for k in sorted(rows));payload=buf.getvalue().encode();output.write_bytes(gzip.compress(payload,compresslevel=6,mtime=0))
  lower_known=bool(rec.get('ipo_date'));upper_known=bool(rec.get('delist_date')) or rec.get('status')=='active'
  expected_lo=max(quote_start,ipo) if lower_known else (min(rows) if rows else END)
  expected_hi=min(END,out) if upper_known else (max(rows) if rows else START)
  expected=[d for d in calendar if expected_lo<=d<=expected_hi];missing=sorted(set(expected)-set(rows));unknown=sorted(set(rows)-set(calendar))
  base['missing_session_scope']='listing_lifecycle' if lower_known and upper_known else 'observed_span_where_listing_lifecycle_unknown'
  base['listing_date_known']=lower_known;base['lifecycle_end_known']=upper_known
  base['unclassified_boundary_sessions']=sum(1 for d in calendar if quote_start<=d<=END and not expected_lo<=d<=expected_hi) if not(lower_known and upper_known) else 0
  state='available' if rows and not window_failures and not bad else 'needs_review' if rows else 'unavailable'
  if window_failures:state='partial_retry_exhausted' if rows else 'retry_exhausted'
  base.update(state=state,completed_utc=now(),row_count=len(rows),first_date=min(rows) if rows else None,last_date=max(rows) if rows else None,expected_calendar_days=len(expected),missing_session_count=len(missing),missing_sessions=missing,dates_not_in_calendar=unknown,validation_issues=bad,window_failures=window_failures,raw_receipts=receipts,normalized_file=str(output.relative_to(ROOT)),normalized_csv_sha256=sha(payload),normalized_gzip_sha256=sha(output.read_bytes()),calendar_basis='Observed SSEComposite sessions; not independently exchange-certified')
  atomic(ROOT/'status'/(code+'.json'),base);return base

def master(path):
 with open(path,newline='',encoding='utf-8-sig') as f: data=list(csv.DictReader(f))
 out=[]
 for r in data:
  instrument=r.get('instrument') or r.get('code');ipo=r.get('ipo_date') or r.get('ipoDate') or r.get('list_date') or '';end=r.get('delist_date') or r.get('outDate') or ''
  if not instrument:continue
  instrument=instrument.lower().replace('.','')
  if instrument[:2] not in ('sh','sz','bj') or len(instrument)!=8 or not instrument[2:].isdigit():raise ValueError('Invalid instrument '+instrument)
  if (ipo and ipo>END) or (end and end<START):continue
  out.append({**r,'instrument':instrument,'ipo_date':ipo,'delist_date':end})
 codes=[r['instrument'] for r in out]
 if len(codes)!=len(set(codes)):raise ValueError('Duplicate instrument master needs lifecycle reconciliation')
 return sorted(out,key=lambda r:r['instrument'])
def summary(records,collector,started,state='running'):
 statuses=[]
 for r in records:
  p=ROOT/'status'/(r['instrument']+'.json')
  if p.exists():statuses.append(json.loads(p.read_text()))
 counts={}
 for s in statuses:counts[s['state']]=counts.get(s['state'],0)+1
 obj={'state':state,'started_utc':started,'updated_utc':now(),'universe_count':len(records),'terminal_count':len(statuses),'pending_count':len(records)-len(statuses),'status_counts':counts,'rows':sum(s['row_count'] for s in statuses),'requests_this_process':collector.network_requests,'prior_research_cache_reused_this_process':collector.cache_reused,'free_disk_bytes':shutil.disk_usage(ROOT).free,'scope':[START,END],'historical_sources_sharded':True,'not_all_possible_quant_data':True}
 atomic(ROOT/'progress.json',obj);return obj

def main():
 a=argparse.ArgumentParser();a.add_argument('--master',required=True);args=a.parse_args();p=Path(args.master).resolve();records=master(p);started=now();collector=Collector()
 calendar=(CACHE/'calendar.txt').read_text().splitlines();assert calendar[0]=='2019-01-02' and calendar[-1]==END
 atomic(ROOT/'manifests/job.json',{'started_utc':started,'universe_source_path':str(p),'universe_source_sha256':sha(p.read_bytes()),'count':len(records),'requested_date_range':[START,END],'rate_limit':'max2inflight; shared lock at least1.05seconds between request starts; timeout10/25; max3attempts','source_endpoint':HOST,'rights':'Public access not a grant to redistribute; research use only pending source licensing','cache_source':str(CACHE),'calendar_sha256':sha((CACHE/'calendar.txt').read_bytes())})
 if (ROOT/'blocked.json').exists():
  print('BLOCKED receipt exists: resolve before explicit restart',flush=True);return 2
 pending=[(i,r) for i,r in enumerate(records) if not (ROOT/'status'/(r['instrument']+'.json')).exists()]
 iterator=iter(pending);finished=0;blocked=None
 with cf.ThreadPoolExecutor(max_workers=2) as pool:
  running={}
  def add():
   if collector.stop.is_set() or (ROOT/'PAUSE_REQUESTED').exists():return
   try:i,r=next(iterator)
   except StopIteration:return
   running[pool.submit(collector.stock,r,calendar)]=(i,r)
  add();add()
  while running:
   done,_=cf.wait(running,return_when=cf.FIRST_COMPLETED)
   for future in done:
    idx,rec=running.pop(future)
    try:
     result=future.result();finished+=1
     print(json.dumps({'index':idx+1,'total':len(records),'instrument':rec['instrument'],'state':result['state'],'rows':result['row_count'],'gaps':result['missing_session_count']},ensure_ascii=False),flush=True)
     if finished%10==0:summary(records,collector,started)
    except Blocked as e:
     collector.stop.set()
     if blocked is None:
      blocked={'time':now(),'instrument':rec['instrument'],'reason':str(e),'resume':'Resolve restriction before authorized retry; never use proxy/IP bypass'}
      atomic(ROOT/'blocked.json',blocked)
     print('BLOCKED',str(e),flush=True)
    add()
 if blocked:
  summary(records,collector,started,'blocked');return 2
 if (ROOT/'PAUSE_REQUESTED').exists():
  summary(records,collector,started,'paused_at_stock_boundary');print('PAUSED at stock boundary',flush=True);return 3
 summary(records,collector,started,'completed_bounded_pass');return 0
if __name__=='__main__':sys.exit(main())
