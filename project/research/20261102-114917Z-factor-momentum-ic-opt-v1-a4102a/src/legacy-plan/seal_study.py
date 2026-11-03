from pathlib import Path
import json,hashlib,datetime,shutil
P=Path(__file__).resolve().parents[1];R=Path(json.loads((P/'outputs/native-study.json').read_text())['workspace']);S=R/'supplementary'
for n in ['package_deliverable.py','seal_study.py']:
 shutil.copy2(P/'scripts'/n,S/'scripts'/n)
h=json.loads((S/'agent-handoff.json').read_text());h.update(remaining_task='Research stopped at bounded budget; see admission.json. Delivery receipts stored outside sealed study.',research_compute_complete=True);(S/'agent-handoff.json').write_text(json.dumps(h,indent=2))
rows=[]
for f in sorted(R.rglob('*')):
 if not f.is_file():continue
 rel=str(f.relative_to(R))
 if rel=='supplementary/final-artifact-manifest.json' or any(part in ['__pycache__','.factor-work'] for part in f.relative_to(R).parts) or f.name=='.study.lock':continue
 with f.open('rb') as stream:
  digest=hashlib.file_digest(stream,'sha256').hexdigest()
 rows.append({'path':rel,'bytes':f.stat().st_size,'sha256':digest})
m={'created_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'study_id':R.name,'file_count':len(rows),'bytes':sum(x['bytes'] for x in rows),'exclusions':['this manifest itself','.study.lock','__pycache__','.factor-work temporary workers'],'files':rows};target=S/'final-artifact-manifest.json';target.write_text(json.dumps(m,ensure_ascii=False,indent=2));print(json.dumps({'path':str(target),'file_count':m['file_count'],'bytes':m['bytes'],'sha256':hashlib.sha256(target.read_bytes()).hexdigest()}))
