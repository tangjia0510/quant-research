import pathlib,json,datetime,hashlib,sys
import acquire_full_statements as a
import pyarrow.parquet as pq
ROOT=pathlib.Path(__file__).resolve().parent
out=ROOT/'source-review/full-statement-a-cdr-scope';out.mkdir(exist_ok=True)
results=[]
for name,report in a.REPORTS.items():
 p=ROOT/'full_statements/normalized'/name/'2026-06-30.parquet';rows=pq.read_table(p,columns=['SECURITY_TYPE_CODE']).to_pylist();expected=sum(x['SECURITY_TYPE_CODE']in('058001001','058001008')for x in rows)
 params={'reportName':report,'columns':'ALL','filter':'''(REPORT_DATE='2026-06-30')(SECURITY_TYPE_CODE in ("058001001","058001008"))''','pageSize':1,'pageNumber':1,'sortColumns':'SECURITY_CODE','sortTypes':'1'}
 with a.host_gate('eastmoney'):r=a.SESSION.get(a.URL,params=params,timeout=(10,45));body=r.content
 (out/(name+'.json')).write_bytes(body);j=r.json();result=j.get('result')or{};observed=result.get('count');ok=r.status_code==200 and j.get('success')and observed==expected
 receipt={'report':name,'url':r.url,'acquired_at':a.now(),'http_status':r.status_code,'sha256':hashlib.sha256(body).hexdigest(),'unfiltered_saved_rows':len(rows),'local_a_cdr_count':expected,'filtered_api_count':observed,'verified':bool(ok),'scope':'A-share and CDR security types only; no trade-market exclusion and no current-survivor filter','evidence':'Read-only saved AKShare stock_report_em.py at pinned commit uses these exact two security-type codes for A-share statements. Count compared with unfiltered full-table snapshot.'};results.append(receipt);print(name,receipt['verified'],expected,observed,flush=True)
(out/'verification.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
if not all(x['verified']for x in results):sys.exit(1)
