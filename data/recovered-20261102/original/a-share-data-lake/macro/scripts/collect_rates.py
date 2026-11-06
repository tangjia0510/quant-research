import requests,time,json,hashlib,csv,calendar,datetime,pathlib
ROOT=pathlib.Path(__file__).resolve().parents[1]; S=requests.Session(); S.headers['User-Agent']='Mozilla/5.0 (research data archival)'
receipts=json.loads((ROOT/'logs/rates-receipts.json').read_text()) if (ROOT/'logs/rates-receipts.json').exists() else []; failures=[]; blocked=set()
def get(url,name):
 family='lpr' if name.startswith('lpr') else 'shibor'
 if family in blocked:return None
 p=ROOT/'raw'/name
 if p.exists():return json.loads(p.read_text())
 for attempt in range(3):
  time.sleep(1.1)
  try:
   r=S.get(url,timeout=35)
   if r.status_code in (401,403,429):
    blocked.add(family); raise ValueError('access/rate restriction '+str(r.status_code))
   r.raise_for_status(); d=r.json();p.write_bytes(r.content)
   receipts.append({'url':r.url,'file':str(p.relative_to(ROOT)),'retrieved_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'sha256':hashlib.sha256(r.content).hexdigest(),'bytes':len(r.content),'http_status':r.status_code})
   (ROOT/'logs/rates-receipts.json').write_text(json.dumps(receipts,ensure_ascii=False,indent=2));return d
  except Exception as e:
   if attempt==2 or 'restriction' in str(e): failures.append({'url':url,'error':str(e)});return None
   time.sleep(3*(attempt+1))
rows=[]
for y in range(2019,2027):
 for m in range(1,13):
  if (y,m)>(2026,10):continue
  a=f'{y}-{m:02}-01';b=f'{y}-{m:02}-{calendar.monthrange(y,m)[1]:02}'
  if b>'2026-10-30':b='2026-10-30'
  d=get(f'https://www.chinamoney.com.cn/ags/ms/cm-u-bk-shibor/ShiborHis?startDate={a}&endDate={b}',f'shibor-{y}-{m:02}.json')
  records=(d or {}).get('records',[])
  for rec in records:
   date=rec.get('showDateCN') or rec.get('date')
   for tenor in ['ON','O/N','1W','2W','1M','3M','6M','9M','1Y']:
    if tenor in rec:rows.append({'date':date,'tenor':tenor,'value_percent':rec[tenor],'source':'CFETS ShiborHis','retrieved_at_utc':next((x['retrieved_at'] for x in receipts if x['file']==f'raw/shibor-{y}-{m:02}.json'),'unknown')})
  print('shibor',a,len(records),flush=True)
with (ROOT/'normalized/shibor_daily.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=['date','tenor','value_percent','source','retrieved_at_utc']);w.writeheader();w.writerows(rows)
lpr=[]
for y in range(2019,2027):
 a=f'{y}-01-01';b=min(f'{y}-12-31','2026-10-30')
 d=get(f'https://www.chinamoney.com.cn/ags/ms/cm-u-bk-currency/LprHis?lang=CN&strStartDate={a}&strEndDate={b}',f'lpr-{y}.json')
 for rec in (d or {}).get('records',[]):
  for tenor in ['1Y','5Y']:
   if tenor in rec:lpr.append({'date':rec.get('showDateCN'),'tenor':tenor,'value_percent':rec[tenor],'source':'CFETS LprHis'})
 print('lpr',y,len((d or {}).get('records',[])),flush=True)
with (ROOT/'normalized/lpr.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=['date','tenor','value_percent','source']);w.writeheader();w.writerows(lpr)
(ROOT/'logs/rates-failures.json').write_text(json.dumps(failures,indent=2));print('DONE',len(rows),len(lpr),len(failures),flush=True)
