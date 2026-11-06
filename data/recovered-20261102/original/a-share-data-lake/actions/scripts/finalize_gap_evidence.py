import json,csv,hashlib,collections,datetime
from pathlib import Path
B=Path(__file__).resolve().parents[1];L=B.parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
records=[]
for p in sorted((B/'raw/sina_factors').glob('*.js')):
 t=p.read_text();o=json.JSONDecoder().raw_decode(t[t.find('{'):])[0]
 for r in o['data']:
  if r['d']<'1990-01-01':records.append({'instrument':p.stem[:2]+'.'+p.stem[2:],'source_record':r,'raw_file':str(p.relative_to(B)),'raw_sha256':sha(p),'source_url':f'https://finance.sina.com.cn/realstock/company/{p.stem}/hfq.js'})
r={'generated_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'records_verified':len(records),'exact_date_counts':dict(collections.Counter(x['source_record']['d'] for x in records)),'exact_value_counts':dict(collections.Counter(str(x['source_record']['f']) for x in records)),'synthetic_records_added':0,'interpretation':'1900-01-01 is a vendor-provided basis sentinel, not corporate event effective date; factor string 1.0000000000000000 is copied from raw JSON, not created as missing-value fallback.','records':records}
(B/'catalog/factor-basis-provenance.json').write_text(json.dumps(r,ensure_ascii=False,indent=2))
codes=['689009','920085'];items={c:{'dividends':[],'equity':[]} for c in codes}
for name,file in [('dividends','sharebonus-all.csv'),('equity','equity-universe.csv')]:
 for row in csv.DictReader((B/'normalized'/file).open()):
  c=row.get('SECURITY_CODE')
  if c in items:items[c][name].append({k:row.get(k) for k in (['SECUCODE','REPORT_DATE','ASSIGN_PROGRESS','IMPL_PLAN_PROFILE','EX_DIVIDEND_DATE'] if name=='dividends' else ['SECUCODE','END_DATE','CHANGE_REASON','TOTAL_SHARES_CHANGE'])})
items['689009']['classification']='Sina provider factor coverage gap: independent source contains 4 implemented cash dividend plans, so empty factor history is not evidence of no corporate actions.'
items['920085']['classification']='Unresolved listing/code coverage: CNINFO mapping only, no certified IPO date, no dividend rows in current exact code match; equity events and no Tencent daily history. Cannot certify no events or assume factor1.'
probe=L/'market/probes/baostock-recheck.log'
r={'generated_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'securities':items,'independent_factor_api':{'name':'BaoStock query_adjust_factor','official_docs':'https://www.baostock.com/mainContent?file=localdatafactorInfo.md','endpoint':'public-api.baostock.com:10030','availability':'Existing normal-endpoint check failed DNS and login10002007; no successful session available, no redundant or bypass requests','evidence_file':str(probe.relative_to(L)),'evidence_sha256':sha(probe)},'decision':'Retain both missing factors. No generated factor series; no further crawl after bounded source/documentation check.','input_hashes':{f:sha(B/'normalized'/f) for f in ['sharebonus-all.csv','equity-universe.csv']}}
(B/'catalog/factor-two-gaps-review.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));print({c:(len(x['dividends']),len(x['equity'])) for c,x in items.items()})
