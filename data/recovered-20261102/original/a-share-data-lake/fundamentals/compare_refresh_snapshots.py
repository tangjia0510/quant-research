"""Observed snapshot differences only; not a certified historical restatement lineage."""
import pathlib,json,collections,datetime
import pyarrow.parquet as pq
ROOT=pathlib.Path(__file__).resolve().parent
out=[]
for version in sorted((ROOT/'financial_refreshes').glob('*')):
 for name,oldbase in [('full','full_statements'),('industry','special_financials'),('forward_forecasts','forward_forecasts')]:
  for p in (version/name/'catalog').glob('*/*.json'):
   m=json.loads(p.read_text());rel=m.get('parquet_path')
   if m.get('status')!='success' or not rel:continue
   old=ROOT/oldbase/rel;new=version/name/rel
   if not old.exists():continue
   a=pq.read_table(old).to_pylist();b=pq.read_table(new).to_pylist()
   if name=='full':a=[x for x in a if x.get('SECURITY_TYPE_CODE')in('058001001','058001008')]
   def key(x):return (x.get('SECURITY_CODE'),x.get('REPORT_DATE',x.get('REPORTDATE')),x.get('PREDICT_FINANCE_CODE'),x.get('NOTICE_DATE'))
   aa={key(x):x for x in a};bb={key(x):x for x in b};changed=[]
   for k in aa.keys()&bb.keys():
    cols=set(aa[k])|set(bb[k]);diff=[col for col in cols if not col.startswith('_')and aa[k].get(col)!=bb[k].get(col)]
    if diff:changed.append({'key':k,'changed_source_fields':sorted(diff)})
   out.append({'refresh':str(version.relative_to(ROOT)),'family':name,'report':m['report'],'period':m['period'],'prior_scope_matched_rows':len(a),'refreshed_rows':len(b),'prior_unique_keys':len(aa),'refreshed_unique_keys':len(bb),'added_keys':sorted(bb.keys()-aa.keys(),key=str),'removed_keys':sorted(aa.keys()-bb.keys(),key=str),'changed_records':changed,'observed_value_changes':len(changed),'old_path':str(old.relative_to(ROOT)),'new_path':str(new.relative_to(ROOT))})
result={'generated_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'entries':out,'pit_ready':False,'caveat':'Changes between our two observed downloads only, not an exhaustive or first-public revision history. Keys include notice date; a changed notice date appears as removed/added. Metadata and schema changes are not automatically accounting restatements.'}
(ROOT/'catalog/latest-refresh-comparison.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print([(x['report'],len(x['added_keys']),len(x['removed_keys']),x['observed_value_changes'])for x in out])
