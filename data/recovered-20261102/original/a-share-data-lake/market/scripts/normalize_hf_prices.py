#!/usr/bin/env python3
import hashlib,json,datetime as dt
from pathlib import Path
import numpy as np,pyarrow as pa,pyarrow.parquet as pq
R=Path(__file__).resolve().parents[1]/'hf_bulk';out=R/'normalized_prices';out.mkdir(exist_ok=True)
a=json.loads((R/'audit.json').read_text());dups=json.loads((R/'duplicate-audit.json').read_text());assert a['invalid_ohlc_rows']==0 and a['invalid_volume_rows']==0 and dups['matches_all_duplicate_keys_from_global_audit'];assert all(x['differences']==['name'] for x in dups['conflicts'])
seen=set();receipts=[];total=0;removed=0
cols=['code','date','open','high','low','close','volume','turnover','prev_close']
for file in sorted((R/'raw').glob('*.parquet')):
 dest=out/file.name;writer=None;nr=0
 for batch in pq.ParquetFile(file).iter_batches(batch_size=100000,columns=cols):
  d=batch.to_pandas();mask=np.ones(len(d),dtype=bool)
  for i,c,date in zip(range(len(d)),d.code,d.date):
   if date=='2025-12-18':
    key=(c,date)
    if key in seen:mask[i]=False;removed+=1
    else:seen.add(key)
  d=d.loc[mask];n=len(d)
  table=pa.table({'date':pa.array(d.date.tolist(),type=pa.string()).cast(pa.date32()),'instrument':pa.array([x[-2:].lower()+x[:6] for x in d.code]),'open':pa.array(d.open),'high':pa.array(d.high),'low':pa.array(d.low),'close':pa.array(d.close),'prev_close_reported':pa.array(d.prev_close),'volume_lots':pa.array(d.volume),'volume_shares':pa.array(d.volume*100),'amount_thousand_cny':pa.array(d.turnover),'amount_cny':pa.array(d.turnover*1000),'source':pa.array(['huggingface:ellendan/a-share-prices']*n),'source_revision':pa.array(['94d41d1a0f8557682c6acfa829e9fc2c946b4605']*n)})
  if writer is None:writer=pq.ParquetWriter(dest,table.schema,compression='zstd')
  writer.write_table(table,row_group_size=100000);nr+=n
 if writer:writer.close()
 h=hashlib.sha256()
 with dest.open('rb') as f:
  for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
 raw=json.loads((R/'metadata'/(file.name+'.json')).read_text());receipts.append({'file':str(dest.relative_to(R)),'rows':nr,'bytes':dest.stat().st_size,'sha256':h.hexdigest(),'raw_file':str(file.relative_to(R)),'raw_sha256':raw['sha256'],'source_url':raw['url']});total+=nr;print(file.name,nr,flush=True)
assert removed==3180 and total==a['rows']-3180
manifest={'generated_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'source':'HF ellendan/a-share-prices, independent unadjusted daily price partition','price_basis':'unadjusted','asof':'2026-03-03','earliest':'2005-01-04','rows':total,'codes':a['unique_codes'],'numeric_duplicate_rows_collapsed':removed,'metadata_name_conflict_keys':dups['conflicts'],'duplicate_policy':'Daily numeric fields of every duplicate pair were identical. Names are not projected; raw names/conflicts preserved. Keep first identical numeric observation, no field mixing.','source_units':{'volume':'lots','turnover':'thousand CNY'},'normalized_units':{'volume_shares':'shares','amount_cny':'CNY'},'missing_sessions':'Not filled; publisher excludes paused rows and omissions may remain','price_limit_fields':'Not included; separate actions branch found field-specific quality issues','metadata_valuations':'All original numeric and descriptive columns remain in raw parquet; historical availability not certified','files':receipts}
(R/'normalized-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n');print('NORMALIZED',total,removed,flush=True)
