from pathlib import Path
import json,datetime,hashlib
import numpy as np,pandas as pd
from analyze_supplementary import hac,holm,clean
P=Path(__file__).resolve().parents[1];O=P/'outputs'
def main():
 plan=json.loads((P/'research-plan.json').read_text());studies=json.loads((O/'native-studies.json').read_text());assert len(studies)==3;direct={x['candidate']:x for x in json.loads((O/'direct-admission-development.json').read_text())['primary_all3']};rows=[];baselines=[]
 for item in studies:
  cid=item['candidate_id'];root=Path(item['workspace']);runpath=root/'runs/discovery'/cid/'run.json'
  if not runpath.exists():
   rows.append({'candidate':cid,'completed':False,'reason':'No completed native run; inspect batch failure ledger','native_one_sided_p':1.0,'direct_pass':direct[cid]['all_pass']});continue
  run=json.loads(runpath.read_text());assert run['status']!='running','Wait for all native tasks to terminate'
  if run['status']!='complete':rows.append({'candidate':cid,'completed':False,'reason':run.get('error',run['status']),'native_one_sided_p':1.0,'direct_pass':direct[cid]['all_pass']});continue
  attempt=root/'runs/discovery'/cid/f"attempt-{run['attempt']}";m=json.loads((attempt/'metrics.json').read_text());a=pd.read_csv(attempt/'daily-ic.csv').set_index('date');b=pd.read_csv(attempt/'baseline/daily-ic.csv').set_index('date');assert a.index.is_unique and b.index.is_unique;assert a.index.equals(b.index),'Candidate/baseline dates must match exactly';assert np.isfinite(a[['ic','rank_ic']]).all().all() and np.isfinite(b[['ic','rank_ic']]).all().all(),'No silent nonfinite IC drop';paired=a[['rank_ic']].join(b[['rank_ic']],lsuffix='_candidate',rsuffix='_baseline',how='inner');assert len(paired)==len(a)==len(b);unc=hac(paired.rank_ic_candidate-paired.rank_ic_baseline,10);portfolio={}
  for label,path in [('candidate',attempt/'portfolio.csv'),('baseline',attempt/'baseline/portfolio.csv'),('equal_weight_near_cash_not_market_benchmark',attempt/'equal-weight.csv')]:
   f=pd.read_csv(path);exposure=f.value/f.account;wealth=np.cumprod(1+f['return']-f.cost);assert np.allclose(f.account,100000*wealth,rtol=1e-6);assert np.allclose(f.account,f.value+f.cash,rtol=1e-6)
   portfolio[label]={'net_total_return':wealth.iloc[-1]-1,'gross_total_return':np.prod(1+f['return'])-1,'mean_stock_exposure':exposure.mean(),'terminal_cash':f.cash.iloc[-1],'terminal_account':f.account.iloc[-1],'total_nominal_cost':f.total_cost.iloc[-1],'mean_daily_turnover':f.turnover.mean(),'mean_daily_cost':f.cost.mean(),'days':len(f)}
  rows.append({'candidate':cid,'completed':True,'attempt':run['attempt'],'workspace':str(root),'native_prediction_metrics':m['signal'],'baseline_prediction_metrics':m['baseline']['signal'],'native_engine_increment_lag5':m['increment'],'prespecified_increment_hac10':unc,'native_one_sided_p':unc['one_sided_p'],'portfolio':portfolio,'robustness':m['robustness'],'direct_pass':direct[cid]['all_pass'],'paired_dates':len(paired),'native_label_dates':len(a),'baseline_label_dates':len(b),'daily_series_all_finite':bool(np.isfinite(a[['ic','rank_ic']]).all().all() and np.isfinite(b[['ic','rank_ic']]).all().all())});baselines.append((cid,pd.read_parquet(attempt/'baseline/predictions.parquet')))
 assert {x['candidate'] for x in rows}=={x['id'] for x in plan['candidates']};corrected=holm([x['native_one_sided_p'] for x in rows])
 for row,p in zip(rows,corrected):
  row['native_holm3_p']=float(p)
  if row['completed']:
   u=row['prespecified_increment_hac10'];g={'mean_increment_positive':u['mean']>0,'hac10_lower95_positive':u['ci95'][0]>0,'holm3_p':p<=.05,'net_not_inferior_to_baseline':row['native_engine_increment_lag5']['annualized_net_return_difference']>=0};row['native_gates']=g;row['native_pass']=all(g.values())
  else:row['native_pass']=False
  row['retained_for_further_research']=row['native_pass'] and row['direct_pass']
 equivalence=[]
 if baselines:
  refid,ref=baselines[0]
  for cid,b in baselines[1:]:
   assert ref.index.equals(b.index);assert np.allclose(ref.label,b.label,equal_nan=True,rtol=0,atol=0);diff=float(np.max(np.abs(ref.prediction-b.prediction)));assert diff<1e-10,'Baselines not numerically equivalent';equivalence.append({'first':refid,'second':cid,'rows':len(ref),'max_abs_prediction_difference':diff})
 eligible=[x for x in rows if x['retained_for_further_research']];eligible.sort(key=lambda x:(-x['prespecified_increment_hac10']['mean'],x['portfolio']['candidate']['mean_daily_turnover'],x['candidate']));result={'frozen_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'primary_objective':'paired model RankIC increment; direct claimed orientation independently required','all_candidates':rows,'selected':eligible[0]['candidate'] if eligible else None,'decision':'retain_for_further_historical_research_only' if eligible else 'none_admitted','baseline_equivalence':equivalence,'native_final_budget':0,'independent_holdout_available':False,'new2026_metrics_used_to_select':False,'prior_exposure_carried_forward':True,'no_candidates_added_after_results':True};(O/'batch-selection.json').write_text(json.dumps(clean(result),ensure_ascii=False,indent=2,allow_nan=False));print(json.dumps({'selected':result['selected'],'decision':result['decision'],'candidates':len(rows)},ensure_ascii=False))
if __name__=='__main__':main()
