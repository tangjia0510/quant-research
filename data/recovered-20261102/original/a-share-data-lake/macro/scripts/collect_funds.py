import requests,time,json,hashlib,datetime,pathlib,re,csv,shutil,fcntl
from html.parser import HTMLParser
import sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[2]/"catalog"))
from host_gate import host_gate
ROOT=pathlib.Path(__file__).resolve().parents[1];OUT=ROOT/'raw/funds';OUT.mkdir(exist_ok=True);NOR=ROOT/'normalized/funds';NOR.mkdir(exist_ok=True);S=requests.Session();S.headers.update({'User-Agent':'Mozilla/5.0','Referer':'https://fund.eastmoney.com/'})
class P(HTMLParser):
 def __init__(self):super().__init__();self.rows=[];self.r=[];self.c=None
 def handle_starttag(self,t,a):
  if t=='tr':self.r=[]
  if t in ('td','th'):self.c=[]
 def handle_data(self,d):
  if self.c is not None:self.c.append(d)
 def handle_endtag(self,t):
  if t in ('td','th') and self.c is not None:self.r.append(''.join(self.c).strip());self.c=None
  if t=='tr' and len(self.r)==14 and re.fullmatch(r'\d{6}',self.r[3]):self.rows.append(self.r)
p=P();p.feed((ROOT/'raw/etf-master-page.html').read_bytes().decode('gb18030'));univ=[{'code':r[3],'name':r[4].replace('行情吧档案',''),'type':r[5]} for r in p.rows];univ=sorted({x['code']:x for x in univ}.values(),key=lambda x:x['code'])
(ROOT/'normalized/fund_current_universe.json').write_text(json.dumps({'as_of':'2026-10-30','source':'https://fund.eastmoney.com/cnjy_dwjz.html','survivorship_warning':'current exchange-traded fund list; delisted not guaranteed','items':univ},ensure_ascii=False,indent=2))
extra=json.loads((ROOT/'logs/fund-universe-comparison.json').read_text()).get('official_missing_from_vendor',[])
univ+=extra
priority=['510300','510500','512100','588000','159915','159919','159922','159845','588080']
univ=sorted(univ,key=lambda x:(0,priority.index(x['code'])) if x['code'] in priority else (1,x['code']))
(ROOT/'normalized/fund_combined_current_universe.json').write_text(json.dumps({'items':univ,'vendor_pool_count':1700,'official_additional_count':len(extra),'note':'Current pool union; includes ETF/LOF/other exchange funds, not historical delisted universe. Endpoint availability varies by instrument.'},ensure_ascii=False,indent=2))
recp=ROOT/'logs/fund-receipts.jsonl';statep=ROOT/'logs/fund-progress.json';done={};fails=json.loads((ROOT/'logs/fund-failures.json').read_text()) if (ROOT/'logs/fund-failures.json').exists() else []
if recp.exists():
 for l in recp.read_text().splitlines():
  d=json.loads(l);done[d['code']]=d
D=json.JSONDecoder()
def extract(text,key):
 m=re.search(r'\bvar\s+'+re.escape(key)+r'\s*=\s*',text)
 if not m:return None
 try:return D.raw_decode(text[m.end():])[0]
 except ValueError:return None
for idx,item in enumerate(univ):
 code=item['code'];out=OUT/(code+'.js.txt')
 if any(x['code']==code for x in fails):continue
 if code in done and out.exists() and hashlib.sha256(out.read_bytes()).hexdigest()==done[code]['sha256']:continue
 if shutil.disk_usage(ROOT).free<15*1024**3:
  statep.write_text(json.dumps({'state':'partial_terminal_diskfloor','universe':len(univ),'downloaded':len(done),'failed':len(fails)},indent=2));print('STOP diskfloor',flush=True);break
 url=f'https://fund.eastmoney.com/pingzhongdata/{code}.js';blocked=False
 for attempt in range(3):
  try:
   with host_gate('eastmoney'):
    r=S.get(url,timeout=35);body=r.content
   if r.status_code in [401,403,429]:blocked=True;raise PermissionError(f'access/rate_restriction_{r.status_code}')
   r.raise_for_status();raw=r.content;txt=r.text
   if extract(txt,'fS_code')!=code:raise ValueError('code identity mismatch/missing')
   nav=extract(txt,'Data_netWorthTrend');ac=extract(txt,'Data_ACWorthTrend')
   money_income=extract(txt,'Data_millionCopiesIncome');money_yield=extract(txt,'Data_sevenDaysYearIncome');kind='unit_nav'
   if not isinstance(nav,list):
    if isinstance(money_income,list) or isinstance(money_yield,list):nav=[];kind='money_fund_income'
    else:raise ValueError('Neither NAV nor money income arrays')
   out.write_bytes(raw);rows=[]
   for x in nav:
    day=datetime.datetime.fromtimestamp(x['x']/1000,datetime.timezone(datetime.timedelta(hours=8))).date().isoformat()
    if '2019-01-01'<=day<='2026-10-30':rows.append({'date':day,'unit_nav':x.get('y'),'daily_growth_percent':x.get('equityReturn'),'distribution_note':x.get('unitMoney','')})
   with (NOR/(code+'-nav.csv')).open('w') as f:w=csv.DictWriter(f,fieldnames=['date','unit_nav','daily_growth_percent','distribution_note']);w.writeheader();w.writerows(rows)
   money_rows={}
   for arr,field in [(money_income,'income_per_10000_units_as_published'),(money_yield,'seven_day_annualized_yield_percent')]:
    for x in arr or []:
     day=datetime.datetime.fromtimestamp(x[0]/1000,datetime.timezone(datetime.timedelta(hours=8))).date().isoformat()
     if '2019-01-01'<=day<='2026-10-30':money_rows.setdefault(day,{'date':day})[field]=x[1]
   if money_rows:
    with (NOR/(code+'-money-income.csv')).open('w') as f:w=csv.DictWriter(f,fieldnames=['date','income_per_10000_units_as_published','seven_day_annualized_yield_percent']);w.writeheader();w.writerows(money_rows[k] for k in sorted(money_rows))
   supplemental={k:extract(txt,k) for k in ['Data_ACWorthTrend','Data_fundSharesPositions','Data_fluctuationScale','Data_holderStructure','Data_assetAllocation','Data_buySedemption','stockCodesNew','Data_millionCopiesIncome','Data_sevenDaysYearIncome','Data_assetAllocationCurrency']};(NOR/(code+'-supplement.json')).write_text(json.dumps(supplemental,ensure_ascii=False))
   rec={'code':code,'url':url,'file':str(out.relative_to(ROOT)),'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'retrieved_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'nav_rows_2019_onward':len(rows),'nav_min_date':min((x['date'] for x in rows),default=None),'nav_max_date':max((x['date'] for x in rows),default=None),'state':'downloaded','data_kind':kind,'money_income_rows':len(money_rows),'money_income_min_date':min(money_rows,default=None),'money_income_max_date':max(money_rows,default=None)}
   with recp.open('a') as f:f.write(json.dumps(rec,ensure_ascii=False)+'\n')
   done[code]=rec;print(idx+1,len(univ),code,len(rows),flush=True);break
  except Exception as e:
   if attempt==2 or blocked or (isinstance(e,requests.HTTPError) and getattr(e.response,'status_code',None)==404) or (isinstance(e,ValueError) and str(e) in ['code identity mismatch/missing','NAV absent/nonarray','Neither NAV nor money income arrays']):fails.append({'code':code,'url':url,'error':str(e)});print('FAIL',code,str(e),flush=True);break
   time.sleep(3*(attempt+1))
 statep.write_text(json.dumps({'state':'running','universe':len(univ),'downloaded':len(done),'failed':len(fails),'last_code':code,'nav_rows':sum(x['nav_rows_2019_onward'] for x in done.values()),'money_income_rows':sum(x.get('money_income_rows',0) for x in done.values()),'updated_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()},indent=2));(ROOT/'logs/fund-failures.json').write_text(json.dumps(fails,indent=2))
 if blocked:
  d=json.loads(statep.read_text());d['state']='partial_terminal_access_restriction';statep.write_text(json.dumps(d,indent=2));print('STOP accessrestriction',flush=True);break
else:
 d=json.loads(statep.read_text());d['state']='first_pass_complete';statep.write_text(json.dumps(d,indent=2))
print('DONE',len(done),len(fails),flush=True)
