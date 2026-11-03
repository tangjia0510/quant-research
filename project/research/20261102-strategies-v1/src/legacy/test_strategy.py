import unittest
import pandas as pd,numpy as np
from strategy import signals,simulate,block_reason
class Checks(unittest.TestCase):
 def inputs(self):
  ix=pd.bdate_range('2018-01-01','2020-03-31').strftime('%Y-%m-%d');x=np.linspace(3,6,len(ix));b=pd.DataFrame(dict(open=x,close=x,high=x+.1,low=x-.1,volume_lots=1000),index=ix)
  e=pd.DataFrame(columns=['record_date','ex_date','cash_per_unit','pay_date']);return b,e
 def test_no_future(self):
  b,e=self.inputs();s,t=signals(b,e);x=b.copy();x.loc['2020-02-03':,'close']*=2;ss,_=signals(x,e);pd.testing.assert_frame_equal(s[s.signal_date<'2020-02-03'],ss[ss.signal_date<'2020-02-03'])
 def test_open_no_intraday(self):
  b,e=self.inputs();s,_=signals(b,e);a=simulate(b,e,s)[1];b.high*=4;b.low*=.5;b.volume_lots*=3;c=simulate(b,e,s)[1];pd.testing.assert_frame_equal(a,c)
 def test_next_open_and_cash(self):
  b,e=self.inputs();s,_=signals(b,e);d,t,_=simulate(b,e,s);self.assertTrue((t.date>t.signal_date).all());self.assertTrue((d.cash>=0).all());self.assertTrue((t.units%100==0).all())
 def test_dividend_receivable(self):
  b,e=self.inputs()
  e=pd.DataFrame([dict(record_date='2019-01-15',ex_date='2019-01-16',cash_per_unit=.1,pay_date='2019-01-21')]);s,_=signals(b,e);d,t,_=simulate(b,e,s,'benchmark',0);d=d.set_index('date');q=d.loc['2019-01-15','units'];self.assertAlmostEqual(d.loc['2019-01-16','receivable'],q*.1);self.assertEqual(d.loc['2019-01-16','dividend_cash_paid'],0);self.assertAlmostEqual(d.loc['2019-01-21','dividend_cash_paid'],q*.1)
 def test_limit_and_no_negative(self):
  self.assertIsNotNone(block_reason(11,10,0));self.assertIsNone(block_reason(10,10,0));self.assertIsNone(block_reason(9.5,10,.5))
 def test_signal_ten_months(self):
  b,e=self.inputs();s,_=signals(b,e);self.assertFalse(s.iloc[:9].ready.any());self.assertTrue(s.iloc[9].ready);self.assertEqual(s.iloc[9].target,1)
 def test_ex_total_wealth_and_rights_after_sale(self):
  b,e=self.inputs();b.loc[:,['open','close']]=10.;b.loc[:, 'high']=10.2;b.loc[:, 'low']=9.8
  e=pd.DataFrame([dict(record_date='2019-01-15',ex_date='2019-01-16',cash_per_unit=.1,pay_date='2019-01-21')]);b.loc['2019-01-16':,['open','close']]=9.9
  s=pd.DataFrame([dict(signal_date='2018-12-31',target=1,ready=True),dict(signal_date='2019-01-16',target=0,ready=True)])
  d,t,_=simulate(b,e,s,total_bp=0);d=d.set_index('date');self.assertAlmostEqual(d.loc['2019-01-15','equity'],d.loc['2019-01-16','equity']);self.assertEqual(d.loc['2019-01-17','units'],0);self.assertGreater(d.loc['2019-01-21','dividend_cash_paid'],0)
 def test_pending_new_signal_overrides(self):
  b,e=self.inputs();b.loc[:,['open','close']]=10.;b.loc['2019-01-02':'2019-01-31','open']=11.
  s=pd.DataFrame([dict(signal_date='2018-12-31',target=1,ready=True),dict(signal_date='2019-01-31',target=0,ready=True)])
  d,t,k=simulate(b,e,s,total_bp=0,start='2019-01-02');self.assertTrue(t.empty);self.assertGreater(len(k),0);self.assertFalse(d.loc[d.date=='2019-02-01','pending'].iloc[0])
if __name__=='__main__':unittest.main()
