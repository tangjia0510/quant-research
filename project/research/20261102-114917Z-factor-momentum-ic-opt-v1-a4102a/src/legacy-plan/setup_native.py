from pathlib import Path
import json,subprocess,sys,datetime,hashlib,inspect,shutil
P=Path(__file__).resolve().parents[1];W=P.parents[2];CLI=W/'quant-research/scripts/quant.py';CFG=W/'quant-research-library/quant-research.json';O=P/'outputs';S=P/'native-source'
def cmd(name,*args):
 t=datetime.datetime.now(datetime.timezone.utc).isoformat();p=subprocess.run([sys.executable,str(CLI),'--config',str(CFG),*map(str,args)],text=True,capture_output=True)
 (O/(name+'.stdout')).write_text(p.stdout);(O/(name+'.stderr')).write_text(p.stderr)
 with (O/'native-command-ledger.jsonl').open('a') as f:f.write(json.dumps({'at':t,'command':[str(CLI),'--config',str(CFG),*map(str,args)],'returncode':p.returncode})+'\n')
 if p.returncode:raise RuntimeError(name+': '+p.stderr[-2000:]+p.stdout[-2000:])
 v=json.loads(p.stdout);assert v['ok'],v;return v['result']
def main():
 plan=json.loads((P/'research-plan.json').read_text())
 proto={'schema_version':1,'mode':'factor','objective':'Mechanism-bounded momentum/reversal IC optimization; native fixed Ridge increment separate from direct factor IC;2026 previously exposed','data':{},'splits':plan['splits'],'model':plan['native_model'],'baseline_features':plan['native_baseline_features'],'label':{'price':'open','entry_lag':1,'horizon':5},'preprocessing':{'clip':10,'label_transform':'raw'},'portfolio':plan['portfolio'],'budget':{'max_trials':2,'max_repairs':2,'timeout_seconds':3600},'seed':42,'robustness':{'enabled':True},'research_limitations':plan['unresolved']+[plan['holdout'],plan['native_missingness'],plan['neutralization']],'selection_rule':'Frozen research-plan.json; see supplementary ledger, Holm6 primary, fixed candidates, no guarantee of admission'}
 (P/'native-protocol-input.json').write_text(json.dumps(proto,ensure_ascii=False,indent=2))
 r=cmd('dataset-add','dataset','add','--id','cn-shsz-audited-quality','--version','2026-11-02-v1','--source',S/'bars.parquet','--format','parquet','--universe',S/'universe.csv','--calendar',S/'calendar.txt','--metadata',S/'metadata.json')
 result=cmd('study-new','study','new','--slug','momentum-ic-opt-v1','--title','量价动量与反转固定候选研究','--mode','factor','--dataset','cn-shsz-audited-quality','--version','2026-11-02-v1','--protocol',P/'native-protocol-input.json')
 (O/'native-study.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));root=Path(result['workspace']);supp=root/'supplementary';supp.mkdir()
 for name in ['research-plan.json','exposure-ledger.json','trial-ledger.json']:shutil.copy2(P/name,supp/name)
 shutil.copytree(P/'scripts',supp/'scripts');shutil.copy2(S/'provenance.json',supp/'source-provenance.json')
 codepaths=[W/'quant-research/SKILL.md',W/'quant-research/references/factor-validation.md',*sorted((W/'quant-research/scripts').rglob('*.py'))]
 (supp/'skill-code-identity.json').write_text(json.dumps({str(x.relative_to(W)):hashlib.sha256(x.read_bytes()).hexdigest() for x in codepaths},indent=2))
 from qlib.backtest.exchange import Exchange
 module=Path(inspect.getfile(Exchange));(supp/'qlib-lot-semantics.json').write_text(json.dumps({'installed_version':'0.9.7','module':str(module),'sha256':hashlib.sha256(module.read_bytes()).hexdigest(),'rounding_function':inspect.getsource(Exchange.round_amount_by_trade_unit),'required_invariant':'No finite close with missingfactor; adjustedamount*factor is rawshares; price*amount cash equal'},indent=2))
 print('NATIVE_ROOT',root,flush=True)
 cmd('prepare','prepare','--workspace',root)
 print('PREPARED',root,flush=True)
if __name__=='__main__':main()
