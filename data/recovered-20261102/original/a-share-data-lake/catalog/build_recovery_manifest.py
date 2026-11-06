# PUBLIC SANITIZED COPY (2026-11-06): machine paths generalized; see provenance/publication_transformations.json.
"""Local, credential-free inventory; no network and no branch mutations."""
import datetime,hashlib,json,os
from pathlib import Path
R=Path(__file__).resolve().parents[1]
BRANCHES={
 'reference':{'checkpoint':'reference/catalog.json','entrypoints':['reference/scripts/build_master.py','reference/scripts/finalize_catalog.py'],'mode':'Source-specific collectors; completed artifacts immutable, inspect script before any new snapshot'},
 'market':{'checkpoint':'market/progress.json','entrypoints':['market/scripts/acquire_tencent_daily.py'],'arguments':['--master','a-share-data-lake/market/manifests/universe-sharded-with-bse.csv'],'terminal_manifest':'market/completion-manifest.json'},
 'actions':{'checkpoint':'actions/catalog/factor-status.json','entrypoints':['actions/scripts/fetch_factors_parallel.py','actions/scripts/fetch_equity.py','actions/scripts/fetch_event_tables.py'],'terminal_manifest':'actions/catalog/artifact-manifest.json'},
 'financial_core':{'checkpoint':'fundamentals/catalog/progress.json','entrypoints':['fundamentals/acquire_statements.py']},
 'financial_full_statements':{'checkpoint':'fundamentals/full_statements/catalog/progress.json','entrypoints':['fundamentals/acquire_full_statements.py']},
 'financial_valuations':{'checkpoint':'fundamentals/valuations/catalog/progress.json','entrypoints':['fundamentals/acquire_valuations.py']},
 'financial_disclosures':{'checkpoint':'fundamentals/catalog/disclosure-effective-coverage.json','entrypoints':['fundamentals/acquire_disclosures.py','fundamentals/repair_disclosure_pagination.py'],'mode':'Original partial plus verified replacements; use effective coverage, not raw sum'},
 'macro':{'checkpoint':'macro/manifest.json','entrypoints':['macro/scripts/update_manifest.py'],'mode':'Family-specific checkpoints and collectors; do not launch every collector blindly'},
 'margin_vendor_detail':{'checkpoint':'macro/logs/margin-detail-progress.json','entrypoints':['macro/scripts/collect_margin_detail.py']},
 'margin_official':{'checkpoint':'macro/logs/official-margin-combined-status.json','entrypoints':['macro/scripts/collect_sse_margin_bulk.py','macro/scripts/collect_szse_margin_bulk.py'],'mode':'Combined official exports plus verified API gapfill; original404 kept'},
 'funds':{'checkpoint':'macro/logs/fund-resolution-status.json','entrypoints':['macro/scripts/collect_funds.py'],'mode':'Identity resolved is not full NAV history; aliases and inactive identities separate'},
 'intraday':{'checkpoint':'intraday/catalog/progress.json','entrypoints':['intraday/scripts/collect.py'],'mode':'Recent1970barwindow, bounded first pass only'},
}
def meta(p):
 b=p.read_bytes();return {'path':str(p.relative_to(R)),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
scripts=[]
for p in sorted(R.rglob('*.py')):
 if any(x in p.parts for x in ['__pycache__','source-review','probes','raw','normalized','delivery']):continue
 role='archived_do_not_run_by_default' if any(x in p.name for x in ['_v1','_v2','_v3','pre_star']) else 'inspect_before_run'
 scripts.append(dict(meta(p),role=role))
for name,v in BRANCHES.items():
 p=R/v['checkpoint'];v['checkpoint_file']=meta(p) if p.exists() else None
 try:
  d=json.loads(p.read_text());v['observed_state']=d.get('state',d.get('status'));v['checkpoint_timestamp']=d.get('updated_at',d.get('updated_utc',d.get('generated_at_utc',d.get('generated_at'))))
 except (OSError,ValueError):v['observed_state']='unknown'
 for script in v['entrypoints']:
  if not (R/script).exists():v.setdefault('missing_entrypoints',[]).append(script)
notes=['This is a file/code/checkpoint inventory, not a process supervisor. Running in a JSON is not proof a process is alive.','Do not spawn duplicate collectors; verify owner/process/checkpoint activity first.','No credentials, cookies, tokens or environment dump are included. Public source URLs stay in original receipts.','Local workspace storage is not a promise of permanent storage or a user-device download.','Preserve raw evidence and original failed snapshots; verified replacements are explicit.','Do not run archived scripts or vendor-reference snippets as current collectors.']
try:final=json.loads((R/'catalog/finalization.json').read_text())
except (OSError,ValueError):final={}
d={'schema_version':1,'generated_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'logical_runtime_root':'fin_data/legacy-work','logical_data_lake_root':'fin_data/legacy-work/a-share-data-lake','python_interpreter':'python3','branches':BRANCHES,'download_and_audit_code_inventory':scripts,'rules':notes,'all_queues_complete':bool(final.get('all_acquisition_queues_terminal_verified'))}
p=R/'catalog/recovery-manifest.json';tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(d,ensure_ascii=False,indent=2));os.replace(tmp,p);print(json.dumps({'scripts':len(scripts),'branches':len(BRANCHES),'all_queues_complete':bool(final.get('all_acquisition_queues_terminal_verified'))}))
