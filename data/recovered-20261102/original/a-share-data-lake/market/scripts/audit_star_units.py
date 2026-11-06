import gzip,json,datetime as dt
from pathlib import Path
import pyarrow.parquet as pq
M=Path(__file__).resolve().parents[1];data={};receipts=[];bad_lots=0;bad_shares=0
for f in sorted((M/'raw').glob('sh688*/*.json.gz')):
 code=f.parent.name
 for r in json.loads(gzip.decompress(f.read_bytes())).get('data',{}).get(code,{}).get('day',[]):
  if not '2019-01-01'<=r[0]<='2026-10-30':continue
  data[(code,r[0])]=(float(r[5]),float(r[8])*10000,float(r[4]),float(r[3]))
for v,a,lo,hi in data.values():
 if v and a:
  bad_lots+=not(lo*.98<=a/(v*100)<=hi*1.02);bad_shares+=not(lo*.98<=a/v<=hi*1.02)
match={};conflicts=0
for f in sorted((M/'hf_features/raw').glob('*.parquet')):
 for b in pq.ParquetFile(f).iter_batches(batch_size=100000,columns=['code','date','volume']):
  d=b.to_pandas();d=d[d.code.str.startswith('688')]
  for r in d.itertuples(index=False):
   k=('sh'+r.code[:6],r.date)
   if k in data:
    if k in match and match[k]!=r.volume:conflicts+=1
    match[k]=r.volume
counts={'exact_raw_volume_matches':0,'within_one_share':0,'other':0}
for k,v in match.items():
 diff=abs(v-data[k][0]);counts['exact_raw_volume_matches' if diff==0 else 'within_one_share' if diff<=1 else 'other']+=1
out={'generated_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'codes':len({k[0] for k in data}),'unique_raw_dates':len(data),'vwap_bad_assuming_lots':int(bad_lots),'vwap_bad_assuming_shares':int(bad_shares),'hf_feature_matched_dates':len(match),'hf_feature_volume_duplicate_conflicts':conflicts,**counts,'conclusion':'Tencent STAR raw volume is shares, unlike main-board lots; empirically corroborated by amount/price bounds and independent raw vendor volume, not official unit documentation','hf_feature_quarantine_remains':True}
(M/'star-volume-unit-audit.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out))
