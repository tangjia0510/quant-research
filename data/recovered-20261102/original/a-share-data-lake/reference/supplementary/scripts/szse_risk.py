import urllib.request,json,time,hashlib,pandas as pd
from pathlib import Path
from datetime import datetime,timezone
B=Path(__file__).resolve().parents[1];rec=[]
for tab in ['tab1','tab2']:
 time.sleep(1);u=f'https://www.szse.cn/api/report/ShowReport?SHOWTYPE=xlsx&CATALOGID=fxjsb&TABKEY={tab}';r=dict(url=u,file=f'raw/szse-risk-{tab}.xlsx',acquired_at=datetime.now(timezone.utc).isoformat())
 try:
  b=urllib.request.urlopen(u,timeout=30).read();(B/r['file']).write_bytes(b);d=pd.read_excel(B/r['file'],dtype=str);r.update(rows=len(d),sha256=hashlib.sha256(b).hexdigest());d.to_csv(B/f'normalized/szse-risk-{tab}.csv',index=False)
 except Exception as e:r['error']=str(e)
 rec.append(r);(B/'szse-risk-receipts.json').write_text(json.dumps(rec,ensure_ascii=False,indent=2));print(r.get('rows',r.get('error')),flush=True)
