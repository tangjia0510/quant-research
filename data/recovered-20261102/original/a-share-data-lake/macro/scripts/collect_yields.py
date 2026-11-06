import requests,time,json,hashlib,csv,re,datetime,pathlib,html
from html.parser import HTMLParser
ROOT=pathlib.Path(__file__).resolve().parents[1]
class P(HTMLParser):
 def __init__(self):super().__init__();self.rows=[];self.row=[];self.cell=None
 def handle_starttag(self,t,a):
  if t=='tr':self.row=[]
  if t in ['td','th']:self.cell=[]
 def handle_data(self,d):
  if self.cell is not None:self.cell.append(d)
 def handle_endtag(self,t):
  if t in ['td','th'] and self.cell is not None:self.row.append(''.join(self.cell).strip());self.cell=None
  if t=='tr' and len(self.row)==10 and re.match(r'\d{4}-\d{2}-\d{2}',self.row[1]):self.rows.append(self.row)
receipts=[];rows=[];fails=[]
for y in range(2019,2027):
 a=f'{y}-01-01';b=min(f'{y}-12-31','2026-10-30');u=f'https://yield.chinabond.com.cn/cbweb-pbc-web/pbc/historyQuery?startDate={a}&endDate={b}&gjqx=0&qxId=ycqx&locale=cn_ZH';p=ROOT/'raw'/f'yield-{y}.html'
 for attempt in range(3):
  try:
   time.sleep(1.1);r=requests.get(u,timeout=45)
   if r.status_code in [401,403,429]:raise RuntimeError(f'access_restriction_{r.status_code}')
   r.raise_for_status();p.write_bytes(r.content);parser=P();parser.feed(r.content.decode('utf-8'))
   if not parser.rows:raise RuntimeError('no parsed data rows')
   rows.extend(parser.rows);receipts.append({'url':r.url,'file':str(p.relative_to(ROOT)),'sha256':hashlib.sha256(r.content).hexdigest(),'retrieved_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'rows':len(parser.rows)});print(y,len(parser.rows),flush=True);break
  except Exception as e:
   if attempt==2 or 'access_restriction' in str(e):fails.append({'year':y,'url':u,'error':str(e)});break
   time.sleep(3*(attempt+1))
 if fails and 'access_restriction' in fails[-1]['error']:break
 (ROOT/'logs/yield-receipts.json').write_text(json.dumps(receipts,ensure_ascii=False,indent=2))
with (ROOT/'normalized/chinabond_yield_curves.csv').open('w') as f:
 w=csv.writer(f);w.writerow(['curve_name','date','3m_percent','6m_percent','1y_percent','3y_percent','5y_percent','7y_percent','10y_percent','30y_percent']);w.writerows(rows)
(ROOT/'logs/yield-failures.json').write_text(json.dumps(fails,indent=2));print('DONE',len(rows),fails,flush=True)
