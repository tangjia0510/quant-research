import importlib.util,unittest,tempfile,json,hashlib
from pathlib import Path
s=importlib.util.spec_from_file_location('selection',Path(__file__).parents[1]/'margin_snapshot_selection.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class SnapshotTests(unittest.TestCase):
 def test_latest_validated_whole_day_only(self):
  with tempfile.TemporaryDirectory() as t:
   r=Path(t);(r/'macro/logs').mkdir(parents=True)
   for n,state in [('a','count_key_date_validated'),('b','count_key_date_validated'),('c','pending')]:
    f=r/f'macro/normalized/{n}/day_snapshot.parquet';f.parent.mkdir(parents=True);f.write_bytes(n.encode())
    d={'refresh_id':n,'target_day':'2026-10-30','sources':{'vendor':{'state':state,'files':[{'file':str(f.relative_to(r/'macro')),'sha256':hashlib.sha256(f.read_bytes()).hexdigest()},{'file':'delta.parquet','sha256':'unused'}]}}}
    (r/f'macro/logs/margin-latest-refresh-{n}.json').write_text(json.dumps(d))
   self.assertEqual(m.select_latest(r)['2026-10-30']['refresh_id'],'b')
   (r/'macro/normalized/b/day_snapshot.parquet').write_bytes(b'changed')
   self.assertEqual(m.select_latest(r)['2026-10-30']['refresh_id'],'a')
if __name__=='__main__':unittest.main()
