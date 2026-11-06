"""Produce observed freshness, never infer source-wide completeness from a max date."""
import json,datetime,pathlib,collections
import pyarrow.parquet as pq
ROOT=pathlib.Path(__file__).resolve().parent
SOURCES=[ROOT,ROOT/'supplemental',ROOT/'full_statements',ROOT/'special_financials',ROOT/'forward_forecasts',ROOT/'pagination_repairs/forecast-stable-v1']+sorted((ROOT/'financial_refreshes').glob('*/*'))
def main():
 entries=[]
 for base in SOURCES:
  groups=collections.defaultdict(list)
  for p in (base/'catalog').glob('*/*.json'):
   j=json.loads(p.read_text())
   if j.get('status')=='success' and j.get('parquet_path'):groups[j['report']].append(j)
  for name,metas in groups.items():
   fiscal=[];pub_eligible=[];future=0;acquired=[]
   for j in metas:
    path=base/j['parquet_path'];schema=pq.read_schema(path);cols=[x for x in ['REPORT_DATE','REPORTDATE','NOTICE_DATE','ACTUAL_PUBLISH_DATE','UPDATE_DATE','_acquired_at']if x in schema.names]
    for row in pq.read_table(path,columns=cols).to_pylist():
     f=row.get('REPORT_DATE',row.get('REPORTDATE'));a=row.get('_acquired_at');n=row.get('NOTICE_DATE')or row.get('ACTUAL_PUBLISH_DATE')
     if f:fiscal.append(f)
     if a:acquired.append(a)
     if a and n:
      local_day=datetime.datetime.fromisoformat(a).astimezone(datetime.timezone(datetime.timedelta(hours=8))).date().isoformat()
      if str(n)[:10]<=local_day:pub_eligible.append(n)
      else:future+=1
   entries.append({'collection':str(base.relative_to(ROOT))or'core','table':name,'latest_observed_fiscal_period':max(fiscal,default=None),'latest_vendor_publication_date_not_after_acquisition_local_day':max(pub_eligible,default=None),'future_dated_publication_rows':future,'retrieval_utc_min':min(acquired,default=None),'retrieval_utc_max':max(acquired,default=None),'successful_report_partitions':len(metas),'expected_source_latest_publication':'unknown; not an official completeness certification','pit_ready':False})
 p=ROOT/'valuations/catalog/progress.json'
 if p.exists():
  x=json.loads(p.read_text());success=[r for r in x['tasks']if r.get('status')=='success'];dist=collections.Counter(str(r.get('max_date'))for r in success)
  entries.append({'collection':'valuations','target_last_complete_market_day':'2026-10-30','latest_observed_date':max((r['max_date']for r in success if r.get('max_date')),default=None),'per_security_last_date_distribution':dict(sorted(dist.items())),'successful_securities':len(success),'expected_securities':x['expected_tasks'],'unavailable':x.get('unavailable',0),'failed':x.get('failed',0),'unattempted':x['expected_tasks']-len(x['tasks']),'pit_ready':False})
 for base in [ROOT/'disclosures']+sorted((ROOT/'disclosure_refreshes').glob('*')):
  pubs=[];retrieval=[];future=0;parts=0
  for meta in (base/'catalog').glob('*.json'):
   j=json.loads(meta.read_text())
   if j.get('status')!='success' or not j.get('parquet_path'):continue
   path=base/j['parquet_path'];parts+=1
   for row in pq.read_table(path,columns=['_announcement_time_utc','_acquired_at','_future_at_acquisition']).to_pylist():
    if row['_acquired_at']:retrieval.append(row['_acquired_at'])
    if row['_future_at_acquisition']:future+=1
    elif row['_announcement_time_utc']:pubs.append(row['_announcement_time_utc'])
  query_windows=[]
  for receipt in (base/'receipts').glob('*/*.json'):
   receipt_data=json.loads(receipt.read_text())
   if receipt_data.get('acquired_at'):retrieval.append(receipt_data['acquired_at'])
   if receipt_data.get('query',{}).get('seDate'):query_windows.append(receipt_data['query']['seDate'])
  if parts or query_windows:entries.append({'collection':str(base.relative_to(ROOT)),'query_date_windows':sorted(set(query_windows)),'latest_official_metadata_announcement_timestamp_not_after_acquisition':max(pubs,default=None),'future_dated_publication_rows':future,'retrieval_utc_min':min(retrieval,default=None),'retrieval_utc_max':max(retrieval,default=None),'successful_leaf_windows':parts,'expected_source_latest_publication':'unknown; dates queried do not certify all filings or actual first-public intraday time','numeric_revision_link_verified':False,'pit_ready':False})
 result={'generated_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'entries':entries,'caveat':'Latest observed period/date is not full coverage. Future-dated NOTICE_DATE is preserved in raw data and not counted as available publication. Formal announcement dates may differ from actual first public timestamp; numeric revision vintages unavailable.'}
 (ROOT/'catalog/freshness.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(len(entries))
if __name__=='__main__':main()
