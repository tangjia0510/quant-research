import gzip,json,collections,datetime
from pathlib import Path
R=Path(__file__).resolve().parents[1]
out=[]
for code in ['sh688001','sh688002','sh688012','sh688013','sh600000','bj920006','bj920012']:
 seen={}
 for p in (R/'market/raw'/code).glob('*.json.gz'):
  d=json.load(gzip.open(p,'rt'))
  for r in d.get('data',{}).get(code,{}).get('day',[]):
   if len(r)>8 and r[0]>='2019-01-01':seen[r[0]]=(r,str(p.relative_to(R)))
 tally=collections.Counter();examples=[]
 for date,(r,p) in sorted(seen.items()):
  low,high,vol,amt=map(float,[r[4],r[3],r[5],r[8]])
  if vol<=0 or amt<=0:continue
  v1=amt*10000/vol;v100=v1/100
  a=low*.995<=v1<=high*1.005;b=low*.995<=v100<=high*1.005
  tally['tested']+=1;tally['shares_hypothesis_within_ohlc']+=a;tally['lots100_hypothesis_within_ohlc']+=b
  if len(examples)<3:examples.append(dict(date=date,low=low,high=high,raw_volume=vol,raw_amount=amt,vwap_if_volume_shares=v1,vwap_if_volume_lots100=v100,raw_path=p))
 out.append(dict(code=code,counts=dict(tally),examples=examples))
d=dict(generated_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),scope='Local raw Tencent arithmetic hypotheses only; amount 10000 conversion itself assumed from existing source contract. Not independent proof of unit. No data mutations.',instruments=out)
(R/'catalog/volume-unit-hypothesis-audit.json').write_text(json.dumps(d,indent=2))
for x in out:print(x['code'],x['counts'])
