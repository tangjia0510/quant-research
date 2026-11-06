import json,hashlib,datetime
from pathlib import Path
B=Path(__file__).resolve().parents[1];out=B/'catalog/artifact-manifest.json';files=[]
for p in sorted(B.rglob('*')):
 if not p.is_file() or p==out:continue
 h=hashlib.sha256()
 with p.open('rb') as r:
  for b in iter(lambda:r.read(4*1024*1024),b''):h.update(b)
 files.append({'path':str(p.relative_to(B)),'bytes':p.stat().st_size,'sha256':h.hexdigest()})
r={'generated_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'base_directory':str(B),'status':'first_pass_terminal_with_documented_gaps','files':files,'file_count':len(files),'total_bytes_excluding_this_manifest':sum(x['bytes'] for x in files),'entry_points':['catalog/branch-status.json','catalog/coverage-gaps.json','catalog/factor-integrity-audit.json','catalog/factor-two-gaps-review.json','catalog/factor-basis-provenance.json','catalog/raw-page-integrity.json','catalog/equity-universe.json','README.md']};out.write_text(json.dumps(r,ensure_ascii=False,indent=2));print(json.dumps({'manifest':str(out),'manifest_bytes':out.stat().st_size,'manifest_sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'files':len(files),'artifact_bytes_excluding_manifest':r['total_bytes_excluding_this_manifest']}))
