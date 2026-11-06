"""Select only validated whole-day replacement snapshots, never delta files."""
import json,hashlib
from pathlib import Path
def select_latest(root):
 chosen={}
 for p in sorted((root/'macro/logs').glob('margin-latest-refresh-*.json')):
  try:
   d=json.loads(p.read_text());v=d.get('sources',{}).get('vendor',{})
   if v.get('state')!='count_key_date_validated':continue
   item=next(x for x in v.get('files',[]) if Path(x['file']).name=='day_snapshot.parquet')
   f=root/'macro'/item['file']
   if hashlib.sha256(f.read_bytes()).hexdigest()!=item['sha256']:continue
   chosen[d['target_day']]={'day':d['target_day'],'file':f,'manifest':str(p.relative_to(root)),'refresh_id':d['refresh_id'],'sha256':item['sha256']}
  except (OSError,ValueError,KeyError,StopIteration):continue
 return chosen
