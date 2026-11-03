from pathlib import Path
import json,datetime,hashlib
import numpy as np,pandas as pd
from scipy import stats
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parents[1];A=ROOT/'artifacts';P=json.loads((ROOT/'protocol.json').read_text())
def save(n,o):(A/n).write_text(json.dumps(o,ensure_ascii=False,indent=2,default=str,allow_nan=False))
def nw(x,lag=5):
 x=np.asarray(x,dtype=float);x=x[np.isfinite(x)];n=len(x)
 if n<2:return {'n':n,'mean':None,'std':None,'hac_t':None,'hac_se':None}
 m=x.mean();u=x-m;long=np.dot(u,u)/n
 for k in range(1,min(lag,n-1)+1):long+=2*(1-k/(lag+1))*np.dot(u[k:],u[:-k])/n
 se=np.sqrt(max(long,0)/n)
 return {'n':n,'mean':float(m),'std':float(x.std(ddof=1)),'hac_t':float(m/se) if se else None,'hac_se':float(se)}
def main():
 df=pd.read_parquet(A/'signal-samples.parquet');df=df.sort_values(['date','instrument'])
 save('exposure-ledger.json',{'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'fixed_protocol_sha256':hashlib.sha256((ROOT/'protocol.json').read_bytes()).hexdigest(),'phases_about_to_be_read':list(P['splits']),'no_tuning_after_exposure':True,'final_not_available_as_untouched_holdout_for_future_research':True})
 rows=[];groups=[];counts=[];metrics={};wealth=[]
 for split,(lo,hi) in P['splits'].items():
  sig=df[df.date.between(lo,hi)].copy();eligible=sig.label_available & sig.label_exit_date.le(pd.Timestamp(hi));s=sig[eligible].copy()
  counts.append({'split':split,'signal_rows':len(sig),'outcome_missing_rows':int((~sig.label_available).sum()),'calendar_tail_censored_signal_rows':int(sig.label_exit_date.isna().sum()),'internal_outcome_quality_or_missing_rows':int((~sig.label_available & sig.label_exit_date.notna()).sum()),'cross_split_or_end_censored_rows':int((sig.label_available&~sig.label_exit_date.le(pd.Timestamp(hi))).sum()),'eligible_rows':len(s),'securities':s.instrument.nunique(),'snapshot_delisted_securities':s.loc[s.status_at_snapshot.eq('delisted'),'instrument'].nunique(),'eligible_rows_snapshot_delisted':int(s.status_at_snapshot.eq('delisted').sum()),'sources':s.source.value_counts().to_dict(),'signal_rows_snapshot_delisted':int(sig.status_at_snapshot.eq('delisted').sum()),'excluded_outcomes_snapshot_delisted':int((sig.status_at_snapshot.eq('delisted')&~eligible).sum())})
  daily=[];gr=[]
  for date,g in s.groupby('date',sort=True):
   if len(g)<P['min_cross_section'] or g.momentum20.nunique()<2:continue
   pear=float(g.momentum20.corr(g.forward5));rank=float(g.momentum20.corr(g.forward5,method='spearman'))
   daily.append({'date':date,'split':split,'n':len(g),'pearson_ic':pear,'rank_ic':rank,'equal_weight_forward5':float(g.forward5.mean())})
   # Deterministic tie order by instrument, not outcomes.
   q=np.minimum(((g.momentum20.rank(method='first')-1)*5/len(g)).astype(int)+1,5)
   for b in range(1,6):
    sub=g[q.eq(b)];gr.append({'date':date,'split':split,'quintile':b,'n':len(sub),'mean_forward5':float(sub.forward5.mean()),'mean_factor':float(sub.momentum20.mean()),'entry_date':sub.label_entry_date.iloc[0],'exit_date':sub.label_exit_date.iloc[0]})
  daily=pd.DataFrame(daily);gr=pd.DataFrame(gr);rows.append(daily);groups.append(gr)
  metrics[split]={'pearson_ic':nw(daily.pearson_ic),'rank_ic':nw(daily.rank_ic),'group_mean_forward5':gr.groupby('quintile').mean_forward5.mean().to_dict(),'rows':len(s),'securities':s.instrument.nunique(),'start':str(daily.date.min().date()),'end':str(daily.date.max().date())}
  wide=gr.pivot(index='date',columns='quintile',values='mean_forward5');metrics[split]['q5_minus_q1_forward5']=nw(wide[5]-wide[1])
  # Select by global calendar offset, never by every-fifth AVAILABLE date.
  calendar=pd.read_csv(ROOT.parents[2]/'a-share-data-lake/reference/normalized/trading-calendar-observed-2019-2026.txt',header=None)[0];calendar=pd.DatetimeIndex(pd.to_datetime(calendar));phase_dates=calendar[(calendar>=pd.Timestamp(lo))&(calendar<=pd.Timestamp(hi))][::5]
  for q in range(1,6):
   w=gr[(gr.quintile.eq(q))&gr.date.isin(phase_dates)].sort_values('date').copy();w['diagnostic_wealth']=(1+w.mean_forward5).cumprod();wealth.append(w)
   metrics[split].setdefault('nonoverlap_phase0',{})[str(q)]={'periods':len(w),'terminal_gross_diagnostic_return':float(w.diagnostic_wealth.iloc[-1]-1) if len(w) else None,'missing_phase_dates':len(phase_dates)-len(w)}
 daily=pd.concat(rows,ignore_index=True);gr=pd.concat(groups,ignore_index=True);w=pd.concat(wealth,ignore_index=True)
 daily.to_csv(A/'daily-ic.csv',index=False);gr.to_csv(A/'daily-quintile-forward-returns.csv',index=False);w.to_csv(A/'nonoverlap-diagnostic-wealth.csv',index=False)
 save('split-coverage.json',counts);save('metrics.json',metrics)
 plt.style.use('seaborn-v0_8-whitegrid')
 fig,ax=plt.subplots(2,2,figsize=(13,8),layout='constrained')
 for i,split in enumerate(['discovery','final']):
  ds=daily[daily.split.eq(split)];ax[0,i].plot(ds.date,ds.rank_ic.rolling(20).mean(),label='Rank IC 20-session mean');ax[0,i].plot(ds.date,ds.pearson_ic.rolling(20).mean(),alpha=.7,label='Pearson IC 20-session mean');ax[0,i].axhline(0,color='gray',lw=.8);ax[0,i].set_title(split+' | fixed momentum20');ax[0,i].legend(fontsize=8)
  m=metrics[split]['group_mean_forward5'];ax[1,i].bar([str(x) for x in m],[v*100 for v in m.values()],color='#326bb1');ax[1,i].set_title('Mean overlapping 5-session forward return (%)');ax[1,i].set_xlabel('Quintile 1 low momentum → 5 high momentum')
 fig.suptitle('Price-volume diagnostic | not an executable strategy',fontsize=14);fig.savefig(A/'factor-diagnostic.png',dpi=160);plt.close(fig)
 cov=pd.read_csv(A/'daily-quality-coverage.csv',parse_dates=['date']);fig,ax=plt.subplots(figsize=(13,4),layout='constrained')
 for c in ['lifecycle','observed','bar_good','signal_eligible','signal_labeled']:ax.plot(cov.date,cov[c],label=c)
 ax.set_title('Coverage by date | frozen SH/SZ identifiers, retrospective source snapshot');ax.legend(ncol=3);fig.savefig(A/'coverage-diagnostic.png',dpi=160);plt.close(fig)
 save('evaluation-complete.json',{'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'fixed_trials':1,'full_qlib_simulation':False,'metrics':'diagnostic only','final_exposed':True})
 print(json.dumps(metrics,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
