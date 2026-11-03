import unittest,numpy as np,pandas as pd
from formulas import illiq20,seas_scores
class FormulaTests(unittest.TestCase):
 def test_illiq_manual_units_prefix(self):
  p=pd.Series(10*np.exp(np.arange(50)*.01));v=pd.Series(1000.,index=p.index);x=illiq20(p,p,v)
  expected=np.mean(np.abs(p.iloc[1:21].to_numpy()/p.iloc[:20].to_numpy()-1)/(p.iloc[1:21].to_numpy()*1000))
  self.assertAlmostEqual(x.iloc[20],expected);self.assertTrue(x.iloc[:20].isna().all())
  np.testing.assert_allclose(illiq20(p,p,v*100),x/100,equal_nan=True)
  q=p.copy();q.iloc[35:]*=4;np.testing.assert_allclose(illiq20(q,q,v).iloc[:35],x.iloc[:35],equal_nan=True)
 def test_missing_zero_no_compression(self):
  p=pd.Series(np.arange(60)+10.);v=pd.Series(1000.,index=p.index);p.iloc[25]=np.nan;x=illiq20(p,p,v)
  self.assertTrue(x.iloc[25:46].isna().all());self.assertTrue(np.isfinite(x.iloc[46]));v.iloc[49]=0;self.assertTrue(np.isnan(illiq20(p,p,v).iloc[49]))
 def frame(self):
  rows=[]
  for i,sign in [('sh000001',1),('sz000001',-1)]:
   for m in range(94):rows.append({'instrument':i,'month':m,'month_return':np.nan if m==0 else sign*(m+1)/1000,'current_eligible':True,'seas_history_eligible':m>=60})
  return pd.DataFrame(rows)
 def test_seas_january_boundary_and_manual(self):
  f=seas_scores(self.frame());g=f[f.instrument=='sh000001'].reset_index(drop=True)
  self.assertTrue(np.isnan(g.seas.iloc[59]));self.assertEqual(g.seas_history_n.iloc[59],4)
  self.assertAlmostEqual(g.seas.iloc[60],np.mean([(m+1)/1000 for m in [49,37,25,13,1]]));self.assertEqual(g.seas_history_n.iloc[60],5)
 def test_future_and_historical_pool(self):
  f=self.frame();a=seas_scores(f);f.loc[f.month>=70,'month_return']*=10;b=seas_scores(f)
  np.testing.assert_allclose(a.loc[a.month<70,'seas'],b.loc[b.month<70,'seas'],equal_nan=True)
  self.assertAlmostEqual(a.loc[(a.instrument=='sh000001')&(a.month==60),'seas'].iloc[0],-a.loc[(a.instrument=='sz000001')&(a.month==60),'seas'].iloc[0])
 def test_missing_month_failclosed(self):
  f=self.frame();f=f[~((f.instrument=='sh000001')&(f.month==30))]
  with self.assertRaises(AssertionError):seas_scores(f)
if __name__=='__main__':unittest.main()
