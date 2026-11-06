import pathlib,sys,requests,json,re,datetime,hashlib,time,csv,shutil
from html.parser import HTMLParser
R=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(R.parent/'catalog'));from host_gate import host_gate
O=R/'raw/fund_holdings';O.mkdir(exist_ok=True);N=R/'normalized/fund_holdings';N.mkdir(exist_ok=True);log=R/'logs/fund-holdings-coverage.json';done=json.loads(log.read_text()) if log.exists() else [];cached={(x['code'],x['year']):x for x in done};done=[x for x in done if x.get('parser_version')==2];errors=[];D=json.JSONDecoder()
class P(HTMLParser):
 def __init__(self):super().__init__();self.period=None;self.rows=[];self.row=[];self.cell=None;self.head=[];self.inhead=False
 def handle_starttag(self,t,a):
  if t=='table':self.head=[]
  if t=='tr':self.row=[]
  if t in ['td','th']:self.cell=[];self.inhead=t=='th'
 def handle_data(self,d):
  if re.fullmatch(r'\d{4}-\d{2}-\d{2}',d.strip()):self.period=d.strip()
  if self.cell is not None:self.cell.append(d)
 def handle_endtag(self,t):
  if t in ['td','th'] and self.cell is not None:
   val=''.join(self.cell).strip();self.row.append(val)
   if self.inhead:self.head.append(val)
   self.cell=None
  if t=='tr' and len(self.row) in [7,9] and self.row[0].isdigit():self.rows.append({'period':self.period,'cells':self.row[:],'headers':self.head[:]})
def numeric(x):
 try:return float(x.replace(',','').replace('%',''))
 except (ValueError,AttributeError):return None
codes=['510300','510500','512100','588000','159915','159919','159922','159845','588080']
try:
 for code in codes:
  for year in range(2026,2018,-1):
   if any(x['code']==code and x['year']==year and x['state'] in ['parsed_partial_portfolio_response','no_report_rows'] for x in done):continue
   p=O/f'{code}-{year}.txt';url='https://fundf10.eastmoney.com/FundArchivesDatas.aspx';params={'type':'jjcc','code':code,'topline':10000,'year':year,'month':''}
   try:
    if shutil.disk_usage(R).free<15*1024**3:raise PermissionError('disk_floor')
    cache=cached.get((code,year))
    if cache and p.exists() and hashlib.sha256(p.read_bytes()).hexdigest()==cache['sha256']:
     raw=p.read_bytes();response_text=raw.decode('utf-8-sig');response_url=cache['source_url'];retrieved_at=cache['retrieved_at_utc']
    else:
     for attempt in range(3):
      try:
       with host_gate('eastmoney'):
        r=requests.get(url,params=params,headers={'Referer':'https://fundf10.eastmoney.com/'},timeout=35);raw=r.content
       if r.status_code in [401,403,429]:raise PermissionError(f'access_restriction_{r.status_code}')
       r.raise_for_status();break
      except PermissionError:raise
      except Exception:
       if attempt==2:raise
       time.sleep(3*(attempt+1))
     response_text=r.text;response_url=r.url;retrieved_at=datetime.datetime.now(datetime.timezone.utc).isoformat()
    p.write_bytes(raw);m=re.search(r'\bcontent\s*:\s*',response_text)
    if not m:raise ValueError('No content literal')
    html=D.raw_decode(response_text[m.end():])[0];parser=P();parser.feed(html);rows=[]
    for x in parser.rows:
     a=x['cells'];h=x['headers'];period=x['period']
     if not period or not period.startswith(str(year)):raise ValueError('Source returned unexpected report year')
     if len(h)!=len(a) or not any('万股' in z for z in h) or not any('万元' in z for z in h):raise ValueError('Unrecognized source units/header layout')
     wi=next(i for i,z in enumerate(h) if '占净值' in z);si=next(i for i,z in enumerate(h) if '万股' in z);vi=next(i for i,z in enumerate(h) if '万元' in z)
     shares=numeric(a[si]);value=numeric(a[vi]);rows.append({'fund_code':code,'report_period_end':period,'rank':int(a[0]),'security_code':a[1],'security_name':a[2],'weight_nav_percent':numeric(a[wi]),'reported_shares_10k':shares,'reported_market_value_10k_cny':value,'shares':None if shares is None else shares*10000,'market_value_cny':None if value is None else value*10000,'publication_date':None,'scope':'source_returned_holdings_not_certified_full_portfolio','source_file':str(p.relative_to(R))})
    out=N/f'{code}-{year}.csv';fields=['fund_code','report_period_end','rank','security_code','security_name','weight_nav_percent','reported_shares_10k','reported_market_value_10k_cny','shares','market_value_cny','publication_date','scope','source_file']
    with out.open('w') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
    quarters=sorted({x['report_period_end'] for x in rows});rec={'code':code,'year':year,'state':'parsed_partial_portfolio_response' if rows else 'no_report_rows','rows':len(rows),'quarter_rows':{q:sum(x['report_period_end']==q for x in rows) for q in quarters},'raw_file':str(p.relative_to(R)),'file':str(out.relative_to(R)),'source_url':response_url,'retrieved_at_utc':retrieved_at,'parser_version':2,'sha256':hashlib.sha256(raw).hexdigest(),'scope_warning':'topline10000 request does not prove complete portfolio; source often returns top10 only; publication dates unknown'};done.append(rec);log.write_text(json.dumps(done,ensure_ascii=False,indent=2));(R/'logs/fund-holdings-progress.json').write_text(json.dumps({'state':'running','funds_target':9,'fund_years_target':72,'fund_years_completed':len(done),'rows':sum(x['rows'] for x in done),'errors':len(errors),'portfolio_complete':False},indent=2));print(code,year,len(rows),flush=True)
   except PermissionError:raise
   except Exception as e:errors.append({'code':code,'year':year,'error':str(e)});print('FAIL',code,year,str(e),flush=True)
except PermissionError as e:errors.append({'terminal':str(e)})
finally:
 (R/'logs/fund-holdings-failures.json').write_text(json.dumps(errors,indent=2));(R/'logs/fund-holdings-progress.json').write_text(json.dumps({'state':'first_pass_finished' if len(done)==72 else 'partial_terminal','funds_target':9,'fund_years_target':72,'fund_years_completed':len(done),'rows':sum(x['rows'] for x in done),'errors':len(errors),'portfolio_complete':False},indent=2));print('DONE',len(done),len(errors),flush=True)
