import unittest,sys,json,pathlib
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent));from collect import norm,parse
class Tests(unittest.TestCase):
 def row(self,**k):
  r=dict(day='2026-10-30 10:00:00',open='10',high='10',low='10',close='10',volume='100',amount='1000');r.update(k);return r
 def test_shares_no_multiplier(self):
  x,w=norm([self.row()],'sh600000');self.assertEqual(x[0]['volume_shares'],100);self.assertFalse(w)
 def test_bj_warning_preserved(self):
  x,w=norm([self.row(amount='900')],'bj920000');self.assertEqual(x[0]['amount_cny'],900);self.assertIn('amount_volume_price_disagreement',w)
 def test_zero_trade_not_missing(self):
  x,w=norm([self.row(volume='0',amount='0')],'sh600000');self.assertEqual(x[0]['volume_shares'],0);self.assertFalse(w)
 def test_duplicate_rejected(self):
  with self.assertRaises(ValueError):norm([self.row(),self.row()],'sh600000')
 def test_nonfinite_rejected(self):
  with self.assertRaises(ValueError):norm([self.row(amount='NaN')],'sh600000')
 def test_jsonp_only_no_execution(self):
  self.assertEqual(parse(b'/*header*/ =([]);'),[])
  with self.assertRaises(Exception):parse(b'=(process.exit());')
 def test_after_cutoff_flag(self):
  _,w=norm([self.row(day='2026-11-02 10:00:00')],'sh600000');self.assertIn('after_frozen_complete_day',w)
 def test_sparse_not_filled(self):
  x,w=norm([self.row(),self.row(day='2026-10-30 10:05:00')],'sh600000');self.assertEqual(len(x),2);self.assertFalse(w)
if __name__=='__main__':unittest.main()
