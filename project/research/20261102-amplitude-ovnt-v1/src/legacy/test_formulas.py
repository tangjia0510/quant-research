import unittest,numpy as np,pandas as pd
from formulas import amplitude_window,overnight_daily,full_month_overnight,ovnt_scores
class Tests(unittest.TestCase):
 def test_amplitude_manual_sign(self):
  c=np.arange(10.,30.);l=c*.98;h=c*(1+np.arange(20)/100);x=amplitude_window(h,l,c);a=h/l-1;self.assertAlmostEqual(x['score'],-(a[-5:].mean()-a[:5].mean()));self.assertEqual(x['valid_days'],20);self.assertEqual(x['k'],5)
 def test_valid_window_threshold_ties_and_scaling(self):
  c=np.repeat(10.,20);l=np.linspace(8,9,20);h=np.linspace(11,12,20);a=amplitude_window(h,l,c);np.testing.assert_allclose(a['score'],amplitude_window(h*2,l*2,c*2)['score'])
  self.assertAlmostEqual(a['score'],-((h/l-1)[-5:].mean()-(h/l-1)[:5].mean()))
  h[:10]=l[:10];b=amplitude_window(h,l,c);self.assertEqual(b['valid_days'],10);self.assertEqual(b['k'],2);self.assertTrue(np.isfinite(b['score']));h[10]=l[10];self.assertTrue(np.isnan(amplitude_window(h,l,c)['score']))
 def test_split_event_identity(self):
  rawclose=np.array([10.,5.2,5.3,5.0]);rawopen=np.array([9.9,5.,5.1,5.4]);factor=np.array([1.,2.,2.,2.1]);adjclose=rawclose*factor;adjopen=rawopen*factor
  daytotal=adjclose[1:]/adjclose[:-1]-1;intraday=rawclose[1:]/rawopen[1:]-1;expected=(1+daytotal)/(1+intraday)-1
  actual=overnight_daily(adjopen,adjclose);np.testing.assert_allclose(actual[1:],expected);self.assertAlmostEqual(actual[1],0.);self.assertTrue(np.isnan(actual[0]))
 def test_month_full_no_fill(self):
  self.assertAlmostEqual(full_month_overnight([.1,-.05,.02],3),1.1*.95*1.02-1);self.assertTrue(np.isnan(full_month_overnight([.1,np.nan,.02],3)));self.assertTrue(np.isnan(full_month_overnight([.1,.02],3)))
 def frame(self):
  return pd.DataFrame([{'instrument':i,'month':m,'overnight_month':np.nan if m==0 else (m+1)*.001,'month_return':.01} for i in ['sh000001','sz000001'] for m in range(30)])
 def test_ovnt_gap_compound_and_prefix(self):
  f=self.frame();a=ovnt_scores(f);g=a[a.instrument=='sh000001'].reset_index(drop=True);self.assertTrue(np.isnan(g.ovnt12.iloc[11]));self.assertAlmostEqual(g.ovnt12.iloc[12],(np.prod(1+np.arange(2,13)*.001)-1)/11)
  f.loc[f.month>=12,'overnight_month']*=5;b=ovnt_scores(f);np.testing.assert_allclose(a.loc[a.month<=12,'ovnt12'],b.loc[b.month<=12,'ovnt12'],equal_nan=True)
 def test_calendar_gap_and_zero_filter(self):
  f=self.frame();f.loc[f.month.isin([10,11,12]),'month_return']=0;a=ovnt_scores(f);self.assertTrue(a.loc[a.month.eq(12),'last3_months_zero'].all());self.assertFalse(a.loc[a.month.eq(11),'last3_months_zero'].any())
  with self.assertRaises(AssertionError):ovnt_scores(f[f.month.ne(6)])
if __name__=='__main__':unittest.main()
