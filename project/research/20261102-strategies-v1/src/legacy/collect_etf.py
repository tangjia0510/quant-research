from pathlib import Path
import requests,sys,json,hashlib,datetime,time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(Path.cwd()/'a-share-data-lake/catalog'))
from host_gate import host_gate
S=ROOT/'sources'; URL='https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get'
for start,end in [('2018-01-01','2019-12-31'),('2020-01-01','2021-12-31'),('2022-01-01','2023-12-31'),('2024-01-01','2025-12-31'),('2026-01-01','2026-10-30')]:
 for basis in ['raw','hfq']:
  p=S/f'510300-{start[:4]}-{basis}.json'; receipt=p.with_suffix('.receipt.json')
  if p.exists() and receipt.exists():continue
  with host_gate('tencent'):
   r=requests.get(URL,params={'param':f'sh510300,day,{start},{end},640,'+('' if basis=='raw' else basis)},timeout=30)
  p.write_bytes(r.content);receipt.write_text(json.dumps({'url':r.url,'status':r.status_code,'sha256':hashlib.sha256(r.content).hexdigest(),'requested_start':start,'requested_end':end,'acquired_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()},indent=2))
  if r.status_code in (401,403,429):raise RuntimeError(f'access restriction {r.status_code}; no retry')
  r.raise_for_status(); d=r.json();assert d['code']==0;print(start,basis,len(d['data']['sh510300'].get('day' if basis=='raw' else 'hfqday',[])),flush=True)
