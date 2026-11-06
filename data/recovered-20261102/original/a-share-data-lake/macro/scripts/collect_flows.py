import requests,time,json,hashlib,datetime,pathlib,fcntl,csv
ROOT=pathlib.Path(__file__).resolve().parents[1];SHARED=ROOT.parent/'logs';SHARED.mkdir(exist_ok=True);OUT=ROOT/'raw/flows';OUT.mkdir(exist_ok=True)
receipts=[];fails=[];coverage=[];rows=[];s=requests.Session();url='https://datacenter-web.eastmoney.com/api/data/v1/get'
def limit():
 with (SHARED/'eastmoney-rate.lock').open('a+') as f:
  fcntl.flock(f,fcntl.LOCK_EX);p=SHARED/'eastmoney-last-request.txt';last=float(p.read_text()) if p.exists() else 0;time.sleep(max(0,1.1-(time.time()-last)));p.write_text(str(time.time()));fcntl.flock(f,fcntl.LOCK_UN)
def fetch(params,name):
 for attempt in range(3):
  limit()
  try:
   r=s.get(url,params=params,timeout=35)
   if r.status_code in [401,403,429]:raise PermissionError(f'access/rate_restriction_{r.status_code}')
   r.raise_for_status();d=r.json();p=OUT/name;p.write_bytes(r.content);receipts.append({'file':str(p.relative_to(ROOT)),'url':r.url,'sha256':hashlib.sha256(r.content).hexdigest(),'retrieved_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'bytes':len(r.content)});(ROOT/'logs/flow-receipts.json').write_text(json.dumps(receipts,indent=2))
   if not d.get('result'):raise ValueError('no result: '+str(d)[:300])
   return d['result']
  except PermissionError:raise
  except Exception as e:
   if attempt==2:raise
   time.sleep(3*(attempt+1))
try:
 for name,report,sort,flt in [('margin_accounts','RPTA_WEB_MARGIN_DAILYTRADE','STATISTICS_DATE',"(STATISTICS_DATE>='2019-01-01')"),('northbound_total','RPT_MUTUAL_DEAL_HISTORY','TRADE_DATE',"(MUTUAL_TYPE=\"005\")(TRADE_DATE>='2019-01-01')"),('shanghai_connect','RPT_MUTUAL_DEAL_HISTORY','TRADE_DATE',"(MUTUAL_TYPE=\"001\")(TRADE_DATE>='2019-01-01')"),('shenzhen_connect','RPT_MUTUAL_DEAL_HISTORY','TRADE_DATE',"(MUTUAL_TYPE=\"003\")(TRADE_DATE>='2019-01-01')")]:
  try:
   params={'reportName':report,'columns':'ALL','pageNumber':1,'pageSize':500,'sortColumns':sort,'sortTypes':'-1','source':'WEB','client':'WEB','filter':flt};allrows=[];d=fetch(params,name+'-1.json');pages=int(d['pages']);expected=d.get('count');allrows+=d['data'];print(name,pages,expected,flush=True)
   for pg in range(2,pages+1):params['pageNumber']=pg;d=fetch(params,f'{name}-{pg}.json');allrows+=d['data']
   keys=sorted(set().union(*(x.keys() for x in allrows))) if allrows else []
   with (ROOT/'normalized'/f'{name}.csv').open('w') as f:w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(allrows)
   coverage.append({'family':name,'rows':len(allrows),'expected_count':expected,'pages':pages,'state':'complete_api_response' if expected==len(allrows) else 'count_mismatch','date_column':sort,'min_date':min(x[sort] for x in allrows),'max_date':max(x[sort] for x in allrows),'source':'Eastmoney public datacenter','units':'raw_vendor_column_semantics; see source metadata','pit_vintage':False})
  except PermissionError as e:fails.append({'family':name,'error':str(e)});break
  except Exception as e:fails.append({'family':name,'error':str(e)})
  (ROOT/'logs/flow-coverage.json').write_text(json.dumps(coverage,indent=2))
finally:(ROOT/'logs/flow-failures.json').write_text(json.dumps(fails,indent=2));print('DONE',coverage,fails,flush=True)
