from pathlib import Path
import sys,json,datetime,subprocess,shutil,hashlib
P=Path(__file__).resolve().parents[1];W=P.parents[2];O=P/'outputs';CLI=W/'quant-research/scripts/quant.py';CFG=W/'quant-research-library/quant-research.json'

def main():
 plan=json.loads((P/'research-plan.json').read_text());frozen=json.loads((P/'plan-freeze.json').read_text());assert hashlib.sha256((P/'research-plan.json').read_bytes()).hexdigest()==frozen['sha256']
 protocol={'schema_version':1,'mode':'factor','objective':'Three fixed price-volume mechanisms; primary paired model RankIC increment vs fixed Ridge baseline; retrospective development and globally bounded parallel batch','data':{},'splits':plan['splits'],'model':plan['model'],'baseline_features':plan['baseline_features'],'label':plan['label'],'preprocessing':plan['preprocessing'],'portfolio':plan['portfolio'],'budget':{'max_trials':1,'max_repairs':1,'timeout_seconds':3600},'seed':plan['seed'],'robustness':{'enabled':True},'research_limitations':plan['limitations']+[plan['exposure'],plan['native_missingness'],'Dataset immutable metadata retains prior-study61-session diagnostic note; THIS supplementary batch uses21-session common signal gate, without changing source bars or native membership'],'selection_rule':'See immutable batch research-plan; all3 terminal first; native HAC10 Holm3 and net noninferiority, separate direct-family gates; no native final budget'}
 protocol_path=P/'native-protocol-input.json';protocol_path.write_text(json.dumps(protocol,ensure_ascii=False,indent=2));records=[]
 for definition in plan['candidates']:
  cid=definition['id'];receipt=O/f'study-{cid}.json'
  if receipt.exists():result=json.loads(receipt.read_text());root=Path(result['workspace']);assert root.exists(),'Previous receipt workspace missing, do not silently allocate another'
  else:
   command=[sys.executable,str(CLI),'--config',str(CFG),'--worker-threads','1','study','new','--slug','batch-v2-'+cid,'--title','量价并行研究 '+cid,'--mode','factor','--dataset',plan['dataset']['id'],'--version',plan['dataset']['version'],'--protocol',str(protocol_path)]
   at=datetime.datetime.now(datetime.timezone.utc).isoformat();p=subprocess.run(command,capture_output=True,text=True);(O/f'create-{cid}.stdout').write_text(p.stdout);(O/f'create-{cid}.stderr').write_text(p.stderr)
   with (O/'creation-command-ledger.jsonl').open('a') as f:f.write(json.dumps({'at':at,'command':command,'returncode':p.returncode})+'\n')
   if p.returncode:raise RuntimeError(p.stderr+p.stdout)
   reply=json.loads(p.stdout);assert reply['ok'];result=reply['result'];receipt.write_text(json.dumps(result,ensure_ascii=False,indent=2));root=Path(result['workspace'])
  drafts=root/'drafts';drafts.mkdir(exist_ok=True);shutil.copy2(P/'scripts/factor_family.py',drafts/'factor_family.py');candidate={'id':cid,'kind':'factor','hypothesis':definition['mechanism']+'; expected positive direct orientation, primary model incremental objective assessed separately','features':plan['baseline_features'],'factor_file':'drafts/factor_family.py','factor_params':{'candidate_id':cid},'max_lookback':definition['lookback'],'factor_timeout':600,'scale_invariant':True,'model':plan['model']};cpath=drafts/(cid+'.json');cpath.write_text(json.dumps(candidate,ensure_ascii=False,indent=2));supp=root/'supplementary';supp.mkdir(exist_ok=True)
  for name in ['research-plan.json','plan-freeze.json','trial-ledger.json']:shutil.copy2(P/name,supp/name)
  shutil.copy2(P/'outputs/factor-tests.log',supp/'factor-preflight-tests.log')
  records.append({'candidate_id':cid,'workspace':str(root),'candidate':str(cpath),'candidate_definition_sha256':hashlib.sha256(cpath.read_bytes()).hexdigest(),'factor_source_sha256':hashlib.sha256((drafts/'factor_family.py').read_bytes()).hexdigest()})
 (O/'native-studies.json').write_text(json.dumps(records,ensure_ascii=False,indent=2));prepares=[{'id':r['candidate_id']+'-prepare','command':'prepare','workspace':r['workspace'],'depends_on':[]} for r in records];pre_ids=[x['id'] for x in prepares];tasks=list(prepares)
 for r in records:
  check=r['candidate_id']+'-check';tasks += [{'id':check,'command':'check','workspace':r['workspace'],'candidate':r['candidate'],'depends_on':pre_ids},{'id':r['candidate_id']+'-evaluate','command':'evaluate','workspace':r['workspace'],'candidate':r['candidate'],'depends_on':[check]}]
 batch={'schema_version':1,'config':str(CFG),'max_workers':2,'worker_threads':1,'global_candidate_budget':3,'max_attempts':2,'timeout_seconds':3600,'memory_budget_mb':6000,'worker_memory_mb':3000,'prepare_memory_mb':4500,'cpu_budget':2,'tasks':tasks};(P/'batch-plan.json').write_text(json.dumps(batch,ensure_ascii=False,indent=2));print(json.dumps({'studies':records,'batch_plan':str(P/'batch-plan.json'),'not_started':True},ensure_ascii=False))
if __name__=='__main__':main()
