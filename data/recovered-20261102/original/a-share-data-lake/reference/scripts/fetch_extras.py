import urllib.request,urllib.parse,json,time,hashlib
from pathlib import Path
from datetime import datetime,timezone
B=Path(__file__).resolve().parents[1]; receipts=[];extra=[]
def fetch(name,url,data=None,referer=None):
 for a in range(3):
  time.sleep(1 if a==0 else 4*a)
  try:
   req=urllib.request.Request(url,data=data,headers={'User-Agent':'Mozilla/5.0','Referer':referer or url})
   with urllib.request.urlopen(req,timeout=35) as r: body=r.read();status=r.status
   p=B/'raw'/name;p.write_bytes(body);receipts.append(dict(file=name,url=url,method='POST' if data else 'GET',status=status,size=len(body),sha256=hashlib.sha256(body).hexdigest(),at=datetime.now(timezone.utc).isoformat()));return body
  except Exception as e:
   receipts.append(dict(file=name,url=url,error=type(e).__name__+': '+str(e),attempt=a+1,at=datetime.now(timezone.utc).isoformat()))
   if a==2:return None
base='https://query.sse.com.cn/commonQuery.do?'
for status,cstatus in [('active','2,4,5,7,8'),('delisted','3')]:
 pars=dict(sqlId='COMMON_SSE_CP_GPJCTPZ_GPLB_GP_L',isPagination='true',type='inParams',STOCK_TYPE='8',COMPANY_STATUS=cstatus,**{'pageHelp.pageSize':'10000','pageHelp.pageNo':'1'})
 name='sse-star-'+status+'.json';body=fetch(name,base+urllib.parse.urlencode(pars),referer='https://www.sse.com.cn/')
 if body:
  d=json.loads(body);rs=d.get('result',[])
  assert len(rs)==int(d['pageHelp']['total'])
  for r in rs:
   c=r.get('A_STOCK_CODE') or r.get('COMPANY_CODE')
   if not c.startswith('68'):continue
   def dt(s):return str(s)[:4]+'-'+str(s)[4:6]+'-'+str(s)[6:8] if str(s).isdigit() and len(str(s))==8 else ''
   extra.append(dict(instrument='sh.'+c,exchange='SSE',code=c,name=r.get('COMPANY_ABBR',''),ipo_date=dt(r.get('LIST_DATE')),delist_date=dt(r.get('DELIST_DATE')),status=status,board='STAR',industry=r.get('CSRC_CODE_DESC',''),source_file=name))
 print(name,len(extra),flush=True)
(B/'normalized/extras.json').write_text(json.dumps(extra,ensure_ascii=False,indent=2))
url='https://www.bse.cn/nqxxController/nqxxCnzq.do'
for page in range(100):
 data=urllib.parse.urlencode({'page':str(page),'typejb':'T','xxfcbj[]':'2','xxzqdm':'','sortfield':'xxzqdm','sorttype':'asc'}).encode()
 body=fetch(f'bse-active-page-{page}.json',url,data,referer='https://www.bse.cn/nq/listedcompany.html')
 if not body:break
 text=body.decode();start=text.find('[');end=text.rfind(']')
 try:d=json.loads(text[start:end+1]);obj=d[0];print('bse',page,obj.get('totalPages'),len(obj.get('content',[])),flush=True)
 except Exception as e: print('bseparse',str(e),text[:200],flush=True);break
 if page+1>=int(obj.get('totalPages',0)):break
(B/'fetch-extras-receipts.json').write_text(json.dumps(receipts,ensure_ascii=False,indent=2))
