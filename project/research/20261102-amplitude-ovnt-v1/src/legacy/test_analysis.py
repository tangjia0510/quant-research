import unittest,numpy as np,pandas as pd
from analyze import monthly_hac,group_stats,holm,turnover
class AnalysisTests(unittest.TestCase):
 def test_calendar_hac(self):
  x=np.array([.01,.02,np.nan,-.04,.03,.01]);s=pd.Series(x,index=pd.period_range('2020-01',periods=6,freq='M'));r=monthly_hac(s,3);n=5;mu=np.nanmean(x);u=np.where(np.isfinite(x),x-mu,0.);v=sum(u*u)+sum(2*(1-k/4)*np.dot(u[k:],u[:-k]) for k in [1,2,3]);self.assertAlmostEqual(r['se'],np.sqrt(max(0,v))/n);self.assertEqual(r['calendar_months'],6);self.assertEqual(r['missing_months'],1)
 def test_inf_rejected(self):
  with self.assertRaises(AssertionError):monthly_hac(pd.Series([.1,np.inf],index=pd.period_range('2020-01',periods=2,freq='M')))
 def test_missing_weights(self):
  f=pd.DataFrame({'label_close':[.1,np.nan,-.2],'close_mature':[True]*3});r=group_stats(f,'label_close');self.assertAlmostEqual(r['conditional_mean'],-.05);self.assertAlmostEqual(r['full_weight_known_contribution'],-.1/3);self.assertAlmostEqual(r['missing_weight'],1/3);self.assertTrue(np.isnan(r['full_portfolio_return']));self.assertAlmostEqual(r['long_only_lower_bound'],-1.1/3)
 def test_turnover_holm(self):
  self.assertEqual(turnover({'a':1},{'b':1}),2);self.assertEqual(turnover({'a':1},{}),1);np.testing.assert_allclose(holm([.01,.04]),[.02,.04])
if __name__=='__main__':unittest.main()
