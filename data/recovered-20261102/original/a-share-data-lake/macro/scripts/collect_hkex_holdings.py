import requests,time,json,hashlib,datetime,pathlib,re,csv
from html.parser import HTMLParser
R=pathlib.Path(__file__).resolve().parents[1];O=R/'raw/hkex_holdings';O.mkdir(exist_ok=True);receipts=[];coverage=[];errors=[]
class P(HTMLParser):
 def __init__(self):super().__init__();self.inputs={};self.rows=[];self.row=[];self.body=False;self.parts=[]
 def handle_starttag(self,t,a):
  at=dict(a)
  if t=='input' and at.get('name'):self.inputs[at['name']]=at.get('value','')
  if t=='tr':self.row=[]
  if t=='div' and 'mobile-list-body' in at.get('class',''):self.body=True;self.parts=[]
 def handle_data(self,d):
  if self.body:self.parts.append(d)
 def handle_endtag(self,t):
  if t=='div' and self.body:self.row.append(''.join(self.parts).strip());self.body=False
  if t=='tr' and len(self.row)==4:self.rows.append(self.row)
for market in ['sh','sz']:
 s=requests.Session();url='https://www3.hkexnews.hk/sdw/search/mutualmarket.aspx?t='+market
 try:
  time.sleep(1.1);r=s.get(url,timeout=35);r.raise_for_status()
  for date in ['2026/09/30','2026/06/30','2026/03/31','2025/12/31']:
   query_date={'2026/09/30':'2026/10/30','2026/06/30':'2026/07/20','2026/03/31':'2026/04/20','2025/12/31':'2026/01/20'}[date]
   if date!='2026/09/30':
    prev=P();prev.feed(r.text);payload={k:v for k,v in prev.inputs.items() if k.startswith('__')};payload.update({'__EVENTTARGET':'btnSearch','__EVENTARGUMENT':'','txtShareholdingDate':query_date,'sortBy':'stockcode','sortDirection':'asc'})
    time.sleep(1.1);r=s.post(url,data=payload,timeout=35);r.raise_for_status()
   parser=P();parser.feed(r.text);actual=re.search(r'Shareholding Date:\s*(\d{4}/\d{2}/\d{2})',r.text);actual=actual.group(1) if actual else None
   if actual!=date:errors.append({'market':market,'requested_date':date,'actual_date':actual,'error':'date response mismatch'});continue
   p=O/f'{market}-{date.replace("/","-")}.html';p.write_bytes(r.content);rec={'file':str(p.relative_to(R)),'url':r.url,'requested_date':query_date,'expected_quarter_end':date,'actual_date':actual,'retrieved_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'sha256':hashlib.sha256(r.content).hexdigest(),'rows':len(parser.rows)};receipts.append(rec)
   rows=[]
   for code,name,shares,pct in parser.rows:
    underlying=re.search(r'#(\d{6})',name)
    rows.append({'date':date.replace('/','-'),'market':market,'connect_stock_code':code,'a_share_code':underlying.group(1) if underlying else '', 'name':name,'ccass_shares':shares.replace(',',''),'percent_listed_traded_shares':pct.rstrip('%'),'publication_available':'fifth_northbound_trading_day_after_quarter_end_not_quarter_end','source_file':str(p.relative_to(R))})
   with (R/'normalized'/f'hkex_northbound_{market}_{date.replace("/","-")}.csv').open('w') as f:
    if rows:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
   coverage.append({'market':market,'date':date,'rows':len(rows),'state':'downloaded'});print(market,date,len(rows),flush=True)
 except Exception as e:errors.append({'market':market,'error':str(e)});print('FAIL',market,str(e),flush=True)
(R/'logs/hkex-holdings-receipts.json').write_text(json.dumps(receipts,indent=2));(R/'logs/hkex-holdings-coverage.json').write_text(json.dumps({'coverage':coverage,'errors':errors,'limits':['Official search retains only twelve months; no historic whole2019 claim.','Since 2024-08-19 quarterly holdings published fifth northbound trading day after quarter end.','Issuer total share count can lag corporate actions, percentage for reference only.']},indent=2))
