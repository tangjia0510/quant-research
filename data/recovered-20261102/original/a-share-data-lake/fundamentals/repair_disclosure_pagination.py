"""Split source-supported report categories when a single day exceeds 100 API pages."""
import pathlib,json,datetime,hashlib
import acquire_disclosures as a
import pyarrow.parquet as pq
BASE=pathlib.Path(__file__).resolve().parent
progress=json.loads((BASE/'disclosures/catalog/progress.json').read_text())
def leaves(x):
 if x.get('children'):
  for y in x['children']:yield from leaves(y)
 else:yield x
bad=[x for task in progress['tasks']for x in leaves(task)if x.get('status')=='pagination_mismatch' and x.get('repeated_page_detected') and x.get('window_start')==x.get('window_end')]
categories=a.CATEGORIES.split(';');out=[]
for task in bad:
 day=task['window_start'];seen=set();parts=[];complete=True
 for category in categories:
  a.ROOT=BASE/'disclosure_repairs'/day/category;a.ROOT.mkdir(parents=True,exist_ok=True);a.CATEGORIES=category
  try:r=a.acquire(day,day)
  except Exception as e:r={'status':'failed','error':str(e)}
  parts.append({'category':category,'root':str(a.ROOT.relative_to(BASE)),**r})
  if r['status']!='success':complete=False
  if r.get('parquet_path'):
   for row in pq.read_table(a.ROOT/r['parquet_path'],columns=['announcementId']).to_pylist():seen.add(str(row['announcementId']))
  print(day,category,r['status'],r.get('rows'),flush=True)
 original=set(str(x['announcementId'])for x in pq.read_table(BASE/'disclosures'/task['parquet_path'],columns=['announcementId']).to_pylist())
 out.append({'day':day,'original_status':task['status'],'original_rows':task['rows'],'original_expected':task['source_total'],'replacement_unique_ids':len(seen),'all_original_ids_preserved':original<=seen,'verified_complete':complete and len(seen)==task['source_total'] and original<=seen,'parts':parts,'note':'Union by official announcementId across report categories; original incomplete day snapshot preserved.'})
 a.write(BASE/'catalog/disclosure-pagination-repairs.json',{'generated_at':a.now(),'entries':out})
