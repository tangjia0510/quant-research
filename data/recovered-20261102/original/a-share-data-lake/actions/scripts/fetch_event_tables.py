"""Bounded public event-report acquisition. No SDK remote code is executed."""
import csv,hashlib,json,sys,time,urllib.request,urllib.parse,urllib.error,shutil
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"catalog"))
from host_gate import host_gate,signal_backpressure
BASE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BASE/'scripts'));from fetch_sharebonus import rate,now,atom,sha
SPECS=[
 ('rights','RPT_IPO_ALLOTMENT','EQUITY_RECORD_DATE,SECURITY_CODE','-1,1','EQUITY_RECORD_DATE',None),
 ('seasoned_offerings','RPT_SEO_DETAIL','ISSUE_DATE,SECURITY_CODE','-1,1','ISSUE_DATE',None),
 ('repurchases','RPTA_WEB_GETHGLIST_NEW','UPD,DIM_DATE,DIM_SCODE','-1,-1,-1','UPDATEDATE',None),
 ('unlock_events','RPT_LIFT_STAGE','FREE_DATE,CURRENT_FREE_SHARES','1,1','FREE_DATE',"(FREE_DATE>='2019-01-01')(FREE_DATE<='2026-10-30')")]
def fetch(name,report,sort,types,fil,page):
 folder=BASE/'raw'/('eastmoney_'+name);folder.mkdir(exist_ok=True);path=folder/f'page-{page:04d}.json';meta=path.with_suffix('.receipt.json')
 p={'reportName':report,'columns':'ALL','sortColumns':sort,'sortTypes':types,'pageSize':'500','pageNumber':str(page),'source':'WEB','client':'WEB'}
 if fil:p['filter']=fil
 url='https://datacenter-web.eastmoney.com/api/data/v1/get?'+urllib.parse.urlencode(p)
 if path.exists() and meta.exists() and sha(path.read_bytes())==json.loads(meta.read_text())['sha256']:return json.loads(path.read_bytes())
 for attempt in range(1,4):
  try:
   with host_gate('eastmoney'):
    with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'}),timeout=25) as r:b=r.read(16*1024*1024);status=r.status
   d=json.loads(b)
   if not d.get('success') or not isinstance(d.get('result',{}).get('data'),list):raise ValueError('Source response '+str(d)[:250])
   path.write_bytes(b);atom(meta,{'url':url,'retrieved_at':now(),'status':status,'attempt':attempt,'sha256':sha(b),'bytes':len(b)});return d
  except Exception as e:
   with (BASE/'logs/events-errors.jsonl').open('a') as f:f.write(json.dumps({'name':name,'page':page,'attempt':attempt,'url':url,'error':str(e),'at':now()})+'\n')
   if isinstance(e,urllib.error.HTTPError) and e.code==429:signal_backpressure('eastmoney',300)
   if isinstance(e,urllib.error.HTTPError) and e.code in (401,403,429,567):raise
   if attempt==3:raise
   time.sleep(2**attempt)
def main():
 for name,report,sort,types,datefield,fil in SPECS:
  cat=BASE/'catalog'/f'{name}-status.json';state={'dataset':name,'report_name':report,'status':'running','started_at':now()};atom(cat,state)
  try:
   first=fetch(name,report,sort,types,fil,1);pages=int(first['result']['pages']);expected=int(first['result']['count']);state.update(target_pages=pages,declared_rows=expected);rows=[]
   for n in range(1,pages+1):
    if shutil.disk_usage(BASE).free<15*1024**3:raise RuntimeError('Disk free floor')
    d=first if n==1 else fetch(name,report,sort,types,fil,n)
    if int(d['result']['count'])!=expected or int(d['result']['pages'])!=pages:raise ValueError('Source count changed during pagination')
    rows.extend(d['result']['data']);state.update(pages_complete=n,rows_downloaded=len(rows),updated_at=now());atom(cat,state)
   if len(rows)!=expected:raise ValueError('Page row count differs from declared total')
   keys=sorted({k for r in rows for k in r});out=BASE/'normalized'/f'{name}-all.csv'
   with out.open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(rows)
   dates=[r[datefield][:10] for r in rows if r.get(datefield)];exact=len({json.dumps(r,sort_keys=True) for r in rows});codes={r.get('SECUCODE') or r.get('SECURITY_CODE') or r.get('DIM_SCODE') for r in rows}
   state.update(status='complete',complete_at=now(),source_rows=len(rows),exact_unique_rows=exact,duplicate_rows=len(rows)-exact,securities=len(codes),date_field=datefield,first_event_date=min(dates) if dates else None,last_event_date=max(dates) if dates else None,columns=keys,normalized_sha256=sha(out.read_bytes()),limitations=['Retrospective vendor event snapshot; not original as-of vintages','Proposal and implementation statuses must be distinguished; latest quoted prices and post-event return fields must NOT be used as historical features','Original vendor numeric units retained without unverified conversion','Announcement dates differ from effective dates; future scheduled records may be present','Coverage is source response; delisted and historic record completeness unproven'])
   atom(cat,state);print(json.dumps({k:v for k,v in state.items() if k not in ['columns','limitations']},ensure_ascii=False),flush=True)
  except Exception as e:
   state.update(status='blocked',error_type=type(e).__name__,error=str(e),updated_at=now());atom(cat,state);print(json.dumps(state),flush=True)
   if isinstance(e,urllib.error.HTTPError) and e.code in (401,403,429,567):break
if __name__=='__main__':main()
