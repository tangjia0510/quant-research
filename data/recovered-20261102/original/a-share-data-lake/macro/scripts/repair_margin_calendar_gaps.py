import requests,pathlib,json,datetime,hashlib,sys,time
import pandas as pd
R=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(R.parent/'catalog'));from host_gate import host_gate
O=R/'raw/margin_calendar_gaps';N=R/'normalized/margin_calendar_gaps';O.mkdir(exist_ok=True);N.mkdir(exist_ok=True);reports=[];receipts=[]
for day in ['2019-12-31','2020-06-30','2020-12-31','2021-06-30']:
 rows=[];pg=1;pages=1;expected=None;error=None
 try:
  while pg<=pages:
   q={'reportName':'RPTA_WEB_RZRQ_GGMX','columns':'ALL','pageNumber':pg,'pageSize':500,'sortColumns':'DATE,SCODE','sortTypes':'-1,1','source':'WEB','client':'WEB','filter':f"(DATE='{day}')"}
   with host_gate('eastmoney'):r=requests.get('https://datacenter-web.eastmoney.com/api/data/v1/get',params=q,timeout=45)
   p=O/f'{day}-{pg:03}.json';p.write_bytes(r.content);receipts.append({'file':str(p.relative_to(R)),'source_url':r.url,'retrieved_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'sha256':hashlib.sha256(r.content).hexdigest(),'http_status':r.status_code})
   if r.status_code in [401,403,429]:raise PermissionError('source_restriction_'+str(r.status_code))
   r.raise_for_status();j=r.json();v=j.get('result')
   if not v:
    reports.append({'date':day,'state':'no_records_returned','response_success':j.get('success'),'response_message':j.get('message'),'response_code':j.get('code'),'rows':0});break
   if expected is None:expected=int(v['count']);pages=int(v['pages'])
   if expected!=int(v['count']) or pages!=int(v['pages']):raise ValueError('pagination changed')
   rows.extend(v['data']);pg+=1
  if rows:
   d=pd.DataFrame(rows);dup=int(d.duplicated(['DATE','SCODE']).sum());assert len(d)==expected and not dup and d.DATE.str.startswith(day).all();p=N/(day+'.parquet');d.to_parquet(p,index=False);reports.append({'date':day,'state':'downloaded_count_keys_dates_verified','rows':len(d),'expected':expected,'file':str(p.relative_to(R)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'markets':d.groupby('MARKET').size().to_dict()})
 except Exception as e:
  reports.append({'date':day,'state':'error','error':str(e)})
  if isinstance(e,PermissionError):break
 obj={'generated_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'reports':reports,'receipts':receipts,'integration_rule':'Add only date/security keys absent from frozen base. Never overwrite old month. Official core already covers these dates but vendor extra fields separately verified.'};(R/'logs/margin-calendar-gap-check.json').write_text(json.dumps(obj,ensure_ascii=False,indent=2));print(reports[-1],flush=True)
