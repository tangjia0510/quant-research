from pathlib import Path
import pandas as pd,json
R=Path(__file__).resolve().parents[1];O=R/'outputs'
d=pd.read_csv(O/'strategy-10bp-daily.csv').set_index('date');t=pd.read_csv(O/'strategy-10bp-trades.csv');periods=[];current=None
for x in t.to_dict('records'):
 if x['side']=='buy' and current is None:
  current=dict(entry=x['date'],entry_signal=x['signal_date'],start_cash=x['cash_after']+x['notional']+x['commission'],buy_orders=0)
 if x['side']=='buy':current['buy_orders']+=1
 else:
  current.update(exit=x['date'],exit_signal=x['signal_date'],end_cash=x['cash_after'],cycle_account_return=x['cash_after']/current['start_cash']-1)
  h=d.loc[current['entry']:current['exit']];current['calendar_days']=(pd.Timestamp(current['exit'])-pd.Timestamp(current['entry'])).days;current['invested_sessions']=int((h.units>0).sum());current['dividends_received']=float(h.dividend_cash_paid.sum());periods.append(current);current=None
assert current is None,'terminal open cycle needs explicit marked treatment'
pd.DataFrame(periods).to_csv(O/'holding-cycles-10bp.csv',index=False)
segs=[]
for k in ['strategy','benchmark']:
 f=pd.read_csv(O/f'{k}-10bp-daily.csv').set_index('date')
 for a,b in [('2019-01-01','2024-12-31'),('2025-01-01','2026-10-30')]:
  before=f[f.index<a].equity.iloc[-1] if len(f[f.index<a]) else 100000.;h=f.loc[a:b];segs.append(dict(kind=k,start=a,end=b,starting_equity=before,ending_equity=h.equity.iloc[-1],net_return=h.equity.iloc[-1]/before-1))
pd.DataFrame(segs).to_csv(O/'predeclared-segments.csv',index=False)
notes={'local_blocked_log_semantics':'Blocked entries are local pending allocation-check deferrals, not actual submitted/exchange-rejected orders. In always-long benchmark a no-cash/no-change monthly allocation can also be logged blocked before zero desired buy is determined; this has no portfolio effect. Do not interpret as one real failed exchange order.','primary_strategy_block':'2024-10-08 open at conservative upper10% threshold;pending buy executed2024-10-09;fixed rule retained after results.','holding_cycle_return':'End cash/start cash per completed invested episode, includes internally credited dividends and trading costs; not incremental factor alpha.','future_unseen':'No independent unseen historical segment claimed.'}
(O/'interpretation-notes.json').write_text(json.dumps(notes,indent=2));print(pd.DataFrame(periods).to_string(index=False))
