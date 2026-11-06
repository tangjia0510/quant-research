"""Remove only independently audited byte-equivalent numeric duplicate code-days."""
import json,hashlib,math,datetime
from pathlib import Path
import pyarrow as pa,pyarrow.compute as pc,pyarrow.parquet as pq
BASE=Path(__file__).resolve().parents[1];src=BASE/'normalized/hf_price_limits';dst=BASE/'normalized/hf_price_limits_unique';dst.mkdir(exist_ok=True)
audit=BASE.parent/'market/hf_bulk/duplicate-audit.json';assert audit.exists();seen={};removed=0;rows=0;files=[]
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
 return h.hexdigest()
for path in sorted(src.glob('*.parquet')):
 writer=None;out=dst/path.name;nr=0
 for batch in pq.ParquetFile(path).iter_batches(batch_size=200000):
  t=pa.Table.from_batches([batch]);isday=pc.equal(t['date'],'2025-12-18');indices=pc.indices_nonzero(isday).to_pylist();keep=[True]*len(t)
  for idx in indices:
   r=t.slice(idx,1).to_pylist()[0];key=(r['code'],r['date']);v=tuple(r[x] for x in ['high_limit','low_limit','prev_close','close'])
   if key in seen:
    if seen[key]!=v:raise ValueError('Conflicting duplicate numeric limits')
    keep[idx]=False;removed+=1
   else:seen[key]=v
  t=t.filter(pa.array(keep));null=pc.or_(pc.is_null(t['high_limit']),pc.is_null(t['low_limit']));bad=pc.fill_null(pc.or_(pc.greater(t['close'],pc.add(t['high_limit'],.011)),pc.less(t['close'],pc.subtract(t['low_limit'],.011))),False)
  status=pc.if_else(null,'missing',pc.if_else(bad,'provider_bounds_inconsistent','bounds_consistent_not_exchange_verified'));t=t.append_column('limit_quality',status)
  if writer is None:writer=pq.ParquetWriter(out,t.schema,compression='zstd')
  writer.write_table(t);nr+=len(t);rows+=len(t)
 if writer:writer.close()
 files.append({'source_file':str(path.relative_to(BASE)),'source_sha256':sha(path),'output_file':str(out.relative_to(BASE)),'sha256':sha(out),'rows':nr})
if removed!=3180:raise ValueError(f'Unexpected duplicate count{removed}')
report={'generated_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'status':'complete','source_duplicate_audit':str(audit),'source_duplicate_audit_sha256':sha(audit),'rows':rows,'duplicates_removed':removed,'duplicate_date':'2025-12-18','numeric_conflicts':0,'files':files,'limitation':'Quality flags are data-consistency checks only; no exchange certification or price-limit rule inference; source ends2026-03-03'}
(BASE/'catalog/hf-price-limits-unique.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps({k:v for k,v in report.items() if k!='files'}))
