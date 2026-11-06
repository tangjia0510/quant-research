#!/usr/bin/env python3
"""Derived A-share and date-screened snapshot views. Not historical-vintage PIT tables."""
from pathlib import Path
import json,hashlib,os,datetime
import pyarrow.parquet as pq
import pyarrow as pa
ROOT=Path(__file__).resolve().parent
SOURCES=[ROOT,ROOT/'supplemental',ROOT/'full_statements',ROOT/'special_financials',ROOT/'forward_forecasts',ROOT/'pagination_repairs/forecast-stable-v1']+sorted((ROOT/'financial_refreshes').glob('*/*'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 out=[]
 for root in SOURCES:
  for catalog in sorted((root/'catalog').glob('*/*.json')):
   meta=json.loads(catalog.read_text());rel=meta.get('parquet_path')
   if meta.get('status')!='success' or not rel:continue
   src=root/rel
   if not src.exists() or sha(src)!=meta['parquet_sha256']:continue
   rows=pq.read_table(src).to_pylist();a=[x for x in rows if x.get('SECURITY_TYPE_CODE')in('058001001','058001008') or x.get('SECURITY_TYPE')in('A股','中国存托凭证')]
   eligible=[x for x in a if x.get('_asof_eligible_by_date_only') is True and not x.get('_notice_date_future_at_acquisition')]
   records={}
   for name,data in [('a-share-current-snapshot',a),('date-screened-current-snapshot-not-pit',eligible)]:
    dest=ROOT/'views'/name/(root.relative_to(ROOT) if root!=ROOT else'core')/meta['report']/(meta['period']+'.parquet');dest.parent.mkdir(parents=True,exist_ok=True)
    # Preserve schemas even when every row was excluded.
    table=pa.Table.from_pylist(data,schema=pq.read_schema(src));pq.write_table(table,dest,compression='zstd')
    records[name]={'rows':len(data),'path':str(dest.relative_to(ROOT)),'sha256':sha(dest)}
   out.append({'report':meta['report'],'period':meta['period'],'source_path':str(src.relative_to(ROOT)),'source_sha256':meta['parquet_sha256'],'vendor_rows':len(rows),'a_share_cdr_rows':len(a),'non_a_share_rows':len(rows)-len(a),'future_notice_a_rows':sum(bool(x.get('_notice_date_future_at_acquisition'))for x in a),'missing_or_ineligible_disclosure_a_rows':len(a)-len(eligible),'views':records})
 result={'generated_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'pit_ready':False,'warning':'Date screen removes future/missing disclosure dates only. Historic revision vintages and original numerical filing linkage are NOT verified; this is not PIT-safe.','entries':out}
 p=ROOT/'views/manifest.json';p.parent.mkdir(exist_ok=True);tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(result,ensure_ascii=False,indent=2));os.replace(tmp,p)
 print(len(out),sum(x['a_share_cdr_rows']for x in out),'A/CDR rows',sum(x['future_notice_a_rows']for x in out),'future excluded')
if __name__=='__main__':main()
