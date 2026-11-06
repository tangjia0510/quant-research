"""Single publication-window refresh; never modifies historical monthly partitions."""
import pathlib,datetime,json,hashlib,gzip,sys,time
import requests,pandas as pd
R=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(R.parent/'catalog'));from host_gate import host_gate
now=datetime.datetime.now(datetime.timezone.utc);stamp=now.strftime('%Y%m%dT%H%M%SZ');D='2026-10-30';O=R/'raw/margin_refresh'/stamp;N=R/'normalized/margin_refresh'/stamp;O.mkdir(parents=True,exist_ok=False);N.mkdir(parents=True);receipts=[]
def fetch(name,url,params,host):
 for attempt in range(3):
  try:
   with host_gate(host):r=requests.get(url,params=params,timeout=45,headers={'User-Agent':'Mozilla/5.0','Referer':'https://www.szse.cn/' if host=='szse' else 'https://data.eastmoney.com/'})
   if r.status_code in [401,403,429]:raise PermissionError(f'source_restriction_{r.status_code}')
   r.raise_for_status();p=O/name;p.write_bytes(r.content);receipts.append({'file':str(p.relative_to(R)),'source_url':r.url,'retrieved_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'sha256':hashlib.sha256(r.content).hexdigest()});return r
  except PermissionError:raise
  except Exception:
   if attempt==2:raise
   time.sleep(3*(attempt+1))
status={'refresh_id':stamp,'target_day':D,'original_month_immutable':'normalized/margin_detail/2026-10.parquet','sources':{},'errors':[]}
try:
 rs=[];expected=None;np=1;pg=1
 while pg<=np:
  q={'reportName':'RPTA_WEB_RZRQ_GGMX','columns':'ALL','pageNumber':pg,'pageSize':500,'sortColumns':'DATE,SCODE','sortTypes':'-1,1','source':'WEB','client':'WEB','filter':f"(DATE='{D}')"}
  j=fetch(f'vendor-{pg:03}.json','https://datacenter-web.eastmoney.com/api/data/v1/get',q,'eastmoney').json();v=j.get('result')
  if not j.get('success') or not v:raise ValueError(str(j)[:200])
  if expected is None:expected=v['count'];np=v['pages']
  if expected!=v['count'] or np!=v['pages']:raise ValueError('pagination snapshot changed')
  rs.extend(v['data']);pg+=1
 df=pd.DataFrame(rs)
 if len(df)!=expected or df.duplicated(['DATE','SCODE']).any() or not df.DATE.str.startswith(D).all():raise ValueError('count/key/date mismatch')
 base=pd.read_parquet(R/status['original_month_immutable']);base=base[base.DATE.str.startswith(D)];new=df[~df.SCODE.isin(base.SCODE)];common=[c for c in base if c in df and c!='SCODE'];left=base.set_index('SCODE')[common];right=df.set_index('SCODE')[common];shared=left.index.intersection(right.index);changed=(left.loc[shared].fillna('__null__').astype(str)!=right.loc[shared].fillna('__null__').astype(str)).any(axis=1)
 outputs=[]
 for name,data in [('day_snapshot',df),('new_security_rows_delta',new)]:
  p=N/(name+'.parquet');data.to_parquet(p,index=False);outputs.append({'file':str(p.relative_to(R)),'rows':len(data),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
 status['sources']['vendor']={'state':'count_key_date_validated','rows':len(df),'baseline_day_rows':len(base),'new_security_rows':len(new),'removed_security_codes':sorted(set(base.SCODE)-set(df.SCODE)),'changed_existing_rows':int(changed.sum()),'changed_existing_codes':changed[changed].index.tolist(),'markets':df.groupby('MARKET').agg(rows=('SCODE','size'),latest_date=('DATE','max')).reset_index().to_dict('records'),'files':outputs}
except Exception as e:status['errors'].append({'source':'vendor','error':str(e)})
try:
 q={'SHOWTYPE':'JSON','CATALOGID':'1837_xxpl','TABKEY':'tab2','txtDate':D};j=fetch('szse-metadata.json','https://www.szse.cn/api/report/ShowReport/data',q,'szse').json();tables=j if isinstance(j,list) else [j];status['sources']['szse']={'metadata':[t.get('metadata',{}) for t in tables]}
 counts=[int(t.get('metadata',{}).get('recordcount',0)) for t in tables]
 if sum(counts)>0:
  q['SHOWTYPE']='xlsx';r=fetch('szse-export.xlsx','https://www.szse.cn/api/report/ShowReport',q,'szse');status['sources']['szse']['export_file']=str((O/'szse-export.xlsx').relative_to(R));status['sources']['szse']['state']='new_export_downloaded_pending_pure_data_parse'
 else:status['sources']['szse']['state']='explicit_target_date_no_records'
except Exception as e:status['errors'].append({'source':'szse','error':str(e)})
status['receipts']=receipts;status['generated_at_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat();p=R/'logs'/f'margin-latest-refresh-{stamp}.json';p.write_text(json.dumps(status,ensure_ascii=False,indent=2));print(json.dumps(status,ensure_ascii=False,indent=2))
