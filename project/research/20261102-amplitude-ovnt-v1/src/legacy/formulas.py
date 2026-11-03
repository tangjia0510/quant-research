import numpy as np,pandas as pd

def amplitude_window(high,low,close):
 h,l,c=map(lambda x:np.asarray(x,dtype=float),(high,low,close));assert len(h)==len(l)==len(c)==20
 good=np.isfinite(h)&np.isfinite(l)&np.isfinite(c)&(h>l)&(l>0)&(c>=l)&(c<=h)
 n=int(good.sum());k=max(1,int(np.floor(n*.25)))
 if n<10:return {'score':np.nan,'high_amp':np.nan,'low_amp':np.nan,'valid_days':n,'k':k}
 a=h[good]/l[good]-1;c=c[good];order=np.argsort(c,kind='stable');vh=float(a[order[-k:]].mean());vl=float(a[order[:k]].mean())
 return {'score':-(vh-vl),'high_amp':vh,'low_amp':vl,'valid_days':n,'k':k}

def overnight_daily(adj_open,adj_close):
 o,c=np.asarray(adj_open,dtype=float),np.asarray(adj_close,dtype=float);prev=np.r_[np.nan,c[:-1]];good=np.isfinite(o)&np.isfinite(prev)&(o>0)&(prev>0)
 return np.divide(o,prev,out=np.full(len(o),np.nan),where=good)-1

def full_month_overnight(returns,expected_days):
 x=np.asarray(returns,dtype=float)
 if len(x)!=expected_days or not np.isfinite(x).all() or (x<=-1).any():return np.nan
 r=float(np.prod(1+x)-1);assert np.isfinite(r);return r

def ovnt_scores(frame):
 f=frame.sort_values(['instrument','month']).copy();assert not f.duplicated(['instrument','month']).any()
 for _,g in f.groupby('instrument',sort=False):assert np.all(np.diff(g.month)==1),'Preserve missing calendar months'
 groups=f.overnight_month.groupby(f.instrument,sort=False);prod=pd.Series(1.,index=f.index);count=pd.Series(0,index=f.index,dtype=int)
 for lag in range(1,12):
  v=groups.shift(lag);prod*=1+v;count+=v.notna().astype(int)
 f['ovnt_input_months']=count;f['ovnt12']=((prod-1)/11).where(count.eq(11))
 g=f.month_return.groupby(f.instrument,sort=False);f['last3_months_zero']=f.month_return.eq(0)&g.shift(1).eq(0)&g.shift(2).eq(0)
 return f
