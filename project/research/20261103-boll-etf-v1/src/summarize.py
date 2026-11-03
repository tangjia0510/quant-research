"""Rebuild summary proposals under work; never overwrite accepted research evidence."""
from pathlib import Path
import argparse,json
import pandas as pd
ID='20261103-boll-etf-v1'
def main():
 a=argparse.ArgumentParser();a.add_argument('--project-root',type=Path,required=True);a.add_argument('--work-dir',type=Path);v=a.parse_args();P=v.project_root.resolve();W=v.work_dir.resolve() if v.work_dir else P/'work'/ID;R=P/'research'/ID
 if not W.resolve().is_relative_to((P/'work').resolve()):raise ValueError('Work output outside project/work')
 s=json.loads((W/'summary.json').read_text());episodes=[];holding={}
 for kind in ['boll_breakout','boll_reentry','benchmark']:
  d=pd.read_csv(W/f'{kind}-10bp-daily.csv');start=None;count=0
  for i,row in d.iterrows():
   if row.units>0:
    if start is None:start=row.date
    count+=1
   elif start is not None:episodes.append(dict(kind=kind,entry_date=start,last_held_close=d.iloc[i-1].date,exit_date=row.date,held_sessions=count,open_at_end=False));start=None;count=0
  if start is not None:episodes.append(dict(kind=kind,entry_date=start,last_held_close=d.iloc[-1].date,exit_date=None,held_sessions=count,open_at_end=True))
  rows=[x for x in episodes if x['kind']==kind];holding[kind]=dict(episodes=len(rows),holding_sessions=int((d.units>0).sum()),mean_held_sessions=float(pd.Series([x['held_sessions'] for x in rows]).mean()),median_held_sessions=float(pd.Series([x['held_sessions'] for x in rows]).median()),max_held_sessions=max(x['held_sessions'] for x in rows))
 pd.DataFrame(episodes).to_csv(W/'holding-episodes.csv',index=False)
 compact=dict(primary=[x for x in s['results'] if x['total_friction_bp']==10],primary_active=[x for x in s['monthly_active'] if x['total_friction_bp']==10],holding=holding,decisions=s['decisions'],diagnostic=s['diagnostic'],fixed_cost_sensitivity=[{k:x[k] for k in ['kind','total_friction_bp','total_return','cagr','max_drawdown']} for x in s['results']],limitations=s['limitations'],status='awaiting_independent_audit')
 (W/'key-evidence-proposal.json').write_text(json.dumps(compact,ensure_ascii=False,indent=2)+'\n');print(json.dumps(holding,indent=2))
if __name__=='__main__':main()
