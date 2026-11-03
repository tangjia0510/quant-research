import pathlib,sys,json,shutil
base=pathlib.Path(__file__).resolve().parents[2];plan=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(base.parent/'quant-research/scripts'))
from quantlib import library
cfg=library.load_config(str(base/'quant-research.json'))
batch=base/'sources/public-mixed/momentum20-v1-20261101'
if not batch.exists(): shutil.copytree(plan,batch)
evidence={}
for name in ['quality.json','missing-sessions.csv','missing-classification.csv','missing-classification-summary.json','factor-events.csv']:
 evidence['quality/'+name]=str(batch/'normalized'/name)
for name in ['preregistration.json','source-amendment.json','source-amendment-2.json','selection.json','freeze-receipt.json']:
 evidence['provenance/'+name]=str(batch/name)
for folder in ['supplemental-notices','suspension-evidence-helper']:
 for p in (batch/folder).iterdir():
  if p.is_file():evidence['evidence/'+folder+'/'+p.name.lower()]=str(p)
result=library.dataset_add(cfg,'cn30-mixed-multiplicative','2026-11-01',str(batch/'normalized/bars.csv'),'csv',universe=str(batch/'normalized/universe.csv'),calendar=str(batch/'mixed-source/calendar.txt'),metadata=json.loads((batch/'normalized/registration-metadata.json').read_text()),evidence=evidence)
(plan/'dataset-registration-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False,indent=2))
