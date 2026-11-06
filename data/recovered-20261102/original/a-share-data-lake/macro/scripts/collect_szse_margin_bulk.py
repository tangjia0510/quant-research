import pathlib,sys,urllib.request,urllib.error,urllib.parse,time,json,hashlib,gzip,datetime,shutil,io
import pandas as pd
import warnings
warnings.filterwarnings("ignore",message="Workbook contains no default style")
R=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(R.parent/'catalog'));from host_gate import host_gate
O=R/'raw/szse_margin_bulk';O.mkdir(exist_ok=True);N=R/'normalized/szse_margin_bulk';N.mkdir(exist_ok=True);recp=R/'logs/szse-margin-bulk-receipts.jsonl';done={};errors=[]
if recp.exists():
 for l in recp.read_text().splitlines():
  x=json.loads(l);done[x['date']]=x
calendar=sorted([x for x in (R.parent/'reference/normalized/trading-calendar-observed-2019-2026.txt').read_text().split() if '2019-01-01'<=x<='2026-10-29'],reverse=True)
try:
 for day in calendar:
  p=O/(day+'.xlsx');out=N/(day+'.csv.gz')
  if day in done and p.exists() and out.exists():continue
  if shutil.disk_usage(R).free<15*1024**3:raise PermissionError('global_disk_floor')
  url='https://www.szse.cn/api/report/ShowReport?'+urllib.parse.urlencode({'SHOWTYPE':'xlsx','CATALOGID':'1837_xxpl','TABKEY':'tab2','txtDate':day})
  try:
   for attempt in range(3):
    try:
     with host_gate('szse',max_inflight=1):
      req=urllib.request.Request(url,headers={'Referer':'https://www.szse.cn/disclosure/margin/margin/index.html'})
      with urllib.request.urlopen(req,timeout=35) as resp:raw=resp.read()
     break
    except urllib.error.HTTPError as e:
     if e.code in [401,403,429]:raise PermissionError(f'access_restriction_{e.code}')
     if e.code==404 or attempt==2:raise
     time.sleep(3*(attempt+1))
    except Exception:
     if attempt==2:raise
     time.sleep(3*(attempt+1))
   if raw[:4]!=b'PK\x03\x04':raise ValueError('Response not XLSX ZIP binary')
   d=pd.read_excel(io.BytesIO(raw),sheet_name=0,dtype=str);d=d[d['证券代码'].str.fullmatch(r'\d{6}',na=False)].copy()
   if d.empty or d['证券代码'].duplicated().any():raise ValueError('Empty/duplicate code in official daily workbook')
   d.insert(0,'date',day);d['exchange']='SZSE';d['date_basis']='official_download_date_parameter';p.write_bytes(raw);d.to_csv(out,index=False,compression='gzip');x={'date':day,'rows':len(d),'raw_file':str(p.relative_to(R)),'normalized_file':str(out.relative_to(R)),'source_url':url,'raw_sha256':hashlib.sha256(raw).hexdigest(),'stored_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'normalized_sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'retrieved_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
   with recp.open('a') as f:f.write(json.dumps(x)+'\n')
   done[day]=x;print(day,len(d),len(done),flush=True)
  except PermissionError:raise
  except Exception as e:errors.append({'date':day,'url':url,'error':str(e)});print('FAIL',day,str(e),flush=True)
  (R/'logs/szse-margin-bulk-progress.json').write_text(json.dumps({'state':'running','completed_dates':len(done),'target_dates':len(calendar),'rows':sum(x['rows'] for x in done.values()),'latest_date':max(done,default=None),'earliest_date':min(done,default=None),'failed_dates':len(errors)},indent=2));(R/'logs/szse-margin-bulk-failures.json').write_text(json.dumps(errors,indent=2))
except PermissionError as e:errors.append({'terminal':str(e)})
finally:
 (R/'logs/szse-margin-bulk-failures.json').write_text(json.dumps(errors,indent=2));(R/'logs/szse-margin-bulk-progress.json').write_text(json.dumps({'state':'complete_first_pass' if len(done)==len(calendar) else 'partial_terminal','completed_dates':len(done),'target_dates':len(calendar),'rows':sum(x['rows'] for x in done.values()),'latest_date':max(done,default=None),'earliest_date':min(done,default=None),'failures':len(errors)},indent=2));print('FINISHED',len(done),len(errors),flush=True)
