from pathlib import Path
import pandas as pd,numpy as np,json,hashlib,datetime
from strategy import signals,simulate
R=Path(__file__).resolve().parents[1];S=R/'sources';O=R/'outputs'
def hac(x,lag=3):
 x=np.asarray(x,float);assert np.isfinite(x).all();n=len(x);mu=x.mean();u=x-mu;v=u@u
 for k in range(1,min(lag,n-1)+1):v+=2*(1-k/(lag+1))*(u[k:]@u[:-k])
 se=np.sqrt(max(v,0))/n
 return dict(n=n,mean=mu,lag=lag,se=se,ci95=[mu-1.96*se,mu+1.96*se])
def metrics(d,t):
 eq=d.equity;ret=eq.pct_change(fill_method=None);ret.iloc[0]=eq.iloc[0]/100000-1
 wealth=np.r_[100000,eq.to_numpy()];dd=wealth/np.maximum.accumulate(wealth)-1
 dur=best=0
 for x in dd:dur=dur+1 if x<0 else 0;best=max(best,dur)
 years=((pd.Timestamp(d.date.iloc[-1])-pd.Timestamp('2019-01-01')).days+1)/365.25
 return dict(total_return=eq.iloc[-1]/100000-1,cagr=(eq.iloc[-1]/100000)**(1/years)-1,annualized_volatility=ret.std(ddof=1)*np.sqrt(252),sharpe_rf0=(ret.mean()/ret.std(ddof=1)*np.sqrt(252) if ret.std(ddof=1)>0 else None),max_drawdown=dd.min(),max_drawdown_duration_sessions=best,mean_exposure=d.exposure.mean(),trades=len(t),sum_traded_notional=t.notional.sum() if len(t) else 0,turnover_notional_over_mean_equity=t.notional.sum()/eq.mean() if len(t) else 0,commission=t.commission.sum() if len(t) else 0,slippage_cost=t.slippage_cost.sum() if len(t) else 0,final_equity=eq.iloc[-1],calendar_years=years)
def main():
 frozen=json.loads((O/'input-manifest-final.json').read_text())
 for x in frozen['files']:
  assert hashlib.sha256((R/x['path']).read_bytes()).hexdigest()==x['sha256'],x['path']
 assert hashlib.sha256((R/'protocol.json').read_bytes()).hexdigest()=='bc8e8b48f197bbbc098a5ee2a040907ca225571cdc15dd4acf2fa86338cc25e7'
 b=pd.read_csv(S/'510300-raw-normalized.csv',index_col='date');e=pd.read_csv(S/'510300-dividends.csv');assert (b.volume_lots>0).all() and (b.high>b.low).all(),'ex-post data quality fail, no backtest'
 for ev in e.to_dict('records'):
  assert ev['record_date']<ev['ex_date']<=ev['pay_date']
  if b.index[0]<=ev['ex_date']<=b.index[-1]:
   assert all(ev[k] in b.index for k in ['record_date','ex_date','pay_date'])
 sig,tr=signals(b,e);sig.to_csv(O/'monthly-signals.csv',index=False);tr.to_csv(O/'signal-total-return-index.csv');res=[];annual=[];monthly=[]
 for bp in [0,10,30]:
  m={}
  for kind in ['strategy','benchmark']:
   d,t,k=simulate(b,e,sig,kind,bp);stem=f'{kind}-{bp}bp';d.to_csv(O/f'{stem}-daily.csv',index=False);t.to_csv(O/f'{stem}-trades.csv',index=False);k.to_csv(O/f'{stem}-blocked.csv',index=False)
   v=metrics(d,t);res.append(dict(kind=kind,total_friction_bp=bp,blocked_orders=len(k),**v));di=d.set_index(pd.to_datetime(d.date));end=di.equity.resample('ME').last();mr=end.pct_change(fill_method=None);mr.iloc[0]=end.iloc[0]/100000-1;m[kind]=mr
   for dt,r in mr.items():monthly.append(dict(kind=kind,total_friction_bp=bp,month=str(dt.to_period('M')),return_net=r))
   before=100000.
   for year,h in di.groupby(di.index.year):
    now=h.equity.iloc[-1];annual.append(dict(kind=kind,total_friction_bp=bp,year=int(year),return_net=now/before-1,first=h.date.iloc[0],last=h.date.iloc[-1]));before=now
  assert m['strategy'].index.equals(m['benchmark'].index);diff=m['strategy']-m['benchmark'];res.append(dict(kind='active_monthly_hac',total_friction_bp=bp,**hac(diff)))
 pd.DataFrame(annual).to_csv(O/'annual-returns.csv',index=False);pd.DataFrame(monthly).to_csv(O/'monthly-returns.csv',index=False)
 main_s=next(x for x in res if x['kind']=='strategy' and x['total_friction_bp']==10);main_b=next(x for x in res if x['kind']=='benchmark' and x['total_friction_bp']==10);active=next(x for x in res if x['kind']=='active_monthly_hac' and x['total_friction_bp']==10)
 out=dict(results=res,decision=dict(net_outperformance_supported=bool(main_s['cagr']>main_b['cagr'] and active['ci95'][0]>0),drawdown_reduced=bool(main_s['max_drawdown']>main_b['max_drawdown']),investable_certification=False),limitations=['Conditional assumed open fills, incomplete historic order-book/limits','Historical adaptation,not independent future evidence','Original global strategy not A-share proof','Full older dividend announcement-asof chain unavailable'])
 (O/'summary.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
if __name__=='__main__':main()
