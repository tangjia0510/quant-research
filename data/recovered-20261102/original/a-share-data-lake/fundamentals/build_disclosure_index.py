"""Effective announcement coverage including verified category-split repairs."""
import pathlib,json,datetime
ROOT=pathlib.Path(__file__).resolve().parent
j=json.loads((ROOT/'disclosures/catalog/progress.json').read_text())
p=ROOT/'catalog/disclosure-pagination-repairs.json';repair=json.loads(p.read_text())['entries']if p.exists()else[];rep={x['day']:x for x in repair if x.get('verified_complete')}
def leaves(x):
 if x.get('children'):
  for y in x['children']:yield from leaves(y)
 else:yield x
windows=[]
for task in j['tasks']:
 entries=[];valid=True;total=0
 for leaf in leaves(task):
  if leaf['status']=='success':
   count=leaf.get('rows',0);entry={'status':'original_verified','rows':count,'partitions':[{'root':'disclosures','parquet_path':leaf.get('parquet_path'),'parquet_sha256':leaf.get('parquet_sha256')}]} 
  elif leaf['window_start']==leaf['window_end'] and leaf['window_start']in rep:
   r=rep[leaf['window_start']];count=r['replacement_unique_ids'];entry={'status':'verified_category_replacement','rows':count,'deduplication_key':'announcementId','partitions':[{'root':x['root'],'parquet_path':x.get('parquet_path'),'parquet_sha256':x.get('parquet_sha256')}for x in r['parts']]}
  else:valid=False;count=leaf.get('rows',0);entry={'status':'unresolved','rows':count,'error':leaf.get('status')}
  total+=count;entries.append({'window_start':leaf.get('window_start'),'window_end':leaf.get('window_end'),**entry})
 windows.append({'window_start':task['window_start'],'window_end':task['window_end'],'effective_success':valid,'unique_rows_within_window':total,'leaves':entries})
out={'generated_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'expected_windows':j['expected_tasks'],'attempted_windows':len(windows),'effective_success':sum(x['effective_success']for x in windows),'unattempted':j['expected_tasks']-len(windows),'effective_rows':sum(x['unique_rows_within_window']for x in windows if x['effective_success']),'windows':windows,'caveat':'Metadata only, not PDF contents; category replacements must be deduplicated by announcementId. Future timestamps retain flags, not PIT-ready numerical data.'}
(ROOT/'catalog/disclosure-effective-coverage.json').write_text(json.dumps(out,ensure_ascii=False,indent=2));print(out['effective_success'],out['effective_rows'])
