import urllib.request,json,time,hashlib,pandas as pd
from pathlib import Path
from datetime import datetime,timezone
B=Path(__file__).resolve().parents[1];rec=[]
for code in ['000300','000905','000852','000016','000688','000510']:
 for kind in ['closeweight','indicator']:
  name=code+'-'+kind+'.xls';u='https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/file/autofile/'+kind+'/'+code+kind+'.xls';time.sleep(1)
  try:
   b=urllib.request.urlopen(u,timeout=30).read();(B/'raw'/name).write_bytes(b);d=pd.read_excel(B/'raw'/name,dtype=str);d.to_csv(B/'normalized'/(name[:-4]+'.csv'),index=False);rec.append(dict(file=name,url=u,rows=len(d),sha256=hashlib.sha256(b).hexdigest(),acquired_at=datetime.now(timezone.utc).isoformat()));print(name,len(d),flush=True)
  except Exception as e:rec.append(dict(file=name,url=u,error=str(e)));print(name,str(e),flush=True)
  (B/'index-weight-receipts.json').write_text(json.dumps(rec,ensure_ascii=False,indent=2))
