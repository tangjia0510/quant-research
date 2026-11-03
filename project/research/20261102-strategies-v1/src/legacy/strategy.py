"""Prespecified single-ETF, cash/share/receivable accounting. No downloaded code."""
import math
import numpy as np
import pandas as pd

def signals(bars,dividends):
    cash=dividends.groupby('ex_date').cash_per_unit.sum().to_dict()
    tr=[];previous=None;level=100.
    for d,r in bars.iterrows():
        if previous is not None:level*= (r.close+cash.get(d,0.))/previous
        tr.append(level);previous=r.close
    series=pd.Series(tr,index=bars.index,name='total_return_index')
    last=series.groupby(pd.to_datetime(series.index).to_period('M')).tail(1)
    sma=last.rolling(10,min_periods=10).mean();target=0;out=[]
    for d,v in last.items():
        if pd.notna(sma[d]):
            if v>sma[d]:target=1
            elif v<sma[d]:target=0
        out.append(dict(signal_date=d,tr=v,sma10=sma[d],target=target,ready=bool(pd.notna(sma[d]))))
    return pd.DataFrame(out),series

def block_reason(open_price,previous_close,ex_cash,tick=.001):
    if not np.isfinite(open_price) or open_price<=0:return 'invalid_open'
    ref=previous_close-ex_cash
    if open_price>=ref*1.10-tick:return 'conservative_upper_boundary'
    if open_price<=ref*.90+tick:return 'conservative_lower_boundary'
    return None

def simulate(bars,dividends,monthly,kind='strategy',total_bp=10,start='2019-01-01'):
    commission=slip=total_bp/20000.;cash=100000.;shares=0;pending=False;target=0;signal_date=None;claims={};entitlements={};trades=[];daily=[];blocked=[];last_buy=None
    sig=monthly.set_index('signal_date').to_dict('index')
    ex=dividends.groupby('ex_date').cash_per_unit.sum().to_dict();events=dividends.to_dict('records');previous=None
    for d,r in bars.iterrows():
        if d<start:
            if d in sig and sig[d]['ready']:target=sig[d]['target'];signal_date=d
            previous=r.close;continue
        if not daily:
            if kind=='benchmark':target=1;signal_date='initial_allocation'
            pending=True
        # Registration-date shares become an ex-date receivable, not spendable cash.
        for i,e in enumerate(events):
            if e['ex_date']==d:claims[i]=entitlements.get(i,0)*e['cash_per_unit']
        paid=0.
        for i in list(claims):
            if events[i]['pay_date']<=d:paid+=claims.pop(i)
        cash+=paid
        if pending:
            reason=block_reason(r.open,previous,ex.get(d,0.))
            if reason:blocked.append(dict(date=d,signal_date=signal_date,target=target,reason=reason))
            else:
                qty=0;side=None;px=0.
                if target==0 and shares and last_buy!=d:qty=shares;side='sell';px=r.open*(1-slip)
                elif target==1:
                    px=r.open*(1+slip);qty=int(math.floor((cash+1e-10)/(100*px*(1+commission))))*100
                    if qty:side='buy'
                if qty:
                    fee=qty*px*commission
                    if side=='buy':cash-=qty*px+fee;shares+=qty;last_buy=d
                    else:cash+=qty*px-fee;shares-=qty
                    trades.append(dict(date=d,signal_date=signal_date,side=side,units=qty,raw_open=r.open,fill_price=px,commission=fee,slippage_cost=qty*abs(px-r.open),notional=qty*px,cash_after=cash,units_after=shares))
                pending=False
        assert cash>=-1e-7 and shares>=0 and shares%100==0
        for i,e in enumerate(events):
            if e['record_date']==d:entitlements[i]=shares
        receivable=sum(claims.values());equity=cash+shares*r.close+receivable
        daily.append(dict(date=d,cash=cash,units=shares,close=r.close,receivable=receivable,dividend_cash_paid=paid,equity=equity,exposure=shares*r.close/equity,pending=pending,target=target))
        # Only after this close can the month's signal create tomorrow's order.
        if d in sig and sig[d]['ready']:
            target=1 if kind=='benchmark' else sig[d]['target'];signal_date=d;pending=True
        previous=r.close
    return pd.DataFrame(daily),pd.DataFrame(trades,columns=['date','signal_date','side','units','raw_open','fill_price','commission','slippage_cost','notional','cash_after','units_after']),pd.DataFrame(blocked,columns=['date','signal_date','target','reason'])
