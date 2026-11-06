"""Bounded oldest-year raw prefetch; main collector alone owns monthly outputs/status."""
raise RuntimeError('Not approved for execution: raw ownership race requires separate-cache consumer or shared request lock. Main serial collector remains authoritative.')
import requests,time,json,hashlib,datetime,pathlib,calendar,gzip,shutil,sys
R=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(R.parent/'catalog'));from host_gate import host_gate
O=R/'raw/margin_detail';L=R/'logs';S=requests.Session();dates=set((R.parent/'reference/normalized/trading-calendar-observed-2019-2026.txt').read_text().split());receipts=L/'margin-prefetch-2019-receipts.jsonl';progress=L/'margin-prefetch-2019-progress.json';count=0;errors=[]
cols='DATE,SCODE,MARKET,SECNAME,RZYE,RQYL,RZRQYE,RQYE,RQMCL,RZMRE,RZCHE,RZJME,RQCHL,RQJMG,SPJ,ZDF,SECUCODE'
def get(shard,pg,a,b):
 global count
 p=O/f'{shard}-{pg:04}.json.gz'
 if p.exists():return json.loads(gzip.decompress(p.read_bytes()))
 main=json.loads((L/'margin-detail-progress.json').read_text());month=main.get('month') or main.get('month_just_completed','9999')
 if month[:4]=='2019':raise PermissionError('main_collector_entered_owned_year_stop_before_overlap')
 if shutil.disk_usage(R).free<15*1024**3:raise PermissionError('diskfloor')
 q={'reportName':'RPTA_WEB_RZRQ_GGMX','columns':cols,'pageNumber':pg,'pageSize':500,'sortColumns':'DATE,SCODE','sortTypes':'-1,1','source':'WEB','client':'WEB','filter':f"(DATE>='{a}')(DATE<='{b}')"}
 for attempt in range(3):
  try:
   with host_gate('eastmoney'):r=S.get('https://datacenter-web.eastmoney.com/api/data/v1/get',params=q,timeout=45);body=r.content
   if r.status_code in [401,403,429]:raise PermissionError(f'source_restriction_{r.status_code}')
   r.raise_for_status();j=r.json()
   if not j.get('success') or not j.get('result'):raise ValueError(str(j)[:200])
   tmp=p.with_suffix('.prefetch.tmp');tmp.write_bytes(gzip.compress(body));tmp.replace(p)
   rec={'file':str(p.relative_to(R)),'source_url':r.url,'raw_sha256':hashlib.sha256(body).hexdigest(),'stored_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'raw_bytes':len(body),'retrieved_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'rows':len(j['result']['data']),'pages':j['result']['pages'],'expected_count':j['result']['count'],'collector':'independent_oldest_year_prefetch'}
   with receipts.open('a') as f:f.write(json.dumps(rec)+'\n')
   count+=1;progress.write_text(json.dumps({'state':'running','scope':'2019_only_raw_prefetch','shard':shard,'page':pg,'new_pages':count,'updated_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()},indent=2));return j
  except PermissionError:raise
  except Exception:
   if attempt==2:raise
   time.sleep(3*(attempt+1))
try:
 for m in range(1,13):
  ym=f'2019-{m:02}';end=calendar.monthrange(2019,m)[1]
  for day in [29,22,15,8,1]:
   if day>end:continue
   a=ym+f'-{day:02}';b=ym+f'-{min(day+6,end):02}';shard=ym+f'-d{day:02}'
   if not any(a<=d<=b for d in dates):continue
   j=get(shard,1,a,b)['result'];rows=len(j['data'])
   for pg in range(2,j['pages']+1):rows+=len(get(shard,pg,a,b)['result']['data'])
   if rows!=j['count']:raise ValueError('shard count mismatch '+shard)
   print('PREFETCH',shard,rows,flush=True)
except Exception as e:errors.append(str(e))
progress.write_text(json.dumps({'state':'complete_raw_prefetch' if not errors else 'partial_terminal','scope':'2019_only_raw_prefetch','new_pages':count,'errors':errors,'receipts':str(receipts.relative_to(R)),'updated_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()},indent=2));print('FINISH',count,errors,flush=True)
