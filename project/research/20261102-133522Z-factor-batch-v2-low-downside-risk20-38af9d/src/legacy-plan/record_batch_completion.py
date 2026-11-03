from pathlib import Path
import json,hashlib,datetime,csv
P=Path(__file__).resolve().parents[1];O=P/'outputs';R=P.parents[1]
original=R/'batches/20261102-price-volume-mechanisms-v2';recovery=R/'batches/20261102-price-volume-mechanisms-v2-serial-recovery-v1'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
s=json.loads((recovery/'state.json').read_text());old=json.loads((original/'state.json').read_text());lineage=json.loads((recovery/'lineage.json').read_text())
assert sha(original/'state.json')=='2d28f3e59d68b5d18bf538d6068a85a8ff43ef586df28410f8ed89f49b202da6'
assert all(x['status'] not in ['pending','running','launching'] for x in s['tasks'].values())
rows=[]
for k,v in s['tasks'].items():
 assert len(v['attempts'])<=2
 oldv=old['tasks'][k]
 assert v['attempts'][:len(oldv['attempts'])]==oldv['attempts']
 if oldv['status']=='success':assert v==oldv, f'Previously successful task changed: {k}'
 for i,a in enumerate(v['attempts'],1):
  start=datetime.datetime.fromisoformat(a['started_at']);end=datetime.datetime.fromisoformat(a['ended_at'])
  rows.append({'task':k,'attempt':i,'started_at':a['started_at'],'ended_at':a['ended_at'],'elapsed_seconds':(end-start).total_seconds(),'returncode':a.get('returncode'),'peak_process_group_rss_mb':a.get('peak_process_group_rss_mb'),'final_task_status':v['status'],'inherited_from_original':i<=len(oldv['attempts'])})
with (O/'batch-timing-attempts.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
record={'recorded_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'original_state_sha256':sha(original/'state.json'),'recovery_state_sha256':sha(recovery/'state.json'),'recovery_plan_sha256':sha(recovery/'plan.json'),'task_status':{k:v['status'] for k,v in s['tasks'].items()},'all_attempts_within_original_limit':True,'old_successes_unchanged':True,'unique_candidates':3,'actual_evaluate_attempts':sum(len(v['attempts']) for k,v in s['tasks'].items() if k.endswith('-evaluate')),'recovery_lineage':lineage,'wall_times_not_additive_due_to_overlap':True,'memory_note':'Sampled process-group RSS is not hard memory control; shared pages can double-count and short peaks can be missed. Two concurrent attempts failed under resource pressure, without definitive kernel OOM evidence.'}
(O/'batch-completion-verification.json').write_text(json.dumps(record,indent=2))
l=json.loads((P/'trial-ledger.json').read_text());l['native_task_attempts']=rows;l['final_batch_status']=record['task_status']
for c in l['candidates']:c['status']=s['tasks'][c['id']+'-evaluate']['status'];c['results_seen']=True;c['seen_scope']='direct development and completed native or failed attempt evidence; new2026 not yet used for selection'
(P/'trial-ledger.json').write_text(json.dumps(l,ensure_ascii=False,indent=2))
print(json.dumps({k:v for k,v in record.items() if k!='recovery_lineage'},indent=2))
