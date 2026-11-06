import requests,pathlib,sys,json,datetime,hashlib,csv,math
R=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(R.parent/'catalog'));from host_gate import host_gate
O=R/'raw/fund_nav_repairs';O.mkdir(exist_ok=True);rs=[];receipts=[];total=None;code='501023';start='2021-12-18'
for pg in range(1,101):
 with host_gate('eastmoney'):
  r=requests.get('https://api.fund.eastmoney.com/f10/lsjz',params={'fundCode':code,'pageIndex':pg,'pageSize':20,'startDate':start,'endDate':'2026-10-30'},headers={'Referer':'https://fund.eastmoney.com/'},timeout=35);raw=r.content
 r.raise_for_status();d=r.json();p=O/(code+f'-{pg:03}.json');p.write_bytes(raw);rows=(d.get('Data') or {}).get('LSJZList') or []
 receipts.append({'file':str(p.relative_to(R)),'url':r.url,'retrieved_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'sha256':hashlib.sha256(raw).hexdigest()})
 if total is None:total=int(d['TotalCount'])
 rs+=rows;print(pg,len(rows),total,flush=True)
 if len(rs)>=total or not rows:break
if len(rs)!=total or len({x['FSRQ'] for x in rs})!=len(rs):raise ValueError('API pagination count/uniqueness failed')
out=R/'normalized/funds'/f'{code}-api-nav-gap.csv'
with out.open('w') as f:
 w=csv.DictWriter(f,fieldnames=['date','unit_nav','cumulative_nav','daily_growth_percent','subscribe_status','redeem_status','source']);w.writeheader()
 for x in rs:w.writerow({'date':x['FSRQ'],'unit_nav':x['DWJZ'],'cumulative_nav':x['LJJZ'],'daily_growth_percent':x['JZZZL'],'subscribe_status':x['SGZT'],'redeem_status':x['SHZT'],'source':'Eastmoney f10/lsjz API supplemental gap'})
(R/'logs/fund-nav-repair-501023.json').write_text(json.dumps({'state':'complete_api_gap_response','code':code,'original_static_nav_last_date':'2021-12-17','supplement_rows':len(rs),'min_date':min((x['FSRQ'] for x in rs),default=None),'max_date':max((x['FSRQ'] for x in rs),default=None),'file':str(out.relative_to(R)),'receipts':receipts,'note':'Preserve original static endpoint CSV; supplemental rows are separate, not silent overwrites. Old last date with subscription/redemption suspended does not prove missing current NAV or active fund lifecycle.'},ensure_ascii=False,indent=2))
