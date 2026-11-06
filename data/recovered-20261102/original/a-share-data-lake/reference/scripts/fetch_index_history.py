import urllib.request,urllib.parse,json,time,hashlib,re
from pathlib import Path
from datetime import datetime,timezone
B=Path(__file__).resolve().parents[1];R=B/'raw/csi-history';R.mkdir(exist_ok=True);rec=[]
def fetch(name,url,data=None):
 p=R/name
 for a in range(2):
  time.sleep(1+3*a)
  try:
   req=urllib.request.Request(url,data=json.dumps(data).encode() if data else None,headers={'User-Agent':'Mozilla/5.0','Content-Type':'application/json','Referer':'https://www.csindex.com.cn/'})
   with urllib.request.urlopen(req,timeout=35) as r:b=r.read();s=r.status
   p.write_bytes(b);rec.append(dict(file=str(p.relative_to(B)),url=url,request=data,status=s,size=len(b),sha256=hashlib.sha256(b).hexdigest(),at=datetime.now(timezone.utc).isoformat()));return b
  except Exception as e:
   rec.append(dict(file=str(p.relative_to(B)),url=url,request=data,error=str(e),attempt=a+1,at=datetime.now(timezone.utc).isoformat()))
  finally:(B/'csi-history-receipts.json').write_text(json.dumps(rec,ensure_ascii=False,indent=2))
rows={}
for keyword in ['沪深300','中证500','中证1000','上证50']:
 for page in range(1,11):
  payload={'lang':'cn','page':{'key':'','page':page,'rows':100},'startDate':'2019-01-01','endDate':'2026-11-01','searchInput':keyword,'classList':[],'indexList':[],'relatedTopics':['index_rebalance'],'typeList':['announcement']}
  b=fetch(f'list-{keyword}-{page}.json','https://www.csindex.com.cn/csindex-home/announcement/queryAnnouncementByVonew',payload)
  if not b:break
  d=json.loads(b);print(keyword,page,d.get('total'),len(d.get('data') or []),flush=True)
  if not isinstance(d.get('data'),list):break
  for x in d['data']:rows[str(x['id'])]=x
  if page*100>=int(d.get('total') or 0):break
(B/'normalized/csi-announcement-list.json').write_text(json.dumps(list(rows.values()),ensure_ascii=False,indent=2))
for i,(key,row) in enumerate(rows.items()):
 b=fetch(f'detail-{key}.json','https://www.csindex.com.cn/csindex-home/announcement/queryAnnouncementById?id='+key)
 if not b:continue
 d=json.loads(b).get('data') or {}
 for j,a in enumerate(d.get('enclosureList',[])):
  url=a.get('fileUrl')
  if not url:continue
  url=urllib.parse.quote(url,safe=':/?=&%');ext=url.split('?')[0].split('.')[-1]
  if ext.lower() not in ('xls','xlsx','pdf','csv','doc','docx'):ext='bin'
  fetch(f'{key}-attachment-{j}.{ext}',url)
 print('detail',i+1,len(rows),key,flush=True)
