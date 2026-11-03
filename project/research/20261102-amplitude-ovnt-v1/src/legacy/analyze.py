from pathlib import Path
import json,datetime,hashlib
import numpy as np,pandas as pd
from scipy.stats import norm,spearmanr
P=Path(__file__).resolve().parents[1];O=P/'outputs';plan=json.loads((P/'protocol.json').read_text());cfg={c['id']:c for c in plan['candidates']}
def clean(x):
 if isinstance(x,dict):return {str(k):clean(v) for k,v in x.items()}
 if isinstance(x,list):return [clean(v) for v in x]
 if isinstance(x,(np.floating,float)):return float(x) if np.isfinite(x) else None
 if isinstance(x,(np.bool_,bool)):return bool(x)
 if isinstance(x,(np.integer,int)):return int(x)
 return x

def monthly_hac(series,lag=3):
 s=series.copy();assert s.index.is_unique;s.index=pd.PeriodIndex(s.index,freq='M');s=s.sort_index().reindex(pd.period_range(s.index.min(),s.index.max(),freq='M'));x=s.to_numpy(dtype=float);assert not np.isinf(x).any(),'Infinite metrics are invalid';ok=np.isfinite(x);n=int(ok.sum());mu=float(np.nanmean(x)) if n else np.nan;u=np.where(ok,x-mu,0.);pairs=[]
 if n<2:return {'n':n,'calendar_months':len(x),'missing_months':int((~ok).sum()),'mean':mu,'one_sided_p':1.,'ci95':[np.nan,np.nan],'hac_lag':lag}
 variance=np.dot(u,u)
 for k in range(1,min(lag,len(x)-1)+1):
  pairs.append(int((ok[k:]&ok[:-k]).sum()));variance+=2*(1-k/(lag+1))*np.dot(u[k:],u[:-k])
 se=np.sqrt(max(0.,variance))/n;sd=np.std(x[ok],ddof=1);t=mu/se if se>0 else np.nan
 return {'n':n,'calendar_months':len(x),'missing_months':int((~ok).sum()),'mean':mu,'std':sd,'icir':mu/sd if sd>0 else np.nan,'positive_fraction':float(np.mean(x[ok]>0)),'se':se,'t':t,'ci95':[mu-1.96*se,mu+1.96*se],'one_sided_p':float(norm.sf(t)) if np.isfinite(t) else 1.,'hac_lag':lag,'finite_pairs_per_calendar_lag':pairs}
def holm(p):
 a=np.empty(len(p));last=0.
 for rank,idx in enumerate(np.argsort(p)):last=max(last,min(1.,(len(p)-rank)*p[idx]));a[idx]=last
 return a

def turnover(now,previous):return sum(abs(now.get(k,0.)-previous.get(k,0.)) for k in now.keys()|previous.keys())
def group_stats(g,label):
 x=g[label].to_numpy(dtype=float);ok=np.isfinite(x);N=len(x);n=int(ok.sum());known=float(x[ok].sum()/N);missing=1-n/N
 return {'intended_n':N,'known_n':n,'missing_n':N-n,'missing_weight':missing,'conditional_mean':float(x[ok].mean()) if n else np.nan,'full_weight_known_contribution':known,'full_portfolio_return':known if n==N else np.nan,'long_only_lower_bound':known-missing,'mature':bool(g['close_mature' if label=='label_close' else 'open_mature'].all())}

def main():
 sig=pd.read_parquet(O/'signals.parquet');monthly=[];groups=[];assignment=[];min_cross=100
 for cid,sub in sig.groupby('candidate',sort=True):
  bins=cfg[cid]['bins'];prev={k:{} for k in range(bins+1)}
  for month,g in sub.groupby('target_month',sort=True):
   g=g.sort_values(['score','instrument']).copy();N=len(g)
   if N<min_cross:continue
   g['group']=np.arange(N)*bins//N+1;assert g.instrument.is_unique
   assignment.append(g[['candidate','target_month','instrument','score','group']])
   weights={k:{v:1/len(h) for v in h.instrument} for k,h in g.groupby('group')};weights[0]={v:1/N for v in g.instrument};to={k:turnover(w,prev[k]) for k,w in weights.items()};prev=weights
   for label in ['label_close','label_open']:
    stats={k:group_stats(h,label) for k,h in g.groupby('group')};pool=group_stats(g,label)
    for k,st in stats.items():groups.append({'candidate':cid,'target_month':month,'label':label,'group':int(k),'target_weight_turnover_proxy':to[k],**st})
    valid=np.isfinite(g[label]);h=g[valid];ic=rank=np.nan
    if len(h)>=100 and h.score.nunique()>1 and h[label].nunique()>1:ic=float(h.score.corr(h[label]));rank=float(spearmanr(h.score,h[label]).statistic)
    a,b=stats[bins],stats[1];spread=a['conditional_mean']-b['conditional_mean'];longexcess=a['conditional_mean']-pool['conditional_mean'];twoleg=to[bins]+to[1]
    row={'candidate':cid,'target_month':month,'label':label,'signal_n':N,'label_n':len(h),'pearson_ic':ic,'rank_ic':rank,'spread_conditional':spread,'long_only_conditional':a['conditional_mean'],'pool_conditional':pool['conditional_mean'],'long_only_excess_conditional':longexcess,'long_only_full_weight_lower_bound':a['long_only_lower_bound'],'long_only_full_portfolio_return':a['full_portfolio_return'],'top_missing_weight':a['missing_weight'],'bottom_missing_weight':b['missing_weight'],'pool_missing_weight':pool['missing_weight'],'two_leg_target_turnover_proxy':twoleg,'long_only_target_turnover_proxy':to[bins],'pool_target_turnover_proxy':to[0],'mature':pool['mature']}
    for bp in [10,25,30,50]:
     row[f'ls_cost_proxy_{bp}bp']=spread-twoleg*bp/10000;row[f'long_only_cost_proxy_{bp}bp']=a['conditional_mean']-to[bins]*bp/10000;row[f'long_only_excess_cost_proxy_{bp}bp']=longexcess-(to[bins]-to[0])*bp/10000
    monthly.append(row)
 d=pd.DataFrame(monthly);g=pd.DataFrame(groups);d.to_csv(O/'monthly-diagnostics.csv',index=False);g.to_csv(O/'monthly-groups.csv',index=False);pd.concat(assignment).to_parquet(O/'group-assignments.parquet',index=False,compression='zstd')
 summaries=[];annual=[]
 for (cid,label),x in d.groupby(['candidate','label']):
  x=x.sort_values('target_month');x=x[x.mature].set_index('target_month');metrics={k:monthly_hac(x[k],cfg[cid]['monthly_hac_lag']) for k in ['spread_conditional','pearson_ic','rank_ic','long_only_conditional','pool_conditional','long_only_excess_conditional','long_only_full_weight_lower_bound','ls_cost_proxy_10bp','ls_cost_proxy_25bp','ls_cost_proxy_30bp','ls_cost_proxy_50bp','long_only_excess_cost_proxy_10bp','long_only_excess_cost_proxy_25bp','long_only_excess_cost_proxy_30bp','long_only_excess_cost_proxy_50bp']}
  summaries.append({'candidate':cid,'label':label,'first_target':x.index.min(),'last_target':x.index.max(),'metrics':metrics,'bins':cfg[cid]['bins'],'monthly_hac_lag':cfg[cid]['monthly_hac_lag'],'mean_two_leg_turnover_proxy':x.two_leg_target_turnover_proxy.mean(),'mean_average_leg_turnover_proxy':x.two_leg_target_turnover_proxy.mean()/2,'annualized_average_leg_turnover_proxy':x.two_leg_target_turnover_proxy.mean()*6,'break_even_cost_proxy':x.spread_conditional.mean()/x.two_leg_target_turnover_proxy.mean(),'mean_top_missing_weight':x.top_missing_weight.mean(),'max_top_missing_weight':x.top_missing_weight.max(),'mean_bottom_missing_weight':x.bottom_missing_weight.mean(),'mean_pool_missing_weight':x.pool_missing_weight.mean(),'top_group_all_returns_complete_months':int(x.long_only_full_portfolio_return.notna().sum()),'mean_signals':x.signal_n.mean(),'mean_available_labels':x.label_n.mean()})
  for year,z in x.groupby(x.index.str[:4]):annual.append({'candidate':cid,'label':label,'year':year,'months':len(z),'spread_conditional':z.spread_conditional.mean(),'rank_ic':z.rank_ic.mean(),'long_only_excess_conditional':z.long_only_excess_conditional.mean(),'mean_top_missing_weight':z.top_missing_weight.mean()})
 blocks=[]
 for label,v in d[d.mature].groupby('label'):
  common=set.intersection(*[set(q.target_month) for _,q in v.groupby('candidate')])
  for cid,q in v.groupby('candidate'):
   for name,mask in [('2020-2023',q.target_month.between('2020-01','2023-12')),('2024-2025',q.target_month.between('2024-01','2025-12')),('2026',q.target_month.between('2026-01','2026-12')),('matched_candidate_months',q.target_month.isin(common))]:
    z=q[mask]
    if len(z):blocks.append({'candidate':cid,'label':label,'block':name,'months':len(z),'spread_conditional':z.spread_conditional.mean(),'rank_ic':z.rank_ic.mean(),'long_only_excess_conditional':z.long_only_excess_conditional.mean(),'mean_top_missing_weight':z.top_missing_weight.mean()})
 pd.DataFrame(blocks).to_csv(O/'subperiod-diagnostics.csv',index=False)
 primary=[s for s in summaries if s['label']=='label_close'];assert len(primary)==2
 ps=holm([s['metrics']['spread_conditional']['one_sided_p'] for s in primary]);rs=holm([s['metrics']['rank_ic']['one_sided_p'] for s in primary])
 for s,p,r in zip(primary,ps,rs):
  m=s['metrics']['spread_conditional'];s['primary_holm2_p']=p;s['secondary_rankic_holm2_p']=r;s['gates']={'at_least24months':m['n']>=24,'positive_mean':m['mean']>0,'positive_hac95_lower':m['ci95'][0]>0,'holm2_p':p<=.05};s['adapted_retrospective_association_supported']=all(s['gates'].values());s['original_universe_replication']=False;s['tradability_certified']=False
 result={'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'protocol_sha256':hashlib.sha256((P/'protocol.json').read_bytes()).hexdigest(),'all_results':summaries,'primary_family_size':2,'selected_variants':None,'native_model_trials':0,'prior_history_exposed':True,'conditional_return_not_complete_portfolio':True,'new_hypotheses_or_sign_changes':False}
 (O/'summary.json').write_text(json.dumps(clean(result),ensure_ascii=False,indent=2,allow_nan=False));pd.DataFrame(annual).to_csv(O/'annual-diagnostics.csv',index=False)
 print(json.dumps(clean([{'candidate':s['candidate'],'mean':s['metrics']['spread_conditional']['mean'],'ci95':s['metrics']['spread_conditional']['ci95'],'p_holm2':s['primary_holm2_p'],'supported':s['adapted_retrospective_association_supported']} for s in primary]),ensure_ascii=False),flush=True)
if __name__=='__main__':main()
