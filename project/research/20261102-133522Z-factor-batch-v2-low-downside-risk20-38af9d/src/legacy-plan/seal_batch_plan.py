from pathlib import Path
import hashlib,json,datetime
P=Path(__file__).resolve().parents[1];dest=P/'final-artifact-manifest.json';assert not dest.exists();files=[]
for p in sorted(P.rglob('*')):
 if p.is_file() and p!=dest and '__pycache__' not in p.parts:
  h=hashlib.sha256()
  with p.open('rb') as f:
   for b in iter(lambda:f.read(1048576),b''):h.update(b)
  files.append({'path':str(p.relative_to(P)),'bytes':p.stat().st_size,'sha256':h.hexdigest()})
m={'sealed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'decision':'none_admitted','files':files,'total_files':len(files),'total_bytes':sum(x['bytes'] for x in files),'native_studies_bound_by':'outputs/native-sealed-manifests.json','original_and_recovery_bound_by':'outputs/batch-completion-verification.json'};dest.write_text(json.dumps(m,ensure_ascii=False,indent=2));print(json.dumps({'manifest':str(dest),'sha256':hashlib.sha256(dest.read_bytes()).hexdigest(),'files':len(files),'bytes':m['total_bytes']}))
