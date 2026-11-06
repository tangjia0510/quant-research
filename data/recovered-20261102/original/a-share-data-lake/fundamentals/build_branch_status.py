"""Branch status with fixed job denominators; row counts are not additive across sources."""
import pathlib,json,datetime,collections
ROOT=pathlib.Path(__file__).resolve().parent
collections_out=[]
for name in ['.','supplemental','full_statements','special_financials','forward_forecasts','disclosures','valuations','pagination_repairs/forecast-stable-v1']+[str(x.relative_to(ROOT)) for x in sorted((ROOT/'financial_refreshes').glob('*/*'))]+[str(x.relative_to(ROOT)) for x in sorted((ROOT/'disclosure_refreshes').glob('*'))]:
 base=ROOT/name;p=base/'catalog/progress.json'
 if not p.exists():continue
 j=json.loads(p.read_text());tasks=j.get('tasks',[]);receipts=[]
 for r in (base/'receipts').glob('**/*.json'):
  v=json.loads(r.read_text())
  if v.get('acquired_at'):receipts.append(v)
 collections_out.append({'collection':'core'if name=='.'else name,'source_status':j.get('status'),'expected_tasks':j.get('expected_tasks'),'attempted_tasks':len(tasks),'status_counts':dict(collections.Counter(t.get('status')for t in tasks)),'rows_in_successful_source_tasks':sum(t.get('rows',0)for t in tasks if t.get('status')=='success'),'success_receipts':len(receipts),'retrieval_utc_min':min((v['acquired_at']for v in receipts),default=None),'retrieval_utc_max':max((v['acquired_at']for v in receipts),default=None),'raw_response_bytes':sum(v.get('raw_bytes',0)for v in receipts),'stored_raw_bytes':sum(v.get('stored_bytes',0)for v in receipts),'pit_ready':False})
result={'generated_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'collections':collections_out,'effective_coverage_overrides':{},'notes':['Do not add row counts across overlapping summary/full/industry/supplemental tables. Vendor universe scopes differ; use A-share/CDR views and per-partition scope.','Formal notice dates are not verified point-in-time availability of latest numeric snapshots.','Receipts count successful stored pages, not all network attempts; original failed snapshots retained.','Public API access does not establish redistribution rights.']}
for label,path in [('supplemental','catalog/pagination-repairs.json'),('disclosures','catalog/disclosure-effective-coverage.json')]:
 p=ROOT/path
 if p.exists():
  x=json.loads(p.read_text());result['effective_coverage_overrides'][label]={k:v for k,v in x.items()if k not in ['entries','windows']}
(ROOT/'catalog/branch-status.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print([(x['collection'],x['source_status'],x['attempted_tasks'])for x in collections_out])
