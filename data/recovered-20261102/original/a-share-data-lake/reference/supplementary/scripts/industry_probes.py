import urllib.request,json,time,hashlib,concurrent.futures
from pathlib import Path
from datetime import datetime,timezone
B=Path(__file__).resolve().parents[1]
jobs=[('sw-dictionary.xls','https://www.swsresearch.com/swindex/pdf/SwClass2021/SwClassCode_2021.xls'),('citic-access-document.html','https://datacube.foundersc.com/document/2?doc_id=10858')]

def run(job):
 name,u=job;r={'file':'raw/'+name,'url':u,'acquired_at':datetime.now(timezone.utc).isoformat()}
 try:
  req=urllib.request.Request(u,headers={'User-Agent':'Mozilla/5.0','Referer':u})
  with urllib.request.urlopen(req,timeout=30) as f:b=f.read();r['status']=f.status
  (B/'raw'/name).write_bytes(b);r.update(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
 except Exception as e:r['error']=str(e)
 return r
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:rec=list(ex.map(run,jobs))
(B/'industry-final-probe-receipts.json').write_text(json.dumps(rec,ensure_ascii=False,indent=2));print(rec)
