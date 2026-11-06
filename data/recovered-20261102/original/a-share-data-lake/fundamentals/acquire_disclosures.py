#!/usr/bin/env python3
"""Public CNINFO JSON API, report-announcement metadata only. Original PDF links retained, not mass downloaded."""
import os,json,time,gzip,hashlib,datetime,pathlib,shutil,fcntl,math,calendar,traceback
import requests
import pyarrow as pa
import pyarrow.parquet as pq
ROOT=pathlib.Path(__file__).resolve().parent/'disclosures';ROOT.mkdir(exist_ok=True)
LOGS=ROOT.parent.parent/'logs';LOGS.mkdir(exist_ok=True)
URL='https://www.cninfo.com.cn/new/hisAnnouncement/query'
CATEGORIES='category_ndbg_szsh;category_bndbg_szsh;category_yjdbg_szsh;category_sjdbg_szsh'
PERIODS=[(f'{y}-{m:02}-01',min(f'{y}-{m:02}-{calendar.monthrange(y,m)[1]}','2026-11-01')) for y in range(2019,2027) for m in range(1,13) if f'{y}-{m:02}-01'<='2026-11-01']
S=requests.Session();S.headers['User-Agent']='Mozilla/5.0 (compatible; rate-limited local financial research)'
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def sha(b):return hashlib.sha256(b).hexdigest()
def write(p,j):
 p.parent.mkdir(parents=True,exist_ok=True);t=p.with_suffix(p.suffix+'.tmp');t.write_text(json.dumps(j,ensure_ascii=False,indent=2));os.replace(t,p)
def pace():
 with open(LOGS/'cninfo-rate.lock','a+') as f:
  fcntl.flock(f,fcntl.LOCK_EX);p=LOGS/'cninfo-last-request.txt'
  try:last=float(p.read_text())
  except:last=0
  time.sleep(max(0,1.2-(time.time()-last)));p.write_text(str(time.time()))
def fetch(start,end,page):
 dest=ROOT/'raw'/(start+'_'+end)/f'page-{page:04}.json.gz';rec=ROOT/'receipts'/(start+'_'+end)/f'page-{page:04}.json'
 if dest.exists() and rec.exists():
  b=dest.read_bytes();r=json.loads(rec.read_text())
  if sha(b)!=r['stored_sha256']:raise RuntimeError('cache_hash_mismatch')
  return json.loads(gzip.decompress(b)),r
 if shutil.disk_usage(ROOT).free<15*1024**3:raise RuntimeError('disk_floor')
 payload={'pageNum':str(page),'pageSize':'30','column':'szse','tabName':'fulltext','plate':'','stock':'','searchkey':'','secid':'','category':CATEGORIES,'trade':'','seDate':start+'~'+end,'sortName':'','sortType':'','isHLtitle':'false'}
 tries=[]
 for attempt in range(3):
  pace()
  try:
   r=S.post(URL,data=payload,timeout=(10,45));b=r.content;tries.append({'at':now(),'status':r.status_code,'bytes':len(b),'sha256':sha(b)})
   if r.status_code in (401,403):raise PermissionError('access_denied_'+str(r.status_code))
   if r.status_code==429:time.sleep(60*(attempt+1));continue
   r.raise_for_status();j=r.json()
   if 'totalAnnouncement' not in j:raise ValueError('unexpected_api_schema')
   z=gzip.compress(b,mtime=0);dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(z)
   receipt={'url':URL,'method':'POST','query':payload,'acquired_at':now(),'raw_sha256':sha(b),'stored_sha256':sha(z),'raw_bytes':len(b),'stored_bytes':len(z),'path':str(dest.relative_to(ROOT)),'attempts':tries,'license':'public API accessibility; redistribution rights not established'};write(rec,receipt);return j,receipt
  except PermissionError:raise
  except Exception as e:tries.append({'at':now(),'error':str(e)[:600]});time.sleep(3*(attempt+1))
 write(rec.with_suffix('.failed.json'),{'url':URL,'query':payload,'attempts':tries,'status':'retry_exhausted'});raise RuntimeError('retry_exhausted')
def acquire(start,end):
 first,rec=fetch(start,end,1);total=int(first.get('totalAnnouncement')or 0);pages=max(1,math.ceil(total/30));rows=list(first.get('announcements')or[]);source_counts=[total]
 if total>900 and start!=end:
  a=datetime.date.fromisoformat(start);b=datetime.date.fromisoformat(end);mid=a+(b-a)//2
  left=acquire(start,mid.isoformat());right=acquire((mid+datetime.timedelta(days=1)).isoformat(),end)
  return {'status':'success' if left['status']=='success' and right['status']=='success' else 'partial','window_start':start,'window_end':end,'rows':left.get('rows',0)+right.get('rows',0),'source_total_at_parent_probe':total,'children':[left,right],'split_for_pagination':True}
 seen=set(str(x.get('announcementId')) for x in rows);repeated_page=None
 for p in range(2,pages+1):
  j,r=fetch(start,end,p);source_counts.append(int(j.get('totalAnnouncement')or 0));new=j.get('announcements')or[]
  if new and all(str(x.get('announcementId')) in seen for x in new):repeated_page=p;break
  rows.extend(new);seen.update(str(x.get('announcementId')) for x in new)
 ids=[str(x.get('announcementId')) for x in rows];dup=len(ids)-len(set(ids));count_ok=len(rows)==total and dup==0 and len(set(source_counts))==1
 norm=[]
 for x in rows:
  out=dict(x);t=x.get('announcementTime');stamp=datetime.datetime.fromtimestamp(t/1000,datetime.timezone.utc)if isinstance(t,(int,float))else None
  out['_announcement_time_utc']=stamp.isoformat()if stamp else None;out['_announcement_time_shanghai']=stamp.astimezone(datetime.timezone(datetime.timedelta(hours=8))).isoformat()if stamp else None
  out['_pdf_url']='https://static.cninfo.com.cn/'+x['adjunctUrl'].lstrip('/')if x.get('adjunctUrl')else None
  out['_correction_title_flag']=any(k in str(x.get('announcementTitle','')) for k in ['更正','修订','补充','更新'])
  out['_future_at_acquisition']=bool(stamp and stamp>datetime.datetime.fromisoformat(rec['acquired_at']));out['_acquired_at']=rec['acquired_at'];out['_numeric_statement_link_verified']=False
  for k,v in list(out.items()):
   if isinstance(v,(dict,list)):out[k]=json.dumps(v,ensure_ascii=False)
  norm.append(out)
 dest=ROOT/'normalized'/(start+'_'+end+'.parquet');dest.parent.mkdir(parents=True,exist_ok=True)
 if norm:pq.write_table(pa.Table.from_pylist(norm),dest,compression='zstd')
 result={'status':'success'if count_ok else'pagination_mismatch','window_start':start,'window_end':end,'source_total':total,'rows':len(rows),'unique_announcements':len(set(ids)),'duplicate_ids':dup,'repeated_page_detected':repeated_page,'source_totals_observed':sorted(set(source_counts)),'pages':pages,'correction_title_rows':sum(x['_correction_title_flag']for x in norm),'future_timestamp_rows':sum(x['_future_at_acquisition']for x in norm),'parquet_path':str(dest.relative_to(ROOT))if norm else None,'parquet_sha256':sha(dest.read_bytes())if norm else None,'completed_at':now(),'limitations':['Metadata and public PDF pointers only; original PDF contents not comprehensively downloaded.','Correction-title flag is heuristic, not a verified restatement lineage; no automatic matching to numeric vendor snapshots.']}
 write(ROOT/'catalog'/f'{start}_{end}.json',result);return result
def main():
 progress={'started_at':now(),'status':'running','expected_windows':PERIODS,'expected_tasks':len(PERIODS),'tasks':[]}
 for start,end in reversed(PERIODS):
  try:r=acquire(start,end)
  except PermissionError as e:
   r={'status':'access_denied','window_start':start,'window_end':end,'error':str(e)};progress['tasks'].append(r);progress['status']='host_access_denied';write(ROOT/'catalog/progress.json',progress);return
  except Exception as e:r={'status':'failed','window_start':start,'window_end':end,'error':str(e)};traceback.print_exc()
  progress['tasks'].append(r);progress['updated_at']=now();progress['success']=sum(x['status']=='success'for x in progress['tasks']);progress['failed']=len(progress['tasks'])-progress['success'];progress['rows']=sum(x.get('rows',0)for x in progress['tasks']);write(ROOT/'catalog/progress.json',progress);print(start,r['status'],r.get('rows'),flush=True)
 progress['status']='complete_with_gaps'if progress['failed']else'complete';write(ROOT/'catalog/progress.json',progress)
if __name__=='__main__':main()
