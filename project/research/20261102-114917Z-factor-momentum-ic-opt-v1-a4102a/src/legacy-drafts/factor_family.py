import numpy as np
import pandas as pd

def all_factors(frame):
    g=frame.groupby(level='instrument',sort=False)
    r5=g.close.transform(lambda s:s/s.shift(5)-1)
    r20=g.close.transform(lambda s:s/s.shift(20)-1)
    skip=g.close.transform(lambda s:s.shift(5)/s.shift(60)-1)
    vol=g.close.transform(lambda s:s.pct_change(fill_method=None).rolling(20,min_periods=20).std(ddof=0))
    v5=g.volume.transform(lambda s:s.rolling(5,min_periods=5).mean())
    v20=g.volume.transform(lambda s:s.rolling(20,min_periods=20).mean())
    ratio=(v5/v20.replace(0,np.nan)).clip(.25,4)
    return pd.DataFrame({'momentum20-reference':r20,'reversal5':-r5,'reversal20':-r20,'momentum60-skip5':skip,'reversal5-risk-adjusted':-r5/vol.replace(0,np.nan),'reversal5-volume-confirmed':-r5*ratio},index=frame.index)

def compute(frame,params):
    name=params['candidate_id']
    result=all_factors(frame)[name]
    return result.rename('x_'+name.replace('-','_')).to_frame()
