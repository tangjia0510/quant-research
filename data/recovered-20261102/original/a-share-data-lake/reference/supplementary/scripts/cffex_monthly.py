import urllib.request,xml.etree.ElementTree as ET,csv,json,time,hashlib
from pathlib import Path
from datetime import datetime,timezone
B=Path(__file__).resolve().parents[1];R=B/'raw/cffex';R.mkdir(exist_ok=True);rows=[];rec=[]
dates={}
for s in (B.parent/'normalized/trading-calendar-observed-2019-2026.txt').read_text().splitlines():
 s=s.strip();dates[s[:7]]=s
for i,dt in enumerate(dates.values()):
 d=dt.replace('-','');u=f'http://www.cffex.com.cn/sj/jycs/{d[:6]}/{d[6:]}/index.xml';p=R/(d+'.xml');r={'url':u,'date':dt,'file':str(p.relative_to(B)),'acquired_at':datetime.now(timezone.utc).isoformat()}
 try:
  time.sleep(1)
  if d=='20261030':b=(B/'raw/cffex-20261030-http.xml').read_bytes();r['reused_current_raw']=True
  else:b=urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'Mozilla/5.0'}),timeout=20).read()
  p.write_bytes(b);data=[{e.tag:e.text for e in n} for n in ET.fromstring(b).findall('.//INDEX')];r.update(rows=len(data),sha256=hashlib.sha256(b).hexdigest());rows.extend(dict(x,snapshot_date=dt,source_file=str(p.relative_to(B))) for x in data)
 except Exception as e:r['error']=str(e)
 rec.append(r);(B/'cffex-monthly-receipts.json').write_text(json.dumps(rec,indent=2));print(i+1,len(dates),dt,r.get('rows',r.get('error')),flush=True)
keys=list(dict.fromkeys(k for r in rows for k in r))
with (B/'normalized/cffex-monthend-contract-snapshots.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(rows)
