import pathlib,json,collections,hashlib,datetime
import pyarrow.parquet as pq
ROOT=pathlib.Path(__file__).resolve().parent
j=json.loads((ROOT/'catalog/disclosure-effective-coverage.json').read_text());occ=collections.defaultdict(list);errors=[];physical=0;future=0
for window in j['windows']:
 if not window['effective_success']:continue
 for leaf in window['leaves']:
  local={}
  for part in leaf['partitions']:
   if not part.get('parquet_path'):continue
   p=ROOT/part['root']/part['parquet_path']
   if hashlib.sha256(p.read_bytes()).hexdigest()!=part['parquet_sha256']:errors.append(str(p));continue
   rows=pq.read_table(p,columns=['announcementId','_announcement_time_utc','_future_at_acquisition']).to_pylist();physical+=len(rows)
   for x in rows:local.setdefault(str(x['announcementId']),x)
  for key,x in local.items():occ[key].append((leaf['window_start'],x['_announcement_time_utc']));future+=int(x['_future_at_acquisition'])
dup={k:v for k,v in occ.items()if len(v)>1}
out={'generated_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'effective_windows':j['effective_success'],'physical_rows_read':physical,'leaf_dedup_rows':sum(len(v)for v in occ.values()),'global_unique_announcement_ids':len(occ),'cross_leaf_duplicate_ids':len(dup),'future_timestamp_rows':future,'hash_mismatch_paths':errors,'duplicate_details':dup,'numeric_linkage_verified':False}
(ROOT/'catalog/disclosure-id-audit.json').write_text(json.dumps(out,ensure_ascii=False,indent=2));print({k:v for k,v in out.items()if k!='duplicate_details'})
