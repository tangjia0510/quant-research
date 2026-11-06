import pathlib,sys,requests,json,re,datetime,hashlib,csv,time
R=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(R.parent/'catalog'));from host_gate import host_gate
mapping=json.loads((R/'logs/fund-verified-aliases.json').read_text());O=R/'raw/fund_aliases';O.mkdir(exist_ok=True);N=R/'normalized/fund_aliases';N.mkdir(exist_ok=True);records=[];D=json.JSONDecoder()
def extract(s,k):
 m=re.search(r'\bvar\s+'+k+r'\s*=\s*',s)
 return D.raw_decode(s[m.end():])[0] if m else None
for item in mapping['verified_pairs']:
 code=item['fund_data_code'];url=f'https://fund.eastmoney.com/pingzhongdata/{code}.js'
 with host_gate('eastmoney'):
  r=requests.get(url,headers={'Referer':'https://fund.eastmoney.com/'},timeout=35);raw=r.content
 r.raise_for_status();assert extract(r.text,'fS_code')==code
 p=O/(code+'.js.txt');p.write_bytes(raw);rows={}
 for key,col in [('Data_millionCopiesIncome','income_per_10000_units_as_published'),('Data_sevenDaysYearIncome','seven_day_annualized_yield_percent')]:
  data=extract(r.text,key)
  if not isinstance(data,list):raise ValueError('Expected monetary-fund income array')
  for x in data:
   date=datetime.datetime.fromtimestamp(x[0]/1000,datetime.timezone(datetime.timedelta(hours=8))).date().isoformat()
   if '2019-01-01'<=date<='2026-10-30':rows.setdefault(date,{'date':date,'fund_data_code':code,'exchange_subscription_code':item['exchange_subscription_code']})[col]=x[1]
 out=N/(code+'-money-income.csv');fields=['date','fund_data_code','exchange_subscription_code','income_per_10000_units_as_published','seven_day_annualized_yield_percent']
 with out.open('w') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows[d] for d in sorted(rows))
 records.append({**item,'state':'downloaded_via_officially_verified_alias','source_url':url,'raw_file':str(p.relative_to(R)),'normalized_file':str(out.relative_to(R)),'sha256':hashlib.sha256(raw).hexdigest(),'rows':len(rows),'min_date':min(rows,default=None),'max_date':max(rows,default=None),'retrieved_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'identity_evidence':'logs/fund-verified-aliases.json','mapping_effective_start_date':None,'identity_caveat':'Mapping explicitly proven by2026-03-31announcement; historical effective start not independently established'});(R/'logs/fund-alias-retrieval.json').write_text(json.dumps(records,ensure_ascii=False,indent=2));print(code,len(rows),flush=True)
