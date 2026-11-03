import unittest
import numpy as np,pandas as pd
from factor_family import compute

class FactorFamilyTests(unittest.TestCase):
 def setUp(self):
  rng=np.random.default_rng(17);idx=pd.MultiIndex.from_product([pd.bdate_range('2020-01-01',periods=110),['a','b','c']],names=['datetime','instrument']);n=len(idx);close=100*np.exp(rng.normal(0,.02,n).reshape(-1,3).cumsum(axis=0)).reshape(-1);self.f=pd.DataFrame({'close':close,'open':close*.995,'high':close*(1+rng.uniform(.002,.04,n)),'low':close*(1-rng.uniform(.002,.04,n)),'volume':rng.uniform(10000,800000,n),'factor':1.},index=idx);self.names=['low-downside-risk20','negative-return-volume-corr20','volume-weighted-close-location20']
 def test_future_and_scale(self):
  cutoff=self.f.index.get_level_values(0).unique()[70];prefix=self.f.loc[self.f.index.get_level_values(0)<=cutoff];alter=self.f.copy();alter.loc[alter.index.get_level_values(0)>cutoff,['close','high','low','volume']]*=3;scaled=self.f.copy();scale=scaled.index.get_level_values('instrument').map({'a':.3,'b':2.,'c':5.}).to_numpy();scaled[['open','high','low','close']]=scaled[['open','high','low','close']].mul(scale,axis=0);scaled.volume/=scale
  for name in self.names:
   a=compute(self.f,{'candidate_id':name});b=compute(alter,{'candidate_id':name});p=compute(prefix,{'candidate_id':name});c=compute(scaled,{'candidate_id':name});np.testing.assert_allclose(a.loc[p.index],p,rtol=1e-7,atol=1e-10,equal_nan=True);np.testing.assert_allclose(a.loc[p.index],b.loc[p.index],rtol=1e-7,atol=1e-10,equal_nan=True);np.testing.assert_allclose(a,c,rtol=1e-7,atol=1e-10,equal_nan=True)
 def test_declared_lookback(self):
  dates=self.f.index.get_level_values(0).unique()
  for name in self.names:
   look=20 if name=='volume-weighted-close-location20' else 21;a=compute(self.f,{'candidate_id':name});window=self.f.loc[self.f.index.get_level_values(0)>=dates[-look]];b=compute(window,{'candidate_id':name});np.testing.assert_allclose(a.loc[dates[-1]],b.loc[dates[-1]],rtol=1e-7,atol=1e-10,equal_nan=True)
 def test_flat_ranges_missing(self):
  f=self.f.copy();row=f.index[90];f.loc[row,['high','low']]=f.loc[row,'close'];z=compute(f,{'candidate_id':'volume-weighted-close-location20'});dates=f.index.get_level_values(0).unique();start=dates.get_loc(row[0]);self.assertTrue(z.loc[(slice(dates[start],dates[start+19]),row[1]),:].isna().all().all());self.assertTrue(z.loc[(dates[start+20],row[1])].notna().all())
 def test_zero_volume_and_constant_series(self):
  f=self.f.copy();f.loc[(slice(None),'a'),'volume']=100.;z=compute(f,{'candidate_id':'negative-return-volume-corr20'});self.assertTrue(z.x_negative_return_volume_corr20.xs('a',level='instrument').isna().all());f=self.f.copy();f.loc[(slice(None),'a'),'close']=100.;z=compute(f,{'candidate_id':'low-downside-risk20'});self.assertTrue((z.x_low_downside_risk20.xs('a',level='instrument').dropna()==0).all());f=self.f.copy();row=f.index[90];f.loc[row,'volume']=0;z=compute(f,{'candidate_id':'negative-return-volume-corr20'});dates=f.index.get_level_values(0).unique();i=dates.get_loc(row[0]);self.assertTrue(z.loc[(slice(dates[i],dates[i+20]),row[1]),:].isna().all().all())
 def test_missing_price_not_compressed(self):
  f=self.f.copy();dates=f.index.get_level_values(0).unique();f.loc[(dates[30],'a'),'close']=np.nan;z=compute(f,{'candidate_id':'low-downside-risk20'});self.assertTrue(z.loc[(slice(dates[30],dates[50]),'a'),:].isna().all().all());self.assertTrue(z.loc[(dates[51],'a')].notna().all())
 def test_constant_return_correlation_missing(self):
  f=self.f.copy();f.loc[(slice(None),'a'),'close']=100.;z=compute(f,{'candidate_id':'negative-return-volume-corr20'});self.assertTrue(z.x_negative_return_volume_corr20.xs('a',level='instrument').isna().all())
 def test_direct_formulas(self):
  f=self.f.xs('a',level='instrument',drop_level=False);r=f.close.pct_change(fill_method=None);v=np.log(f.volume).diff();expected=-r.rolling(20,min_periods=20).corr(v);a=compute(f,{'candidate_id':'negative-return-volume-corr20'});np.testing.assert_allclose(a.iloc[:,0],expected,rtol=1e-7,atol=1e-10,equal_nan=True)

if __name__=='__main__':unittest.main()
