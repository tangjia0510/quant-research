from pathlib import Path
import argparse,json,datetime
import numpy as np,pandas as pd
from scipy import stats
P=Path(__file__).resolve().parents[1];O=P/'outputs';plan=json.loads((P/'research-plan.json').read_text());names=[v['id'] for v in plan['candidates']]
def clean(v):
 if isinstance(v,dict):return {str(k):clean(x) for k,x in v.items()}
 if isinstance(v,list):return [clean(x) for x in v]
 if isinstance(v,(float,np.floating)):return float(v) if np.isfinite(v) else None
 if isinstance(v,(bool,np.bool_)):return bool(v)
 if isinstance(v,(int,np.integer)):return int(v)
 return v
def dump(name,v):(O/name).write_text(json.dumps(clean(v),ensure_ascii=False,indent=2,default=str,allow_nan=False))
def hac(x,lag):
 x=np.asarray(x,dtype=float);x=x[np.isfinite(x)];n=len(x)
 if n<2:return {'n':n,'mean':None,'std':None,'icir':None,'positive_fraction':None,'se':None,'t':None,'one_sided_p':1.}
 mu=x.mean();u=x-mu;var=np.dot(u,u)/n
 for k in range(1,min(lag,n-1)+1):var+=2*(1-k/(lag+1))*np.dot(u[k:],u[:-k])/n
 se=np.sqrt(max(0,var)/n);std=x.std(ddof=1);t=mu/se if se>0 else np.nan
 return {'n':n,'mean':mu,'std':std,'icir':mu/std if std>0 else np.nan,'positive_fraction':np.mean(x>0),'se':se,'t':t,'one_sided_p':stats.norm.sf(t) if np.isfinite(t) else 1.,'ci95':[mu-1.96*se,mu+1.96*se],'hac_lag':lag}
def holm(p):
 order=np.argsort(p);a=np.empty(len(p));prev=0
 for rank,idx in enumerate(order):prev=max(prev,min(1.,(len(p)-rank)*p[idx]));a[idx]=prev
 return a

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--phase',choices=['development','exposed2026'],required=True);args=ap.parse_args()
 if args.phase=='exposed2026':assert (O/'selection.json').exists(),'Must freeze selected candidate first'
 years=range(2020,2026) if args.phase=='development' else [2026];daily=[];groups=[];coverage=[]
 for year in years:
  df=pd.read_parquet(O/f'factor-observations-{year}.parquet').sort_values(['date','instrument'])
  for date,g in df.groupby('date',sort=True):
   segment='train_descriptive' if year<2025 else ('valid_descriptive' if date<=pd.Timestamp('2025-06-30') else 'discovery')
   if year==2026:segment='exposed2026'
   boundary=pd.Timestamp('2024-12-31') if year<2025 else pd.Timestamp('2025-06-30' if segment=='valid_descriptive' else '2025-12-31')
   if year==2026:boundary=pd.Timestamp('2026-10-30')
   qs={name:np.minimum(((g[name].rank(method='first')-1)*5/len(g)).astype(int)+1,5) for name in names}
   for h in [1,5,10]:
    label=g[f'label_{h}'];end=g[f'label_end_{h}'];valid=label.notna()&end.le(boundary);n=int(valid.sum());purge=int((label.notna()&~end.le(boundary)).sum());missing=int(label.isna().sum())
    coverage.append({'date':date,'segment':segment,'horizon':h,'signal_n':len(g),'label_n':n,'label_missing_n':missing,'cross_boundary_n':purge,'too_small_to_measure_ic':n<100})
    if n<100:continue
    for name in names:
     pear=g.loc[valid,name].corr(label[valid]);rank=g.loc[valid,name].corr(label[valid],method='spearman')
     daily.append({'date':date,'year':year,'month':str(date.to_period('M')),'quarter':str(date.to_period('Q')),'segment':segment,'candidate':name,'horizon':h,'signal_n':len(g),'label_n':n,'label_missing_n':missing,'cross_boundary_n':purge,'snapshot_delisted_signal_n':int(g.status_at_snapshot.eq('delisted').sum()),'snapshot_delisted_label_missing_n':int((g.status_at_snapshot.eq('delisted')&~valid).sum()),'pearson_ic':pear,'rank_ic':rank})
     for q in range(1,6):
      signal=qs[name].eq(q);v=signal&valid
      groups.append({'date':date,'year':year,'month':str(date.to_period('M')),'segment':segment,'candidate':name,'horizon':h,'quintile':q,'signal_n':int(signal.sum()),'label_n':int(v.sum()),'missing_or_purged_n':int((signal&~valid).sum()),'mean_forward_return':label[v].mean()})
  print('analyzed',year,flush=True)
 pd.DataFrame(coverage).to_csv(O/f'direct-coverage-{args.phase}.csv',index=False)
 d=pd.DataFrame(daily);gr=pd.DataFrame(groups);d.to_csv(O/f'direct-daily-{args.phase}.csv',index=False);gr.to_csv(O/f'groups-daily-{args.phase}.csv',index=False)
 summary=[]
 for (seg,name,h),z in d.groupby(['segment','candidate','horizon']):
  zgr=gr[(gr.segment==seg)&(gr.candidate==name)&(gr.horizon==h)];w=zgr.pivot(index='date',columns='quintile',values='mean_forward_return')
  mean_groups=zgr.groupby('quintile').mean_forward_return.mean()
  summary.append({'segment':seg,'candidate':name,'horizon':int(h),'pearson':hac(z.pearson_ic,max(5,2*h)),'rank':hac(z.rank_ic,max(5,2*h)),'q5_minus_q1':hac(w[5]-w[1],max(5,2*h)),'group_mean_returns':mean_groups.to_dict(),'group_mean_order_spearman':stats.spearmanr(mean_groups.index,mean_groups.values).statistic,'mean_signal_n':z.signal_n.mean(),'mean_label_n':z.label_n.mean(),'label_availability':z.label_n.sum()/z.signal_n.sum(),'positive_months':int((z.groupby('month').rank_ic.mean()>0).sum()),'month_count':z.month.nunique(),'quarter_means':z.groupby('quarter').rank_ic.mean().to_dict(),'monthly_rank_ic':z.groupby('month').rank_ic.mean().to_dict()})
 dump(f'direct-summary-{args.phase}.json',summary)
 d.groupby(['candidate','horizon','year'])[['pearson_ic','rank_ic','signal_n','label_n']].mean().to_csv(O/f'direct-yearly-{args.phase}.csv')
 if args.phase=='development':
  primary=[x for x in summary if x['segment']=='discovery' and x['horizon']==5];adjust=holm([x['rank']['one_sided_p'] for x in primary]);gate=plan['direct_admission_gates'];selection=[]
  for z,p in zip(primary,adjust):
   z['primary_holm_p']=p;tests={'mean_rank_ic':z['rank']['mean']>=gate['mean_rank_ic_min'],'rank_icir':z['rank']['icir']>=gate['daily_rank_icir_min'],'holm_p':p<=.05,'positive_months':z['positive_months']>=4,'both_quarters_positive':len(z['quarter_means'])==2 and all(x>0 for x in z['quarter_means'].values()),'group_spread':z['q5_minus_q1']['mean']>=.0005};z['gates']=tests;z['all_pass']=all(tests.values());selection.append(z)
  secondary=[x for x in summary if x['segment']=='discovery' and x['horizon']!=5];adj=holm([x['rank']['one_sided_p'] for x in secondary]);
  for z,p in zip(secondary,adj):z['secondary_holm_p']=p
  eligible=[x for x in selection if x['candidate']!='momentum20-reference' and x['all_pass']];pool=eligible or [x for x in selection if x['candidate']!='momentum20-reference'];chosen=max(pool,key=lambda x:x['rank']['mean'])
  record={'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'selected':chosen['candidate'],'direct_gates_passed':bool(eligible),'status':'provisional_retrospective_association_only' if eligible else 'none_admitted_exploratory_native_comparator','primary_family_all6':selection,'secondary_family_all12':secondary,'selection_used_2026_new_candidate_results':False,'prior_2026_influence_already_disclosed':True,'independent_holdout_available':False,'no_direction_or_threshold_changes':True}
  dump('selection.json',record)
  ledger=json.loads((P/'trial-ledger.json').read_text())
  for item in ledger['candidates']:item.update(status='supplementary_discovery_measured',result_seen=True,selected_for_native=item['id'] in ['momentum20-reference',chosen['candidate']])
  (P/'trial-ledger.json').write_text(json.dumps(ledger,ensure_ascii=False,indent=2));print('SELECTED',chosen['candidate'],'PASS',bool(eligible),flush=True)
if __name__=='__main__':main()
