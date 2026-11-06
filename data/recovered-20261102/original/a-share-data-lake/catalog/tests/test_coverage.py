import importlib.util, tempfile, unittest, json
from pathlib import Path
SPEC=importlib.util.spec_from_file_location('coverage',Path(__file__).parents[1]/'build_coverage.py'); m=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(m)
class CoverageTests(unittest.TestCase):
 def test_unknown_expected_not_zero(self):
  self.assertIsNone(m.progress_counts(None,{'success':2},{'success'})['unattempted'])
 def test_partial_not_complete(self):
  d=m.progress_counts(10,{'success':2,'failed':1},{'success','failed'});self.assertEqual(d['unattempted'],7);self.assertFalse(d['scope_complete'])
 def test_sentinel_not_market_start(self):
  self.assertEqual(m.minmax(['1900-01-01','2020-01-01'])['first_observed_date'],'2020-01-01')
 def test_bad_json_diagnostic(self):
  with tempfile.TemporaryDirectory() as td:
   p=Path(td)/'bad.json';p.write_text('{');issues=[];self.assertIsNone(m.read_json(p,issues));self.assertEqual(len(issues),1)
 def test_future_notice_flag(self):
  with tempfile.TemporaryDirectory() as td:
   p=Path(td);(p/'catalog').mkdir();(p/'catalog/progress.json').write_text(json.dumps({'expected_tasks':2,'tasks':[{'status':'success','report':'balance','period':'2026-09-30','rows':1,'notice_date_max':'2999-01-01'}]}));issues=[];d=m.fundamentals(p,issues);self.assertEqual(len(d['future_dated_notice_tasks']),1);self.assertEqual(d['report_period_counts']['unattempted'],1)
 def test_temporary_csv_not_published(self):
  with tempfile.TemporaryDirectory() as td:
   p=Path(td);(p/'normalized').mkdir();(p/'normalized/x.tmp.csv').write_text('date,value\n2020-01-01,1\n');(p/'normalized/x.csv').write_text('date,value\n2020-01-01,1\n');d=m.generic(p,[]);self.assertEqual(len(d['normalized_tables']),1);self.assertTrue(d['normalized_tables'][0]['file'].endswith('/x.csv'))
 def test_duplicate_universe_flag(self):
  with tempfile.TemporaryDirectory() as td:
   p=Path(td)/'u.csv';p.write_text('instrument,exchange\nsh.600000,SSE\nsh.600000,SSE\n');self.assertEqual(m.universe(p,[])['duplicates'],['sh.600000'])
if __name__=='__main__':unittest.main()
