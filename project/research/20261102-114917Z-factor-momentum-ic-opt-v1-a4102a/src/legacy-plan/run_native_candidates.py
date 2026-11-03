from pathlib import Path
import json,subprocess,sys,datetime,shutil,hashlib
P=Path(__file__).resolve().parents[1];W=P.parents[2];O=P/'outputs';root=Path(json.loads((O/'native-study.json').read_text())['workspace']);CLI=W/'quant-research/scripts/quant.py';CFG=W/'quant-research-library/quant-research.json'
def cmd(name,*args):
 now=datetime.datetime.now(datetime.timezone.utc).isoformat();print('START',name,now,flush=True)
 command=[sys.executable,str(CLI),'--config',str(CFG),*map(str,args)]
 with (O/(name+'.stdout')).open('w') as out,(O/(name+'.stderr')).open('w') as err:p=subprocess.run(command,stdout=out,stderr=err)
 with (O/'native-command-ledger.jsonl').open('a') as f:f.write(json.dumps({'at':now,'command':command,'returncode':p.returncode})+'\n')
 if p.returncode:raise RuntimeError(name+':'+(O/(name+'.stderr')).read_text()[-2000:]+(O/(name+'.stdout')).read_text()[-1000:])
 result=json.loads((O/(name+'.stdout')).read_text());assert result['ok'],result;print('DONE',name,flush=True);return result

def main():
 assert (root/'data/manifest.json').exists(),'Native preparation must finish successfully first'
 integrity=json.loads((O/'selection-integrity.json').read_text());assert integrity['family_primary6_secondary12_verified'];assert hashlib.sha256((O/'selection.json').read_bytes()).hexdigest()==integrity['selection_sha256']
 selection=json.loads((O/'selection.json').read_text());plan=json.loads((P/'research-plan.json').read_text());ids=['momentum20-reference',selection['selected']];definitions={x['id']:x for x in plan['candidates']}
 drafts=root/'drafts';drafts.mkdir(exist_ok=True);shutil.copy2(P/'scripts/factor_family.py',drafts/'factor_family.py')
 for cid in ids:
  definition=definitions[cid];candidate={'id':cid,'kind':'factor','hypothesis':definition['mechanism']+'; direct selected by frozen Holm6 gates; model prediction IC is a separate baseline increment; all reversal-family directions influenced by previously exposed history','features':plan['native_baseline_features'],'factor_file':'drafts/factor_family.py','factor_params':{'candidate_id':cid},'max_lookback':definition['lookback'],'factor_timeout':600,'scale_invariant':True,'model':plan['native_model']}
  path=drafts/(cid+'.json');path.write_text(json.dumps(candidate,ensure_ascii=False,indent=2))
  cmd('check-'+cid,'check','--workspace',root,'--candidate',path)
  cmd('evaluate-'+cid,'evaluate','--workspace',root,'--candidate',path)
 # Freeze both compared implementations before retrospective final evaluation.
 cmd('freeze','freeze','--workspace',root,'--candidates',*ids)
 print('FROZEN_READY_FOR_RETROSPECTIVE_FINAL',flush=True)
if __name__=='__main__':main()
