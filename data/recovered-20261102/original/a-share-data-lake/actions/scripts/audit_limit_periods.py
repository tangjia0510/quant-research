import csv,json
from pathlib import Path
import pyarrow.parquet as pq,pyarrow.compute as pc,pyarrow as pa
BASE=Path(__file__).resolve().parents[1];out=[];periods={k:{'rows':0,'null_limit_rows':0,'outside_limit_rows':0} for k in ['all','since2019','since2025']}
for p in sorted((BASE/'normalized/hf_price_limits').glob('*.parquet')):
 for b in pq.ParquetFile(p).iter_batches(batch_size=200000):
  t=pa.Table.from_batches([b]);null=pc.or_(pc.is_null(t['high_limit']),pc.is_null(t['low_limit']));bad=pc.fill_null(pc.or_(pc.greater(t['close'],pc.add(t['high_limit'],.011)),pc.less(t['close'],pc.subtract(t['low_limit'],.011))),False)
  out+=t.filter(bad).to_pylist()
  for name,mask in [('all',pa.array([True]*len(t))),('since2019',pc.greater_equal(t['date'],'2019-01-01')),('since2025',pc.greater_equal(t['date'],'2025-01-01'))]:
   periods[name]['rows']+=pc.sum(pc.cast(mask,pa.int64())).as_py() or 0;periods[name]['null_limit_rows']+=pc.sum(pc.cast(pc.and_(mask,null),pa.int64())).as_py() or 0;periods[name]['outside_limit_rows']+=pc.sum(pc.cast(pc.and_(mask,bad),pa.int64())).as_py() or 0
p=BASE/'catalog/hf-price-limits.json';d=json.loads(p.read_text());d['period_audit']=periods;d['limitations'].append('754 source rows close outside provided limits, including recent periods; do not treat limit fields as execution-certified');p.write_text(json.dumps(d,ensure_ascii=False,indent=2))
with (BASE/'normalized/hf-limit-anomalies.csv').open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=list(out[0]));w.writeheader();w.writerows(out)
print(json.dumps(periods))
