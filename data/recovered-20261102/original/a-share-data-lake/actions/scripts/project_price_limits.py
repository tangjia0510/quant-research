"""Lossless selected-column projection of an independently downloaded public snapshot."""
import json,hashlib,datetime,math
from pathlib import Path
import pyarrow as pa,pyarrow.parquet as pq,pyarrow.compute as pc
BASE=Path(__file__).resolve().parents[1];SOURCE=BASE.parent/'market/hf_bulk';OUT=BASE/'normalized/hf_price_limits';OUT.mkdir(exist_ok=True)
def sha(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
 return h.hexdigest()
report={'source_metadata':json.loads((SOURCE/'metadata/source.json').read_text()),'generated_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'files':[],'rows':0,'null_limit_rows':0,'invalid_order_rows':0,'close_outside_limits':0,'examples':[],'limitations':['Third-party publisher fields are not exchange-certified daily limits','Raw duplicate code-dates are retained; source audit reports3180 duplicates, so this projection is not unique canonical price table','Missing price limits remain null; no 5/10/20/30 percent rule inferred','No historical ST or pause status can be inferred just from price-limit ratio','Source stops2026-03-03 and covers main-board only, not wholeA','See parent source audit for units and underlying-licence uncertainty']}
for path in sorted((SOURCE/'raw').glob('*.parquet')):
 out=OUT/path.name;writer=None;n=0
 for batch in pq.ParquetFile(path).iter_batches(batch_size=200000,columns=['code','date','high_limit','low_limit','prev_close','close']):
  t=pa.Table.from_batches([batch]);codes=t['code'].to_pylist();instrument=pa.array([x[7:].lower()+'.'+x[:6] for x in codes]);t=t.append_column('instrument',instrument)
  if writer is None:writer=pq.ParquetWriter(out,t.schema,compression='zstd')
  writer.write_table(t);n+=len(t);report['rows']+=len(t)
  hi=t['high_limit'];lo=t['low_limit'];close=t['close'];null=pc.or_(pc.is_null(hi),pc.is_null(lo));bad=pc.and_(pc.invert(null),pc.or_(pc.less(hi,lo),pc.or_(pc.less_equal(hi,0),pc.less_equal(lo,0))))
  outside=pc.and_(pc.invert(null),pc.or_(pc.greater(close,pc.add(hi,.011)),pc.less(close,pc.subtract(lo,.011))))
  report['null_limit_rows']+=pc.sum(pc.cast(null,pa.int64())).as_py() or 0;report['invalid_order_rows']+=pc.sum(pc.cast(bad,pa.int64())).as_py() or 0;report['close_outside_limits']+=pc.sum(pc.cast(outside,pa.int64())).as_py() or 0
  if len(report['examples'])<20:report['examples']+=(t.filter(pc.fill_null(pc.or_(bad,outside),False)).slice(0,20-len(report['examples'])).to_pylist())
 if writer:writer.close()
 report['files'].append({'source_file':str(path.relative_to(BASE.parent)),'source_sha256':sha(path),'output_file':str(out.relative_to(BASE)),'sha256':sha(out),'rows':n});print(path.name,n,flush=True)
(BASE/'catalog/hf-price-limits.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps({k:v for k,v in report.items() if k not in ['source_metadata','files','examples','limitations']},ensure_ascii=False),flush=True)
