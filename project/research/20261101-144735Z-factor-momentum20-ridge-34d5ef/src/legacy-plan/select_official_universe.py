import json,hashlib
from pathlib import Path
import pandas as pd
p=Path(__file__).parent;q=p/'source-review'
if (p/'selection.json').exists():raise RuntimeError('Do not replace frozen selection')
records=[]
for name,delisted in [('sse-active',False),('sse-delisted',True)]:
 d=json.loads((q/(name+'.bin')).read_bytes())
 assert len(d['result'])==int(d['pageHelp']['total'])
 for r in d['result']:
  code=r.get('A_STOCK_CODE') or r['COMPANY_CODE']
  if not code.startswith('60'):continue
  def date(s):return pd.to_datetime(s).date().isoformat()
  records.append({'code':'sh.'+code,'name':r.get('COMPANY_ABBR',''),'ipoDate':date(r['LIST_DATE']),'outDate':date(r['DELIST_DATE']) if delisted else '', 'source':name})
for name,delisted in [('szse-active',False),('szse-delisted',True)]:
 d=pd.read_csv(q/(name+'.csv'),dtype=str).fillna('')
 for r in d.to_dict('records'):
  code=r['证券代码'] if delisted else r['A股代码']
  if not (code.startswith('00') or code.startswith('30')):continue
  records.append({'code':'sz.'+code,'name':r['证券简称'] if delisted else r['A股简称'],'ipoDate':r['上市日期'] if delisted else r['A股上市日期'],'outDate':r['终止上市日期'] if delisted else '', 'source':name})
d=pd.DataFrame(records)
if d.code.duplicated().any(): raise RuntimeError('Duplicate official active/delisted codes require reconciliation '+str(d[d.code.duplicated(keep=False)].to_dict('records')))
d=d[(d.ipoDate<='2018-12-31') & ((d.outDate=='') | (d.outDate>='2019-01-01'))]
selection=[]
for pat in [r'sh\.60\d{4}',r'sz\.00\d{4}',r'sz\.30\d{4}']:
 part=d[d.code.str.fullmatch(pat)].sort_values('code').head(10)
 assert len(part)==10
 selection.extend(part.to_dict('records'))
amend={'reason':'BaoStock public endpoint failed two logins and DNS diagnostics; change source before prices or any model result', 'original_prereg_sha256':hashlib.sha256((p/'preregistration.json').read_bytes()).hexdigest(),'universe_source':'SSE and SZSE official current plus delisted listings, fetched fresh by HTTPS','price_source_proposed':'Tencent publicly documented raw and hfq daily endpoints; preserve raw and validate canonical factors/volume/calendar before registration','algorithm_unchanged':'pre2019IPO; outdate empty or>=2019-01-01; first10code perSH60/SZ00/SZ30; no replacement','source_documents':['https://akshare.akfamily.xyz/data/stock/stock_issue.html','https://akshare.akfamily.xyz/data/stock/stock_quote.html'],'reference_code_commit':'akfamily/akshare@1b88b68356bebf1fd32461d74a8aaaa66588d2d5','price_requests_so_far':0,'limitations':['Different provider snapshots can revise historical prices and listings','Official current+delisted union not full point-in-time daily eligibility; code reuse/mergers need checks','Tencent missing selected stocks is a hard data-quality blocker, never silently replaced']}
(p/'source-amendment.json').write_text(json.dumps(amend,ensure_ascii=False,indent=2)+'\n')
payload={'price_data_fetched':False,'algorithm_sha256':amend['original_prereg_sha256'],'source_amendment_sha256':hashlib.sha256((p/'source-amendment.json').read_bytes()).hexdigest(),'source_files':{n:hashlib.sha256((q/n).read_bytes()).hexdigest() for n in ['sse-active.bin','sse-delisted.bin','szse-active.bin','szse-delisted.bin']},'selected':selection,'instruments':[r['code'] for r in selection]}
(p/'selection.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n');(p/'instruments.txt').write_text('\n'.join(payload['instruments'])+'\n')
print(json.dumps(payload,ensure_ascii=False,indent=2))
