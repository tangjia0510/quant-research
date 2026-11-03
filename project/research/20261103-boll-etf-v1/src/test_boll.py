import unittest
import numpy as np,pandas as pd
from boll import indicators,targets,simulate,block_reason
class Checks(unittest.TestCase):
 def inputs(self):
  ix=pd.bdate_range('2018-01-01','2020-03-31').strftime('%Y-%m-%d');x=10+np.sin(np.arange(len(ix))/20)
  b=pd.DataFrame(dict(open=x,close=x,high=x+.2,low=x-.2,volume_lots=1000),index=ix);e=pd.DataFrame(columns=['record_date','ex_date','cash_per_unit','pay_date']);return b,e
 def test_population(self):
  b,e=self.inputs();v=indicators(b,e);self.assertTrue(v.iloc[:19].percent_b.isna().all());self.assertAlmostEqual(v['std'].iloc[19],np.std(v.tr.iloc[:20],ddof=0));self.assertAlmostEqual(v.middle.iloc[19],v.tr.iloc[:20].mean())
 def test_scale_invariance(self):
  b,e=self.inputs();v=targets(indicators(b,e));x=b.copy();x.loc[:,['open','close','high','low']]*=7;u=targets(indicators(x,e));np.testing.assert_allclose(v.percent_b,u.percent_b,equal_nan=True,atol=1e-10);np.testing.assert_allclose(v.bandwidth,u.bandwidth,equal_nan=True,atol=1e-10);pd.testing.assert_series_equal(v.boll_breakout,u.boll_breakout);pd.testing.assert_series_equal(v.boll_reentry,u.boll_reentry)
 def test_zero_std(self):
  b,e=self.inputs();b['close']=10.;v=targets(indicators(b,e));self.assertTrue(v.percent_b.isna().all());self.assertFalse(v.boll_breakout.any());self.assertFalse(v.boll_reentry.any())
 def test_signal_states(self):
  # Back in upper half must not enter MR; breakout exits strictly below middle.
  p=[.5,-.1,.2,.5,1,1.1,.5,.49,-.1,.7,-.1,0,.49,.5]
  ind=pd.DataFrame(dict(percent_b=p,tr=p,middle=.5));s=targets(ind)
  self.assertEqual(s.boll_reentry.tolist(),[0,0,1,0,0,0,0,0,0,0,0,1,1,0]);self.assertEqual(s.boll_breakout.tolist(),[0,0,0,0,0,1,1,0,0,0,0,0,0,0])
 def test_future_perturbation(self):
  b,e=self.inputs();s=targets(indicators(b,e));x=b.copy();x.loc['2020-02-03':,'close']*=2;ss=targets(indicators(x,e));pd.testing.assert_frame_equal(s.loc[:'2020-01-31'],ss.loc[:'2020-01-31'])
  for kind in ['boll_breakout','boll_reentry']:
   d,t,_=simulate(b,e,s,kind);dd,tt,_=simulate(x,e,ss,kind);pd.testing.assert_frame_equal(d[d.date<'2020-02-03'],dd[dd.date<'2020-02-03'])
 def test_next_open_lots_cash(self):
  b,e=self.inputs();s=targets(indicators(b,e))
  for kind in ['boll_breakout','boll_reentry']:
   d,t,_=simulate(b,e,s,kind);self.assertTrue((t.date>t.signal_date).all());self.assertTrue((d.cash>=0).all());self.assertTrue((t.units%100==0).all());self.assertFalse(t.date.duplicated().any())
 def test_open_information_set(self):
  b,e=self.inputs();s=targets(indicators(b,e));x=b.copy();x.high*=5;x.low*=.1;x.volume_lots*=3
  for kind in ['boll_breakout','boll_reentry','benchmark']:
   pd.testing.assert_frame_equal(simulate(b,e,s,kind)[1],simulate(x,e,s,kind)[1])
 def test_dividend_rights_and_continuity(self):
  b,e=self.inputs();b.loc[:,['open','close']]=10.;e=pd.DataFrame([dict(record_date='2019-01-15',ex_date='2019-01-16',cash_per_unit=.1,pay_date='2019-01-21')]);b.loc['2019-01-16':,['open','close']]=9.9;s=targets(indicators(b,e));s['boll_reentry']=1;s['ready']=True;s.loc['2019-01-16':,'boll_reentry']=0
  d,t,_=simulate(b,e,s,'boll_reentry',0);d=d.set_index('date');self.assertAlmostEqual(d.loc['2019-01-15','equity'],d.loc['2019-01-16','equity']);self.assertEqual(d.loc['2019-01-17','units'],0);self.assertGreater(d.loc['2019-01-21','dividend_cash_paid'],0);self.assertEqual(d.loc['2019-01-16','dividend_cash_paid'],0)
 def test_pending_override(self):
  b,e=self.inputs();b.loc[:,['open','close']]=10.;b.loc['2019-01-02':'2019-01-04','open']=11.;s=targets(indicators(b,e));s['ready']=True;s['boll_breakout']=1;s.loc['2019-01-04':,'boll_breakout']=0
  d,t,k=simulate(b,e,s,'boll_breakout',0,start='2019-01-02');self.assertTrue(t.empty);self.assertEqual(len(k),3);self.assertFalse(d.loc[d.date=='2019-01-07','pending'].iloc[0])
 def test_boundaries(self):
  self.assertIsNotNone(block_reason(11,10,0));self.assertIsNone(block_reason(9.5,10,.5))
if __name__=='__main__':unittest.main()
