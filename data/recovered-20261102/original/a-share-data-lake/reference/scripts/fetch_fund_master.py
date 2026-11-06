import urllib.request,urllib.parse,json,time,hashlib,re
from pathlib import Path
from datetime import datetime,timezone
B=Path(__file__).resolve().parents[1];rec=[]
def get(n,u):
 time.sleep(1)
 try:
  b=urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'Mozilla/5.0','Referer':'https://www.sse.com.cn/'}),timeout=35).read();(B/'raw'/n).write_bytes(b);rec.append(dict(file=n,url=u,bytes=len(b),sha256=hashlib.sha256(b).hexdigest(),at=datetime.now(timezone.utc).isoformat()));print(n,len(b),flush=True);return b
 except Exception as e:rec.append(dict(file=n,url=u,error=str(e)));print(n,str(e),flush=True)
 finally:(B/'fund-master-receipts.json').write_text(json.dumps(rec,ensure_ascii=False,indent=2))
for page in range(1,6):
 pars={'isPagination':'true','sqlId':'FUND_LIST','pageHelp.pageSize':'1000','pageHelp.pageNo':str(page),'pageHelp.beginPage':str(page),'pageHelp.cacheSize':'1','pageHelp.endPage':str(page),'pagecache':'false'}
 b=get('sse-all-funds-page'+str(page)+'.json','https://query.sse.com.cn/commonSoaQuery.do?'+urllib.parse.urlencode(pars))
 if not b:break
 d=json.loads(b);print(d.keys(),d.get('pageHelp'),flush=True)
 if page*1000>=int(d.get('pageHelp',{}).get('total',0)):break
for kind,url in [('all','https://www.szse.cn/market/fund/list/all/index.html'),('etf','https://www.szse.cn/market/fund/list/etfList/index.html'),('convertible','https://www.szse.cn/market/bond/index.html')]:
 b=get('szse-'+kind+'-page.html',url)
 if not b:continue
 s=b.decode(errors='replace');m=re.search(r'data-s-catalog-id="([^"]+)"',s) or re.search(r"CatalogId\s*=\s*'([^']+)'",s)
 if not m:print('noCatalog',kind,flush=True);continue
 cat=m.group(1);get('szse-'+kind+'-master.xlsx','https://www.szse.cn/api/report/ShowReport?'+urllib.parse.urlencode({'SHOWTYPE':'xlsx','CATALOGID':cat,'TABKEY':'tab1'}))
