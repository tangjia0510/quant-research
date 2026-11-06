"""Link independently verified pagination replacements without erasing failure evidence."""
import pathlib,json,datetime,hashlib
ROOT=pathlib.Path(__file__).resolve().parent
original=json.loads((ROOT/'supplemental/catalog/progress.json').read_text())
rep=ROOT/'pagination_repairs/forecast-stable-v1'
entries=[]
for task in original['tasks']:
 if task.get('status')=='success':continue
 path=rep/'catalog'/task['report']/(task['period']+'.json')
 fixed=json.loads(path.read_text())if path.exists()else{}
 data=rep/fixed['parquet_path']if fixed.get('parquet_path')else None
 verified=bool(fixed.get('status')=='success' and data and data.exists() and hashlib.sha256(data.read_bytes()).hexdigest()==fixed['parquet_sha256'] and fixed['rows']==fixed['source_total'] and fixed['duplicate_keys']==0)
 entries.append({'report':task['report'],'period':task['period'],'original_status':task['status'],'original_error':task.get('error'),'replacement_verified':verified,'replacement_catalog':str(path.relative_to(ROOT))if verified else None,'replacement_rows':fixed.get('rows')if verified else None,'original_raw_retained':True,'note':'Independent stable-sort acquisition snapshot; does not establish revision history.'})
result={'generated_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'original_expected_tasks':original['expected_tasks'],'original_attempted':len(original['tasks']),'original_success':sum(t['status']=='success'for t in original['tasks']),'verified_replacements':sum(x['replacement_verified']for x in entries),'entries':entries}
result['effective_success']=result['original_success']+result['verified_replacements']
result['unresolved_attempted_failures']=len(entries)-result['verified_replacements']
result['unattempted']=result['original_expected_tasks']-result['original_attempted']
result['effective_status']='complete_with_replacements' if result['effective_success']==result['original_expected_tasks'] else 'incomplete'
(ROOT/'catalog/pagination-repairs.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(result['verified_replacements'])
