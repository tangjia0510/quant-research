#!/usr/bin/env python3
"""Rebuild frozen inputs then evaluate fixed BOLL rules; writes only work/<id>."""
import argparse,datetime,hashlib,importlib.util,json,math,sys
from pathlib import Path
import numpy as np,pandas as pd
from boll import indicators,targets,simulate
from rebuild_inputs import rebuild
ID='20261103-boll-etf-v1'
PROTOCOL_SHA='048ceb889b5f046cf5cde6aa4ec2d94763323334c7d29a59724bc7eb403ddf88'

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def hac(x,lag=3):
 x=np.asarray(x,float);assert len(x)>lag and np.isfinite(x).all();n=len(x);mu=x.mean();u=x-mu;v=u@u
 for k in range(1,min(lag,n-1)+1):v+=2*(1-k/(lag+1))*(u[k:]@u[:-k])
 se=np.sqrt(max(v,0))/n;p=math.erfc(abs(mu/se)/math.sqrt(2)) if se>0 else (0. if mu else 1.)
 return dict(n=n,mean=float(mu),lag=lag,se=float(se),ci95=[float(mu-1.96*se),float(mu+1.96*se)],p_two_sided_normal=p)
def holm(ps):
 order=np.argsort(ps);out=np.zeros(len(ps));running=0
 for rank,i in enumerate(order):running=max(running,min(1.,(len(ps)-rank)*ps[i]));out[i]=running
 return out.tolist()
def metrics(d,t):
 eq=d.equity;ret=eq.pct_change(fill_method=None);ret.iloc[0]=eq.iloc[0]/100000-1;wealth=np.r_[100000,eq.to_numpy()];dd=wealth/np.maximum.accumulate(wealth)-1;dur=best=0
 for x in dd:dur=dur+1 if x<0 else 0;best=max(best,dur)
 years=((pd.Timestamp(d.date.iloc[-1])-pd.Timestamp('2019-01-01')).days+1)/365.25
 return dict(total_return=float(eq.iloc[-1]/100000-1),cagr=float((eq.iloc[-1]/100000)**(1/years)-1),annualized_volatility=float(ret.std(ddof=1)*np.sqrt(252)),sharpe_rf0=float(ret.mean()/ret.std(ddof=1)*np.sqrt(252)) if ret.std(ddof=1)>0 else None,max_drawdown=float(dd.min()),max_drawdown_duration_sessions=best,mean_exposure=float(d.exposure.mean()),trades=len(t),sum_traded_notional=float(t.notional.sum()) if len(t) else 0,turnover_notional_over_mean_equity=float(t.notional.sum()/eq.mean()) if len(t) else 0,commission=float(t.commission.sum()) if len(t) else 0,slippage_cost=float(t.slippage_cost.sum()) if len(t) else 0,final_equity=float(eq.iloc[-1]),calendar_years=years)
def main():
 a=argparse.ArgumentParser();a.add_argument('--project','--project-root',dest='project',type=Path,required=True);a.add_argument('--work-dir',type=Path);a.add_argument('--prepare-only',action='store_true');a.add_argument('--authorization',type=Path);args=a.parse_args();P=args.project.resolve();R=P/'research'/ID;O=args.work_dir.resolve() if args.work_dir else P/'work'/ID
 if not (P/'work').resolve().is_relative_to(P) or not O.resolve().is_relative_to((P/'work').resolve()):raise ValueError('Work directory must stay inside project/work')
 spec=importlib.util.spec_from_file_location('portable_project',((P.parent if json.loads((P/'project.json').read_text()).get('skill_source') == '..' else P/'skill')/'scripts/project.py'));project=importlib.util.module_from_spec(spec);spec.loader.exec_module(project)
 project.validate(P)
 assert sha(R/'protocol.json')==PROTOCOL_SHA,'Protocol drift; new amendment/research needed'
 meta=json.loads((R/'research.yaml').read_text())
 def resolve(root,id):return Path(project.resolve(root,id)['path'])
 O.mkdir(parents=True,exist_ok=True)
 if not args.prepare_only:
  if not args.authorization or not args.authorization.is_file():raise RuntimeError('Need explicit project/migration acceptance authorization file before evaluation')
  auth=json.loads(args.authorization.read_text());assert auth.get('research_id')==ID and auth.get('migration_accepted') is True and auth.get('protocol_sha256')==PROTOCOL_SHA
  # Re-runs keep previous evidence in separate work destination selected by explicit external archive; never overwrite results.
  if (O/'summary.json').exists():raise RuntimeError('Existing result: no silent overwrite')
 inputs=O/'inputs';bars,dividends=rebuild(P,resolve,inputs)
 assert np.isfinite(bars.to_numpy()).all() and (bars[['open','close','high','low']]>0).all().all();assert (bars.high>=bars[['open','close']].max(axis=1)).all() and (bars.low<=bars[['open','close']].min(axis=1)).all()
 assert (bars.volume_lots>0).all() and (bars.high>bars.low).all(),'Ex-post full-bar quality gate; no outcome-based execution filtering'
 for ev in dividends.to_dict('records'):
  assert ev['record_date']<ev['ex_date']<=ev['pay_date']
  if bars.index[0]<=ev['ex_date']<=bars.index[-1]:assert all(ev[k] in bars.index for k in ['record_date','ex_date','pay_date'])
 quality=dict(rows=len(bars),first=bars.index[0],last=bars.index[-1],no_missing_calendar=True,source_refs=meta['data_refs'],raw_rebuild_hash_match=True)
 (O/'data-quality.json').write_text(json.dumps(quality,indent=2)+'\n')
 if args.prepare_only:print(json.dumps(quality));return
 frozen=[dict(path=str(p.relative_to(P)),sha256=sha(p)) for p in sorted(R.rglob('*')) if p.is_file() and '__pycache__' not in p.parts]
 receipt=dict(started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),protocol_sha256=PROTOCOL_SHA,authorization_sha256=sha(args.authorization),research_files=frozen,input_sha256={p.name:sha(p) for p in inputs.iterdir() if p.is_file()},runtime=dict(python=sys.version,numpy=np.__version__,pandas=pd.__version__))
 (O/'execution-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
 sig=targets(indicators(bars,dividends));sig.to_csv(O/'daily-indicators-targets.csv');results=[];annual=[];monthly=[];curves={};active=[]
 for bp in [0,10,30]:
  m={}
  for kind in ['boll_breakout','boll_reentry','benchmark']:
   d,t,k=simulate(bars,dividends,sig,kind,bp);stem=f'{kind}-{bp}bp';d.to_csv(O/f'{stem}-daily.csv',index=False);t.to_csv(O/f'{stem}-trades.csv',index=False);k.to_csv(O/f'{stem}-blocked.csv',index=False)
   results.append(dict(kind=kind,total_friction_bp=bp,blocked_orders=len(k),**metrics(d,t)));di=d.set_index(pd.to_datetime(d.date));end=di.equity.resample('ME').last();mr=end.pct_change(fill_method=None);mr.iloc[0]=end.iloc[0]/100000-1;m[kind]=mr
   if bp==10:curves[kind]=di
   for dt,r in mr.items():monthly.append(dict(kind=kind,total_friction_bp=bp,month=str(dt.to_period('M')),return_net=float(r)))
   before=100000.
   for year,h in di.groupby(di.index.year):now=h.equity.iloc[-1];annual.append(dict(kind=kind,total_friction_bp=bp,year=int(year),return_net=float(now/before-1)));before=now
  for kind in ['boll_breakout','boll_reentry']:
   assert m[kind].index.equals(m['benchmark'].index);active.append(dict(kind=kind,total_friction_bp=bp,**hac(m[kind]-m['benchmark'])))
 for bp in [0,10,30]:
  rows=[x for x in active if x['total_friction_bp']==bp]
  for x,p in zip(rows,holm([x['p_two_sided_normal'] for x in rows])):x['holm_p_two_strategies']=p
 pd.DataFrame(annual).to_csv(O/'annual-returns.csv',index=False);pd.DataFrame(monthly).to_csv(O/'monthly-returns.csv',index=False)
 desc=sig[['percent_b','bandwidth']].copy();desc['forward5_tr_return']=sig.tr.shift(-5)/sig.tr-1;desc=desc.loc['2019-01-01':];valid=desc[['percent_b','forward5_tr_return']].dropna();diagnostic=dict(n=len(valid),pearson=float(valid.corr(method='pearson').iloc[0,1]),spearman=float(valid.corr(method='spearman').iloc[0,1]),label='Overlapping5-session close-total-return; descriptive single-ETF time-series association, not cross-sectional IC or executable return',terminal_missing_labels=int(desc.forward5_tr_return.isna().sum()),used_for_selection=False);desc.to_csv(O/'percent-b-descriptive-labels.csv')
 main_b=next(x for x in results if x['kind']=='benchmark' and x['total_friction_bp']==10);decisions=[]
 for kind in ['boll_breakout','boll_reentry']:
  s=next(x for x in results if x['kind']==kind and x['total_friction_bp']==10);ac=next(x for x in active if x['kind']==kind and x['total_friction_bp']==10)
  decisions.append(dict(kind=kind,net_outperformance_supported=bool(s['cagr']>main_b['cagr'] and ac['ci95'][0]>0 and ac['holm_p_two_strategies']<.05),drawdown_reduced=bool(s['max_drawdown']>main_b['max_drawdown']),registry_admitted=False,investable_certification=False))
 summary=dict(results=results,monthly_active=active,diagnostic=diagnostic,decisions=decisions,limitations=['SingleETF historical adaptation, no unseen future holdout','Original Bollinger screening is not a fully specified proven trading strategy; exits/account are local hypotheses','Incomplete historical orderbook/limits and dividend as-of chain','Cash interest0, fixed friction, open fill assumptions'])
 (O/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
 print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
