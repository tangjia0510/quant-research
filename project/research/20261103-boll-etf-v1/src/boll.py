"""Causal BOLL signals and audited-style ETF cash/share/receivable ledger."""
import math
import numpy as np
import pandas as pd

def indicators(bars,dividends):
    cash=dividends.groupby('ex_date').cash_per_unit.sum().to_dict(); tr=[];prev=None;level=100.
    for d,r in bars.iterrows():
        if prev is not None:level*=(r.close+cash.get(d,0.))/prev
        tr.append(level);prev=r.close
    out=pd.DataFrame({'tr':tr},index=bars.index)
    out['middle']=out.tr.rolling(20,min_periods=20).mean()
    out['std']=out.tr.rolling(20,min_periods=20).std(ddof=0)
    out['upper']=out.middle+2*out['std'];out['lower']=out.middle-2*out['std']
    width=out.upper-out.lower
    out['percent_b']=(out.tr-out.lower)/width.where(width>0)
    out['bandwidth']=width/out.middle
    return out

def targets(ind):
    """Target states know only each day's completed close. Exit has state priority."""
    out=ind.copy();previous_b=np.nan; states={'boll_breakout':0,'boll_reentry':0}; cols={k:[] for k in states}
    for d,r in ind.iterrows():
        valid=np.isfinite(r.percent_b)
        for kind,state in states.items():
            if valid:
                if state:
                    if (kind=='boll_breakout' and r.tr<r.middle) or (kind=='boll_reentry' and r.tr>=r.middle):state=0
                elif np.isfinite(previous_b):
                    if kind=='boll_breakout' and previous_b<=1 and r.percent_b>1:state=1
                    elif kind=='boll_reentry' and previous_b<0 and 0<=r.percent_b<.5:state=1
            states[kind]=state;cols[kind].append(state)
        previous_b=r.percent_b
    for k,v in cols.items():out[k]=v
    out['ready']=np.isfinite(out.percent_b)
    return out

def block_reason(open_price,previous_close,ex_cash,tick=.001):
    if not np.isfinite(open_price) or open_price<=0:return 'invalid_open'
    ref=previous_close-ex_cash
    if open_price>=ref*1.10-tick:return 'conservative_upper_boundary'
    if open_price<=ref*.90+tick:return 'conservative_lower_boundary'
    return None

def simulate(bars,dividends,sig,kind,total_bp=10,start='2019-01-01'):
    assert kind in ['boll_breakout','boll_reentry','benchmark']
    commission=slip=total_bp/20000.;cash=100000.;shares=0;target=0;pending=False;signal_date=None
    claims={};entitlements={};trades=[];daily=[];blocked=[];last_buy=None;previous=None
    ex=dividends.groupby('ex_date').cash_per_unit.sum().to_dict();events=dividends.to_dict('records')
    # Month-end from global exchange dates, not volume or outcome filtering.
    month_ends=set(pd.Series(bars.index,index=bars.index).groupby(pd.to_datetime(bars.index).to_period('M')).last())
    for d,r in bars.iterrows():
        if d<start:
            if kind!='benchmark' and bool(sig.loc[d,'ready']):target=int(sig.loc[d,kind]);signal_date=d
            previous=r.close;continue
        if not daily:
            if kind=='benchmark':target=1;signal_date='initial_allocation'
            pending=True
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
        # Orders are created after today's equity mark, never use future high/low/volume.
        desired=1 if kind=='benchmark' else (int(sig.loc[d,kind]) if bool(sig.loc[d,'ready']) else target)
        if desired!=target or d in month_ends:
            target=desired;signal_date=d;pending=True
        previous=r.close
    return pd.DataFrame(daily),pd.DataFrame(trades,columns=['date','signal_date','side','units','raw_open','fill_price','commission','slippage_cost','notional','cash_after','units_after']),pd.DataFrame(blocked,columns=['date','signal_date','target','reason'])
