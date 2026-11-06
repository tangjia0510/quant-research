import json,datetime,shutil
from pathlib import Path
BASE=Path(__file__).resolve().parents[1];datasets={}
for p in sorted((BASE/'catalog').glob('*-status.json')):
 if p.name=='branch-status.json':continue
 d=json.loads(p.read_text());name=p.name.removesuffix('-status.json')
 if name=='factor':
  items=d.get('items',{});complete=[v for v in items.values() if v['status']=='complete'];datasets[name]={'state':d.get('status','running'),'target_securities':d.get('target_count'),'attempted_securities':len(items),'complete_securities':len(complete),'unavailable_securities':sum(v['status']=='unavailable' for v in items.values()),'blocked_securities':sum(v['status']=='blocked' for v in items.values()),'factor_rows':sum(v['events'] for v in complete),'stop_reason':d.get('stop_reason'),'manifest':str(p.relative_to(BASE))}
 else:datasets[name]={k:d.get(k) for k in ['status','source_rows','rows_downloaded','securities','pages_complete','target_pages','first_event_date','last_event_date','first_report_date','last_report_date','error']};datasets[name]['manifest']=str(p.relative_to(BASE))
for name,file in [('reported_price_limits','hf-price-limits-unique.json'),('current_name_flags','current-name-risk-flags.json')]:
 p=BASE/'catalog'/file
 if p.exists():d=json.loads(p.read_text());datasets[name]={'state':'complete_local_projection','rows':d.get('rows'),'manifest':str(p.relative_to(BASE))}
p=BASE/'catalog/hf-status-audit.json'
if p.exists():
 d=json.loads(p.read_text());datasets['vendor_historical_status']={'state':'complete_field_specific_local_projection','rows':d['accepted_keys'],'securities':d['securities'],'first_date':d['first_date'],'last_date':d['last_date'],'is_st_ones':d['st_flagged_days'],'manifest':str(p.relative_to(BASE)),'quality':'vendor_only_not_exchange_or_PIT_certified'}
p=BASE/'catalog/current-risk-official-shsz.json'
if p.exists():
 d=json.loads(p.read_text());datasets['official_current_risk']={'state':'complete_snapshot','manifest':str(p.relative_to(BASE)),'effective_dates':'unknown','history':'not_inferred'}
size=sum(p.stat().st_size for p in BASE.rglob('*') if p.is_file());result={'generated_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'state':'running' if any(v.get('state',v.get('status'))=='running' for v in datasets.values()) else 'pass_finished_with_documented_gaps','datasets':datasets,'bytes_on_disk':size,'free_bytes':shutil.disk_usage(BASE).free,'gaps_file':'catalog/coverage-gaps.json','warning':'Dataset counts overlap; do not sum them as independent coverage or claim all quant dependencies complete'}
p=BASE/'catalog/branch-status.json';p.write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False))
