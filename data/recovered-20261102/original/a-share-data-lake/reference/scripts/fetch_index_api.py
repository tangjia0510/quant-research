import urllib.request,urllib.parse,json,time,hashlib
from pathlib import Path
from datetime import datetime,timezone
B=Path(__file__).resolve().parents[1];rec=[]
def get(name,url,data=None):
 time.sleep(1)
 try:
  req=urllib.request.Request(url,data=json.dumps(data).encode() if data else None,headers={'User-Agent':'Mozilla/5.0','Content-Type':'application/json','Referer':'https://www.csindex.com.cn/'})
  with urllib.request.urlopen(req,timeout=40) as r:b=r.read();s=r.status
  (B/'raw'/name).write_bytes(b);rec.append(dict(file=name,url=url,request=data,status=s,bytes=len(b),sha256=hashlib.sha256(b).hexdigest(),at=datetime.now(timezone.utc).isoformat()));print(name,s,len(b),flush=True);return b
 except Exception as e:rec.append(dict(file=name,url=url,request=data,error=str(e),at=datetime.now(timezone.utc).isoformat()));print(name,type(e).__name__,str(e),flush=True)
 finally:(B/'index-api-receipts.json').write_text(json.dumps(rec,ensure_ascii=False,indent=2))
for c in ['000300','000905','000852','000016','000688','000510']:
 for typ in ['cons','weight']:
  get(c+'-'+typ+'-official.xls','https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/file/autofile/'+typ+'/'+c+typ+'.xls')
url='https://www.csindex.com.cn/csindex-home/announcement/queryAnnouncementByVonew'
payload={'pageNum':1,'pageSize':100,'startDate':'2019-01-01','endDate':'2026-11-01','searchInput':'沪深300','relatedTopics':['index_rebalance'],'typeList':['announcement']}
get('csi-news-probe.json',url,payload)
