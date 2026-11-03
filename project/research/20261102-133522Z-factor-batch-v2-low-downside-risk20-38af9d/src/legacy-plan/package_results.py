from pathlib import Path
import json,zipfile,hashlib,datetime
P=Path(__file__).resolve().parents[1];R=P.parents[1];BASE=R.parent;D=BASE/'deliverables/price-volume-batch-v2-20261102';D.mkdir(parents=True,exist_ok=True)
items={}
def add(p,name):
 if p.is_file():items[str(name)]=p
for p in sorted(P.rglob('*')):
 if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.parquet','.pyc') and '/qa/' not in str(p) and '/rendered/' not in str(p):add(p,Path('research')/p.relative_to(P))
for b in ['20261102-price-volume-mechanisms-v2','20261102-price-volume-mechanisms-v2-serial-recovery-v1']:
 root=R/'batches'/b
 for p in sorted(root.rglob('*')):
  if p.is_file() and p.suffix in ['.json','.log']:add(p,Path('batch-evidence')/b/p.relative_to(root))
for root in [R/'engineering-audits/batch-scheduler-v1',BASE/'engineering-audits/batch-scheduler-v1/resource-amendment-v1']:
 for p in sorted(root.glob('*')):
  if p.is_file() and p.suffix in ['.json','.py','.md']:add(p,Path('independent-audits')/root.name/p.name)
for s in json.loads((P/'outputs/native-studies.json').read_text()):
 root=Path(s['workspace']);prefix=Path('native-studies')/s['candidate_id']
 for name in ['protocol.json','study.json','freeze.json','report.md','report.html','supplementary/final-artifact-manifest.json']:
  add(root/name,prefix/name)
 for dirname in ['drafts','candidates']:
  for p in sorted((root/dirname).rglob('*')):
   if p.is_file() and p.suffix in ['.json','.py']:add(p,prefix/p.relative_to(root))
 for p in sorted((root/'runs/discovery').rglob('*')):
  if p.is_file() and (p.name in ['metrics.json','result.json','run.json','daily-ic.csv','portfolio.csv','portfolio-orders.csv','equal-weight.csv','equal-weight-orders.csv','double_cost.csv','delayed_signal.csv','execution.log']):add(p,prefix/p.relative_to(root))
for p in sorted((BASE/'quant-research/scripts').rglob('*.py')):
 if '__pycache__' not in p.parts:add(p,Path('frozen-skill/scripts')/p.relative_to(BASE/'quant-research/scripts'))
for p in [BASE/'quant-research/SKILL.md',*sorted((BASE/'quant-research/references').glob('*.md'))]:add(p,Path('frozen-skill')/p.relative_to(BASE/'quant-research'))
entries=[]
for name,p in items.items():entries.append({'path':name,'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
manifest={'created_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'no_full_market_parquet_included':True,'all_native_finalization_omitted_by_budget':True,'files':entries}
zip_path=D/'三机制量价因子研究-20261102.zip'
with zipfile.ZipFile(zip_path,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
 for name,p in items.items():z.write(p,name)
 z.writestr('PACKAGE-MANIFEST.json',json.dumps(manifest,ensure_ascii=False,indent=2))
with zipfile.ZipFile(zip_path) as z:assert z.testzip() is None
result={'path':str(zip_path),'bytes':zip_path.stat().st_size,'files':len(items)+1,'sha256':hashlib.sha256(zip_path.read_bytes()).hexdigest()};(D/'package-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False))
