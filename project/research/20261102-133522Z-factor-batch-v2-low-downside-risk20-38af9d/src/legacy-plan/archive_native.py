import subprocess,json
from pathlib import Path
P=Path(__file__).resolve().parents[1];R=P.parents[1];base=R.parent;py=R/'runtime/py311/bin/python';cli=base/'quant-research/scripts/quant.py';config=R/'quant-research.json'
assert json.loads((P/'outputs/batch-selection.json').read_text())['native_final_budget']==0
for s in json.loads((P/'outputs/native-studies.json').read_text()):
 for command,args in [('freeze',['--candidates',s['candidate_id']]),('report',[])]:
  cmd=[str(py),str(cli),'--config',str(config),'--worker-threads','1',command,'--workspace',s['workspace']]+args
  proc=subprocess.run(cmd,capture_output=True,text=True)
  (P/'outputs'/f"archive-{s['candidate_id']}-{command}.log").write_text(proc.stdout+'\n'+proc.stderr)
  if proc.returncode:raise RuntimeError((s['candidate_id'],command,proc.returncode))
print('Three studies frozen for rejected-candidate archival; native final intentionally not executed.')
