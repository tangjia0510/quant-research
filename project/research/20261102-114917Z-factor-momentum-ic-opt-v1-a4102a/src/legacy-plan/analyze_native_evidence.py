from pathlib import Path
import json
import pandas as pd,numpy as np
from analyze_supplementary import hac,clean
P=Path(__file__).resolve().parents[1];O=P/'outputs';root=Path(json.loads((O/'native-study.json').read_text())['workspace']);summary=[]
for cid in ['momentum20-reference','reversal20']:
 r=root/'runs/discovery'/cid/'attempt-1';mfile=r/'metrics.json'
 if not mfile.exists():continue
 m=json.loads(mfile.read_text());a=pd.read_csv(r/'daily-ic.csv').set_index('date');b=pd.read_csv(r/'baseline/daily-ic.csv').set_index('date');paired=a[['rank_ic']].join(b[['rank_ic']],lsuffix='_candidate',rsuffix='_baseline',how='inner').dropna();unc=hac(paired.rank_ic_candidate-paired.rank_ic_baseline,10);portfolios={}
 for label,file in [('candidate',r/'portfolio.csv'),('baseline',r/'baseline/portfolio.csv'),('equal_weight',r/'equal-weight.csv')]:
  f=pd.read_csv(file);exposure=f.value/f.account;orders=pd.read_csv(file.with_name(file.stem+'-orders.csv'))
  portfolios[label]={'days':len(f),'net_total_return_recomputed':float(np.prod(1+f['return']-f.cost)-1),'gross_total_return_recomputed':float(np.prod(1+f['return'])-1),'terminal_account':f.account.iloc[-1],'terminal_cash':f.cash.iloc[-1],'terminal_stock_value':f.value.iloc[-1],'mean_stock_exposure':exposure.mean(),'min_stock_exposure':exposure.min(),'max_stock_exposure':exposure.max(),'near_cash_days_below_1pct_stock':int((exposure<.01).sum()),'total_nominal_cost':f.total_cost.iloc[-1],'requested_orders':len(orders),'requested_unique_instruments':orders.instrument.nunique(),'requested_buys_max_on_day':int(orders[orders.direction==1].groupby('trade_date').size().max()) if (orders.direction==1).any() else 0,'holdings_count':'not saved by native artifact; order counts are not holdings or fills','weight_and_lot_note':'top10 target 95%, 100 raw-share units; price/lot/cash constraints affect realized exposures; requested orders not executed fill log'}
  assert np.allclose(f.account,100000*np.cumprod(1+f['return']-f.cost),rtol=1e-6),label
  assert np.allclose(f.account,f.value+f.cash,rtol=1e-6),label
 decision={'paired_rankic_hac10_ci_lower_positive':unc['ci95'][0]>0,'annualized_net_difference_nonnegative':m['increment']['annualized_net_return_difference']>=0};summary.append({'candidate':cid,'native_prediction_signal':m['signal'],'native_increment_lag5_preserved':m['increment'],'prespecified_hac_lag10_increment':unc,'native_model_admission_gates':decision,'native_model_admitted':all(decision.values()),'portfolio_audit':portfolios})
(O/'native-evidence-summary.json').write_text(json.dumps(clean(summary),ensure_ascii=False,indent=2,allow_nan=False));print(json.dumps(clean(summary),ensure_ascii=False))
