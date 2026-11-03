import numpy as np,pandas as pd

def illiq20(adjusted_close,raw_close,volume_shares):
    valid=np.isfinite(adjusted_close)&np.isfinite(raw_close)&np.isfinite(volume_shares)&(adjusted_close>0)&(raw_close>0)&(volume_shares>0)
    p=adjusted_close.where(valid)
    r=p/p.shift(1)-1
    return (r.abs()/(raw_close*volume_shares).where(valid)).rolling(20,min_periods=20).mean()

def seas_scores(frame):
    # Frame must contain every calendar month per instrument, including missing observations.
    f=frame.sort_values(['instrument','month']).copy()
    assert not f.duplicated(['instrument','month']).any()
    for _,g in f.groupby('instrument',sort=False):
        assert np.all(np.diff(g.month.to_numpy())==1),'Missing calendar rows must not compress lags'
    available=f.month_return.where(f.current_eligible)
    mean=available.groupby(f.month).transform('mean')
    f['historical_excess_month_return']=available-mean
    groups=f.historical_excess_month_return.groupby(f.instrument,sort=False)
    total=pd.Series(0.,index=f.index);count=pd.Series(0,index=f.index,dtype='int64')
    for lag in range(11,240,12):
        x=groups.shift(lag);total+=x.fillna(0);count+=x.notna().astype(int)
    f['seas_history_n']=count
    f['seas']= (total/count.where(count>0)).where((count>=5)&f.seas_history_eligible&f.current_eligible)
    return f
