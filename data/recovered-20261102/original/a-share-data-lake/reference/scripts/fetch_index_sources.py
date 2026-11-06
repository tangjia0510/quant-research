import urllib.request,urllib.parse,json,time,hashlib
from pathlib import Path
from datetime import datetime,timezone
B=Path(__file__).resolve().parents[1]; rec=[]
def get(name,url):
 time.sleep(1)
 try:
  with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'}),timeout=40) as r:b=r.read();s=r.status
  (B/'raw'/name).write_bytes(b);rec.append(dict(file=name,url=url,status=s,bytes=len(b),sha256=hashlib.sha256(b).hexdigest(),at=datetime.now(timezone.utc).isoformat()));print(name,s,len(b),flush=True)
 except Exception as e:rec.append(dict(file=name,url=url,error=str(e),at=datetime.now(timezone.utc).isoformat()));print(name,type(e).__name__,str(e),flush=True)
 (B/'index-fetch-receipts.json').write_text(json.dumps(rec,ensure_ascii=False,indent=2))
get('bse-code-mapping.html','https://www.bse.cn/service/code_mapping.html')
for code in ['000300','000905','000852','000016','000688','000510']:
 get(code+'cons.xls','https://www.csindex.com.cn/uploads/file/autofile/cons/'+code+'cons.xls')
 get(code+'weight.xls','https://www.csindex.com.cn/uploads/file/autofile/weight/'+code+'weight.xls')
 get(code+'methodology.pdf','https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/indices/detail/files/zh_CN/'+code+'_Index_Methodology_cn.pdf')
