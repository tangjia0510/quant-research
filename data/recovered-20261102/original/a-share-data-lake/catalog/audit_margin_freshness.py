from pathlib import Path
import json,datetime,hashlib,collections
import pyarrow.parquet as pq
from margin_snapshot_selection import select_latest
R=Path(__file__).resolve().parents[1];groups={};files=[];snapshots=select_latest(R)
paths=sorted((R/'macro/normalized/margin_detail').glob('*.parquet'))+ [x['file'] for x in snapshots.values()]
for p in paths:
 t=pq.read_table(p,columns=['DATE','MARKET','SECUCODE']).to_pylist()
 files.append({'file':str(p.relative_to(R)),'rows':len(t),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
 for r in t:
  if p.parent.name=='margin_detail' and r['DATE'][:10] in snapshots:continue
  key=r['MARKET'];date=r['DATE'][:10];g=groups.setdefault(key,{'latest_observed_date':date,'earliest_observed_date':date,'date_rows':collections.Counter()})
  g['latest_observed_date']=max(g['latest_observed_date'],date);g['earliest_observed_date']=min(g['earliest_observed_date'],date);g['date_rows'][date]+=1
for g in groups.values():
 g['rows_on_latest_observed_date']=g['date_rows'][g['latest_observed_date']];g['rows_on_target_date']=g['date_rows'].get('2026-10-30',0);g['target_date_observed']=g['latest_observed_date']=='2026-10-30';g['status']='observed_target_reached_not_full_history' if g['target_date_observed'] else 'latest_market_observation_behind_target'
d={'generated_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'target':'2026-10-30','source':'actual complete monthly files with validated latest whole-day replacement; excludes overlapping shards and deltas','markets':groups,'files':files,'latest_day_replacement_manifests':[x['manifest'] for x in snapshots.values()],'api_response_complete_not_equal_all_market_date_complete':True,'aggregate_caveat':'margin_accounts is a market-level vendor aggregate without per-exchange fields; its max date cannot certify each exchange daily detail is current.'}
(R/'catalog/margin-per-market-freshness.json').write_text(json.dumps(d,ensure_ascii=False,indent=2));print({k:{x:v for x,v in g.items() if x!='date_rows'} for k,g in groups.items()})
