"""Isolated legacy pipeline adapter. Never imports or writes the original study workspace.
Dry-run validates frozen inputs and stages a topological execution plan; it does NOT
claim that unexecuted historical results have been reproduced.
"""
import argparse,hashlib,importlib.util,importlib.metadata,json,os,py_compile,shutil,subprocess,sys
from pathlib import Path
DIAG='20261102-price-volume-quality-v1'
MOM='20261102-114917Z-factor-momentum-ic-opt-v1-a4102a'
def read(p):return json.loads(Path(p).read_text())
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def wr(p,o):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(o,ensure_ascii=False,indent=2)+'\n')
def copy(src,dst):dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst)
def main(rid):
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--project-root',required=True);ap.add_argument('--work-dir',required=True);ap.add_argument('--execute',action='store_true');ap.add_argument('--dry-run',action='store_true');a=ap.parse_args()
 if a.execute and a.dry_run:raise ValueError('Choose execute or dry-run, not both')
 P=Path(a.project_root).resolve();R=P/'research'/rid;O=Path(a.work_dir).resolve()
 if O==P/'work' or not O.is_relative_to(P/'work'):raise ValueError('Use fresh subdirectory under project/work')
 if O.exists() and any(O.iterdir()):raise ValueError('Work attempt exists; use a new attempt directory')
 spec=importlib.util.spec_from_file_location('portable_project',((P.parent if json.loads((P/'project.json').read_text()).get('skill_source') == '..' else P/'skill')/'scripts/project.py'));proj=importlib.util.module_from_spec(spec);spec.loader.exec_module(proj)
 meta=read(R/'research.yaml');archive=Path(proj.resolve(P,'legacy-'+rid)['path']);bindings=read(P/'local-paths.json');rawcount=rawbytes=0
 # Resolve rooted data locations without relying on the old absolute workspace.
 def root(name):
  if name not in bindings:raise ValueError('Missing external root: '+name)
  q=Path(bindings[name]);return (q if q.is_absolute() else P/q).resolve()
 L=root('legacy_library');D=root('data_lake')
 if any(O.is_relative_to(x) or x.is_relative_to(O) for x in [L,D]):raise ValueError('Output overlaps external inputs')
 is30='momentum20-ridge' in rid
 if is30:
  bind=read(P/'environment/momentum30-raw-bindings.json');source=Path(proj.resolve(P,bind['catalog_id'])['path']);inputs=[(source/x['path'],x) for x in bind['files']]
 else:
  manifest=Path(proj.resolve(P,'legacy-diagnostic-input-manifest')['path']);frozen=read(manifest)
  inputs=[]
  for name,x in frozen['inputs'].items():
   rel=Path(name)
   if rel.parts[0]!='a-share-data-lake' or '..' in rel.parts:raise ValueError('Unexpected input manifest path')
   inputs.append((D.joinpath(*rel.parts[1:]),x))
 for p,x in inputs:
  if not p.is_file() or p.stat().st_size!=x['bytes'] or sha(p)!=x['sha256']:raise ValueError('External input missing or changed: '+str(p))
  rawcount+=1;rawbytes+=p.stat().st_size
 O.mkdir(parents=True);S=O/'sandbox';lib=S/'quant-research-library';S.mkdir();(S/'a-share-data-lake').mkdir();(S/'quant-research').symlink_to(P/'skill',target_is_directory=True)
 # Expose ONLY the frozen source membership, not today's broader data lake.
 # New files/factors cannot silently enter a historical replay through a glob.
 if not is30:
  for p,x in inputs:
   view=S/'a-share-data-lake'/p.relative_to(D);view.parent.mkdir(parents=True,exist_ok=True);view.symlink_to(p)
 steps=[];amendments=[];delayed_direct=[]
 def command(name,args,cwd=S):steps.append({'name':name,'argv':[str(x) for x in args],'cwd':str(cwd)})
 def python(name,path,*args):command(name,[sys.executable,path,*args])
 def stage(record,subdir):
  target=lib/subdir/record.name;target.mkdir(parents=True,exist_ok=True);copy(record/'protocol.json',target/'protocol.json')
  for p in sorted((record/'src/legacy').glob('*.py')):copy(p,target/'scripts'/p.name)
  (target/'outputs').mkdir(exist_ok=True);return target
 diag=None
 if not is30:
  diag=stage(P/'research'/DIAG,'diagnostics');(diag/'dataset').mkdir();(diag/'artifacts').mkdir()
  python('rebuild_shared_diagnostic_from_frozen_lake_sources',diag/'scripts/build_diagnostic.py')
  if rid==DIAG:python('evaluate_fixed_diagnostic',diag/'scripts/evaluate.py')
  steps.append({'name':'seal_rebuilt_diagnostic_manifest','internal':'seal_diagnostic','target':str(diag)})
 if meta['type']=='factor' and 'reproductions/' in meta['legacy_ref']['path']:
  target=stage(R,'reproductions')
  if rid=='20261102-amplitude-ovnt-v1':
   # This study depends on prepared OHLC AND the prior ILLIQ monthly base.
   # Rebuild both, never consume the archived intermediate parquet files.
   plan=lib/'plans/momentum-opt-v1';(plan/'scripts').mkdir(parents=True);(plan/'native-source').mkdir()
   copy(P/'research'/MOM/'src/legacy-plan/build_native_source.py',plan/'scripts/build_native_source.py')
   copy(P/'research'/MOM/'evidence/plan/research-plan.json',plan/'research-plan.json')
   python('rebuild_native_source_for_amplitude',plan/'scripts/build_native_source.py')
   proto=read(P/'research'/MOM/'protocol.json');old=dict(proto['data'])
   for k in ['dataset_id','dataset_version','manifest_hash']:proto['data'].pop(k,None)
   proto['data'].update(format='parquet',path=str(plan/'native-source/bars.parquet'),universe=str(plan/'native-source/universe.csv'),calendar=str(plan/'native-source/calendar.txt'))
   pf=O/'dependency-native-protocol.json';wr(pf,proto);native=lib/'studies'/MOM;cfg=O/'quant-research.json'
   wr(cfg,{'schema_version':1,'research_root':str(lib/'studies'),'warehouse_root':str(lib/'warehouse'),'factor_root':str(lib/'factors'),'sources_root':str(lib/'sources'),'runtime_root':str(O/'runtime')})
   base=[sys.executable,((P.parent if json.loads((P/'project.json').read_text()).get('skill_source') == '..' else P/'skill')/'scripts/quant.py'),'--config',cfg,'--worker-threads','1']
   command('initialize_native_dependency',base+['init','--workspace',native,'--protocol',pf]);command('prepare_native_dependency',base+['prepare','--workspace',native])
   prior=stage(P/'research/20261102-illiq-seas-v1','reproductions');steps.append({'name':'bind_prior_rebuilt_diagnostic','internal':'bind_panel','target':str(prior),'diagnostic':str(diag)})
   python('rebuild_prior_illiq_monthly_base',prior/'scripts/build_monthly.py')
   steps.append({'name':'bind_amplitude_rebuilt_inputs','internal':'bind_amplitude','target':str(target),'prior':str(prior),'diagnostic':str(diag),'native':str(native)})
   amendments.append({'reason':'Amplitude has explicit native-prepared and prior-monthly dependencies; recompute before score calculation. Only generated receipt hashes rebound, frozen bars/monthly numeric file hashes must still match.'})
  else:steps.append({'name':'bind_rebuilt_panel_manifest','internal':'bind_panel','target':str(target),'diagnostic':str(diag)})
  python('rebuild_monthly_features',target/'scripts/build_monthly.py');python('evaluate_fixed_paper_candidates',target/'scripts/analyze.py')
 elif meta['type']=='factor':
  if is30:
   plan=lib/'plans/momentum20-v1';plan.mkdir(parents=True);(plan/'mixed-source').mkdir()
   for p,x in inputs:
    # Use validated raw copies in work; no normalized source or report is staged.
    copy(p,plan/p.relative_to(source))
   copy(R/'src/legacy-plan/normalize_mixed.py',plan/'normalize_mixed.py')
   python('normalize_30stock_raw_inputs',plan/'normalize_mixed.py');bars=plan/'normalized/bars.csv';uni=plan/'normalized/universe.csv';cal=plan/'mixed-source/calendar.txt';fmt='csv'
  else:
   plan=lib/'plans/momentum-opt-v1';(plan/'scripts').mkdir(parents=True);(plan/'native-source').mkdir()
   copy(P/'research'/MOM/'src/legacy-plan/build_native_source.py',plan/'scripts/build_native_source.py')
   copy(P/'research'/MOM/'evidence/plan/research-plan.json',plan/'research-plan.json')
   python('rebuild_native_source_from_rebuilt_diagnostic',plan/'scripts/build_native_source.py');bars=plan/'native-source/bars.parquet';uni=plan/'native-source/universe.csv';cal=plan/'native-source/calendar.txt';fmt='parquet'
   # Reproduce the predeclared direct factor family as well; never reselect native candidates.
   family=lib/'plans'/('price-volume-batch-v2' if 'batch-v2' in rid else 'momentum-direct-replay')
   (family/'scripts').mkdir(parents=True);(family/'outputs').mkdir()
   for name in ['build_supplementary.py','analyze_supplementary.py','factor_family.py']:
    copy(R/'src/legacy-plan'/name,family/'scripts'/name)
   for name in ['research-plan.json','trial-ledger.json']:copy(R/'evidence/plan'/name,family/name)
   direct_start=len(steps)
   python('rebuild_fixed_direct_factor_family',family/'scripts/build_supplementary.py')
   for phase in ['development','exposed2026']:python('direct_diagnostics_'+phase,family/'scripts/analyze_supplementary.py','--phase',phase)
   if 'batch-v2' in rid:
    delayed_direct=steps[direct_start:];steps=steps[:direct_start]
  proto=read(R/'protocol.json');old=dict(proto['data'])
  for key in ['dataset_id','dataset_version','manifest_hash']:proto['data'].pop(key,None)
  proto['data'].update(format=fmt,path=str(bars),universe=str(uni),calendar=str(cal));protofile=O/'runtime-protocol.json';wr(protofile,proto)
  amendments.append({'reason':'External managed dataset locator replaced by recomputed work-local files; statistical rules unchanged','original_data_identity':old,'runtime_data_identity':proto['data'],'original_protocol_sha256':sha(R/'protocol.json'),'runtime_protocol_sha256':sha(protofile)})
  native=lib/'studies'/rid;cli=((P.parent if json.loads((P/'project.json').read_text()).get('skill_source') == '..' else P/'skill')/'scripts/quant.py');config=O/'quant-research.json';wr(config,{'schema_version':1,'research_root':str(lib/'studies'),'warehouse_root':str(lib/'warehouse'),'factor_root':str(lib/'factors'),'sources_root':str(lib/'sources'),'runtime_root':str(O/'runtime')})
  base=[sys.executable,cli,'--config',config,'--worker-threads','1']
  command('initialize_replay_study',base+['init','--workspace',native,'--protocol',protofile]);steps.append({'name':'copy_frozen_candidates','internal':'copy_drafts','source':str(R/'src/legacy-drafts'),'target':str(native/'drafts')})
  command('prepare_native_replay',base+['prepare','--workspace',native])
  if delayed_direct:
   steps.append({'name':'bind_rebuilt_native_for_direct_batch','internal':'bind_batch','native':str(native),'family':str(family),'diag':str(diag),'reference':str(lib/'studies'/MOM)})
   steps.extend(delayed_direct)
  candidates=[]
  for p in sorted((R/'src/legacy-drafts').glob('*.json')):
   obj=read(p)
   if 'id' in obj and 'kind' in obj:
    candidates.append(obj['id']);command('check_'+obj['id'],base+['check','--workspace',native,'--candidate',native/'drafts'/p.name]);command('evaluate_'+obj['id'],base+['evaluate','--workspace',native,'--candidate',native/'drafts'/p.name])
  if not candidates:raise ValueError('No frozen candidates found')
  command('report_native_replay',base+['report','--workspace',native])
  amendments.append({'native_candidate_ids':candidates,'selection':'Historical frozen choices replayed, no new candidate selection; no finalize or fresh holdout claim.'})
 # Compile every staged Python file and check command paths/dependency ordering without running heavy computation.
 for p in S.rglob('*.py'):
  if p.is_symlink() or 'a-share-data-lake' in p.parts or 'quant-research' in p.parts:continue
  py_compile.compile(str(p),cfile=str(O/'compile-cache'/(sha(p)+'.pyc')),doraise=True)
 for st in steps:
  if 'argv' in st:
   script=Path(st['argv'][1]);assert script.is_file(),str(script)
 env={}
 for name in ['numpy','pandas','pyarrow','scipy','pyqlib','scikit-learn']:
  try:env[name]=importlib.metadata.version(name)
  except importlib.metadata.PackageNotFoundError:env[name]=None
 locks={str(p.relative_to(P)):sha(p) for p in (P/'environment').glob('*') if p.is_file() and p.name in ['uv.lock','pyproject.toml']}
 result={'research_id':rid,'status':'dryrun_verified_not_recomputed','raw_or_normalized_source_files_verified':rawcount,'input_bytes_verified':rawbytes,'old_intermediate_panels_consumed':False,'execution_order':steps,'output_root':str(O),'protocol_locator_amendments':amendments,'python':sys.version,'packages':env,'environment_lock_hashes':locks,'limitations':['Hash-validated external data-lake normalized source snapshots still required; these are external dataset inputs, not included in bundle.','Dryrun is path/inputs/dependency validation only; no new historical statistics computed.']}
 wr(O/'replay-plan.json',result)
 if not a.execute:print(json.dumps({k:v for k,v in result.items() if k not in ['execution_order','protocol_locator_amendments']},indent=2));return
 if any(env[n] is None for n in ['numpy','pandas','pyarrow','scipy']):raise RuntimeError('Missing environment dependencies')
 for i,st in enumerate(steps):
  if 'argv' in st:
   with (O/f'{i:02d}-{st["name"]}.log').open('w') as f:subprocess.run(st['argv'],cwd=st['cwd'],stdout=f,stderr=subprocess.STDOUT,check=True)
  elif st['internal']=='seal_diagnostic':
   t=Path(st['target']);files={str(p.relative_to(t)):{'sha256':sha(p),'bytes':p.stat().st_size} for folder in ['dataset','artifacts'] for p in (t/folder).rglob('*') if p.is_file() and p.name!='artifact-manifest.json'};wr(t/'artifacts/artifact-manifest.json',{'files':files,'replayed_from_raw_sources':True})
  elif st['internal']=='bind_panel':
   t=Path(st['target']);p=read(t/'protocol.json');oldhash=p['data']['manifest_sha256'];p['data']['manifest_sha256']=sha(Path(st['diagnostic'])/p['data']['manifest']);wr(t/'protocol.json',p);wr(t/'replay-locator-amendment.json',{'original_manifest_sha256':oldhash,'rebuilt_manifest_sha256':p['data']['manifest_sha256'],'rules_changed':False})
  elif st['internal']=='copy_drafts':shutil.copytree(st['source'],st['target'])
  elif st['internal']=='bind_amplitude':
   t=Path(st['target']);prior=Path(st['prior']);p=read(t/'protocol.json');original=dict(p['data']);native=Path(st['native'])
   assert sha(native/'data/bars.parquet')==p['data']['bars_sha256'],'Rebuilt amplitude OHLC differs from frozen bytes'
   assert sha(prior/'outputs/monthly-panel.parquet')==p['data']['monthly_panel_sha256'],'Rebuilt prior monthly panel differs from frozen bytes'
   wr(prior/'final-artifact-manifest.json',{'files':[{'path':'outputs/'+name,'sha256':sha(prior/'outputs'/name)} for name in ['calendar.txt','monthly-panel.parquet']],'scope':'rebuilt dependency subset; not original complete study seal'})
   p['data']['prior_seal_sha256']=sha(prior/'final-artifact-manifest.json');p['data']['original_manifest_sha256']=sha(Path(st['diagnostic'])/'artifacts/artifact-manifest.json');wr(t/'protocol.json',p)
   wr(t/'replay-locator-amendment.json',{'original_data':original,'rebuilt_data':p['data'],'numeric_file_identity_unchanged':True,'original_seal_not_forged':True})
  elif st['internal']=='bind_batch':
   import pandas as pd
   native=Path(st['native']);ref=Path(st['reference']);family=Path(st['family']);plan=read(family/'research-plan.json')
   # These exact prepared-data hashes are frozen in the original batch protocol.
   # Do not silently substitute differing numeric/physical datasets on replay.
   assert sha(native/'data/bars.parquet')==plan['dataset']['reference_prepared_bars_sha256'],'Rebuilt native bars hash differs; review serializer/data identity before direct replay'
   assert sha(native/'data/eligibility.parquet')==plan['dataset']['reference_eligibility_sha256'],'Rebuilt eligibility hash differs'
   if ref!=native:ref.symlink_to(native,target_is_directory=True)
   status=pd.read_csv(Path(st['diag'])/'dataset/universe-frozen.csv')[['symbol','status']].rename(columns={'symbol':'instrument','status':'status_at_snapshot'})
   sp=native/'supplementary/development/supplementary-coverage.csv';sp.parent.mkdir(parents=True,exist_ok=True);status.to_csv(sp,index=False)
   wr(native/'supplementary/final-artifact-manifest.json',{'files':[{'path':str(sp.relative_to(native)),'sha256':sha(sp)}],'replay_note':'Only status lookup regenerated from frozen universe; no original supplementary matrices consumed.'})
 result['status']='executed_results_require_comparison';wr(O/'replay-plan.json',result);print(json.dumps({'status':result['status'],'output_root':str(O)},indent=2))
