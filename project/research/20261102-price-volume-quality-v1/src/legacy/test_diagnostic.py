import unittest
import numpy as np,pandas as pd
from build_diagnostic import stock_signals
class ContractTests(unittest.TestCase):
 def fixture(self):
  cal=pd.bdate_range('2024-01-01',periods=120);x=np.arange(120)/100+10
  d=pd.DataFrame({'date':cal,'open':x,'close':x,'high':x*1.01,'low':x*.99,'volume_shares':10000.,'amount_cny':x*10000,'source':'test','factor':1.})
  return cal,d
 def test_nextopen(self):
  c,d=self.fixture();o,q=stock_signals(d,c,c[0],pd.NaT)
  self.assertAlmostEqual(o.loc[70,'forward5'],d.open[76]/d.open[71]-1)
  self.assertAlmostEqual(o.loc[70,'momentum20'],d.close[70]/d.close[50]-1)
  self.assertEqual(o.loc[70,'label_entry_date'],c[71]);self.assertEqual(o.loc[70,'label_exit_date'],c[76])
 def test_no_compressed_missing(self):
  c,d=self.fixture();o,_=stock_signals(d.drop(index=73),c,c[0],pd.NaT)
  self.assertFalse(o.loc[70,'label_available']);self.assertFalse(o.loc[80,'signal_eligible'])
 def test_future_not_signal(self):
  c,d=self.fixture();a,_=stock_signals(d,c,c[0],pd.NaT);d.loc[71:,['open','close','high','low']]*=2;b,_=stock_signals(d,c,c[0],pd.NaT)
  np.testing.assert_allclose(a.loc[:70,'momentum20'],b.loc[:70,'momentum20'],equal_nan=True)
 def test_no_factor_fill(self):
  c,d=self.fixture();d.loc[65,'factor']=np.nan;o,_=stock_signals(d,c,c[0],pd.NaT);self.assertFalse(o.loc[70,'signal_eligible'])
 def test_lifecycle(self):
  c,d=self.fixture();o,_=stock_signals(d,c,c[0],c[80],None,str(c[80].date()));self.assertFalse(o.loc[80,'bar_good']);self.assertFalse(o.loc[75,'label_available'])
 def test_delist_effective_exclusive(self):
  c,d=self.fixture();o,_=stock_signals(d,c,c[0],c[80]);self.assertFalse(o.loc[80,"bar_good"]);self.assertTrue(o.loc[79,"bar_good"])
 def test_units(self):
  c,d=self.fixture();a,_=stock_signals(d,c,c[0],pd.NaT);d.volume_shares*=100;b,_=stock_signals(d,c,c[0],pd.NaT)
  self.assertTrue(a.loc[70,'signal_eligible']);self.assertFalse(b.loc[70,'signal_eligible'])
 def test_scale_invariance(self):
  c,d=self.fixture();a,_=stock_signals(d,c,c[0],pd.NaT);d[["open","high","low","close","amount_cny"]]*=3;b,_=stock_signals(d,c,c[0],pd.NaT);np.testing.assert_allclose(a.momentum20,b.momentum20,atol=1e-12,equal_nan=True);np.testing.assert_allclose(a.forward5,b.forward5,atol=1e-12,equal_nan=True)
 def test_ipo(self):
  c,d=self.fixture();o,_=stock_signals(d,c,c[0],pd.NaT);self.assertFalse(o.loc[59,'signal_eligible']);self.assertTrue(o.loc[60,'signal_eligible'])
if __name__=='__main__':unittest.main()
