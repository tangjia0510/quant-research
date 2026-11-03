from pathlib import Path
import json,hashlib,datetime
P=Path(__file__).resolve().parents[1];O=P/'outputs'
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
records=[]
for s in json.loads((O/'native-studies.json').read_text()):
 root=Path(s['workspace']);assert (root/'freeze.json').exists();target=root/'supplementary/final-artifact-manifest.json';assert not target.exists();files=[]
 for f in sorted(root.rglob('*')):
  if f.is_file() and f!=target:files.append({'path':str(f.relative_to(root)),'bytes':f.stat().st_size,'sha256':sha(f)})
 target.parent.mkdir(exist_ok=True);target.write_text(json.dumps({'sealed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'purpose':'Rejected discovery archival, no native finalization','files':files,'total_files':len(files),'total_bytes':sum(x['bytes'] for x in files)},indent=2))
 records.append({'candidate':s['candidate_id'],'manifest':str(target),'sha256':sha(target),'files':len(files),'bytes':sum(x['bytes'] for x in files)});print(records[-1],flush=True)
(O/'native-sealed-manifests.json').write_text(json.dumps(records,indent=2))
