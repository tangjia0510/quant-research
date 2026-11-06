import importlib.util,unittest
from pathlib import Path
s=importlib.util.spec_from_file_location('freshness',Path(__file__).parents[1]/'build_freshness.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class FreshnessTests(unittest.TestCase):
 def test_unknown_publication_not_guessed(self):
  r=m.row('events','event','2009-01-01');self.assertIsNone(r['latest_expected_source_publication_at']);self.assertEqual(r['freshness_state'],'expected_latest_unverified')
 def test_old_daily_not_current(self):
  r=m.row('daily','daily','2026-03-03','2026-10-30');self.assertEqual(r['freshness_state'],'observation_behind_target')
 def test_daily_reaching_target_not_PIT(self):
  r=m.row('daily','daily','2026-10-30','2026-10-30');self.assertFalse(r['publication_lag_inferred_from_age']);self.assertIsNone(r['latest_expected_source_publication_at'])
 def test_market_lifecycle_partition(self):
  universe=[{'instrument':'sz.000001','status':'active'},{'instrument':'sz.000002','status':'delisted'},{'instrument':'bj.920001','status':'inferred'},{'instrument':'sh.600001','status':'active'}]
  stocks=[{'instrument':'sz000001','last_date':m.TARGET},{'instrument':'sz000002','last_date':'2020-01-01'},{'instrument':'bj920001','last_date':None}]
  c=m.market_freshness_counts(stocks,universe)
  self.assertEqual(sum(c.values()),4);self.assertEqual(c['observed_target_reached'],1);self.assertEqual(c['delisted_older_or_no_observation'],1);self.assertEqual(c['lifecycle_unknown_before_target_or_no_observation'],1);self.assertEqual(c['unattempted_or_nonterminal'],1)
if __name__=='__main__' :unittest.main()
