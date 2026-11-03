import unittest
import numpy as np,pandas as pd
from factor_family import all_factors,compute
class Tests(unittest.TestCase):
 def frame(self):
  rng=np.random.default_rng(42);dates=pd.bdate_range('2020-01-01',periods=200);x=pd.MultiIndex.from_product([dates,['a','b','c']],names=['datetime','instrument']);c=np.exp(np.cumsum(rng.normal(0,.01,len(x))))*10
  return pd.DataFrame({'close':c,'open':c,'high':c*1.01,'low':c*.99,'volume':rng.uniform(1000,10000,len(x)),'factor':1.},index=x)
 def test_future(self):
  a=self.frame();base=all_factors(a);cut=a.index.get_level_values(0).unique()[120];b=a.copy();b.loc[b.index.get_level_values(0)>cut,['close','volume']]*=7;np.testing.assert_allclose(base.loc[:cut],all_factors(b).loc[:cut],equal_nan=True)
 def test_scale(self):
  a=self.frame();b=a.copy();b.close*=3;np.testing.assert_allclose(all_factors(a),all_factors(b),equal_nan=True,rtol=1e-7,atol=1e-9)
 def test_lookback(self):
  a=self.frame();base=all_factors(a);dates=a.index.get_level_values(0).unique()
  for n,k in [('momentum20-reference',21),('reversal5',6),('reversal20',21),('momentum60-skip5',61),('reversal5-risk-adjusted',21),('reversal5-volume-confirmed',20)]:
   b=a.loc[a.index.get_level_values(0)>=dates[-k]];np.testing.assert_allclose(base.loc[dates[-1],n],all_factors(b).loc[dates[-1],n],rtol=1e-7,atol=1e-9)
 def test_no_compressed_missing(self):
  a=self.frame();date=a.index.get_level_values(0).unique()[120];a.loc[(date,'a'),'close']=np.nan;r=all_factors(a);self.assertTrue(pd.isna(r.loc[(date,'a'),'reversal5']))
if __name__=='__main__':unittest.main()
