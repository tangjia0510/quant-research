import urllib.request,urllib.parse,json,time,hashlib
from pathlib import Path
out=Path(__file__).parent/'source-review';out.mkdir(exist_ok=True)
common={'sqlId':'COMMON_SSE_CP_GPJCTPZ_GPLB_GP_L','isPagination':'true','type':'inParams','pageHelp.pageSize':'10000','pageHelp.pageNo':'1','STOCK_TYPE':'1','STOCK_CODE':'','REG_PROVINCE':'','CSRC_CODE':''}
queries=[('sse-active','https://query.sse.com.cn/sseQuery/commonQuery.do',{**common,'COMPANY_STATUS':'2,4,5,7,8'}),('sse-delisted','https://query.sse.com.cn/commonQuery.do',{**common,'COMPANY_STATUS':'3'}),('szse-active','https://www.szse.cn/api/report/ShowReport',{'SHOWTYPE':'xlsx','CATALOGID':'1110','TABKEY':'tab1'}),('szse-delisted','https://www.szse.cn/api/report/ShowReport',{'SHOWTYPE':'xlsx','CATALOGID':'1793_ssgs','TABKEY':'tab2'})]
statuses=[]
for name,url,params in queries:
 full=url+'?'+urllib.parse.urlencode(params)
 try:
  req=urllib.request.Request(full,headers={'Referer':'https://www.sse.com.cn/' if name.startswith('sse-') else 'https://www.szse.cn/'})
  with urllib.request.urlopen(req,timeout=20) as r: data=r.read();status=r.status;ctype=r.headers.get('Content-Type')
  (out/(name+'.bin')).write_bytes(data)
  result={'source':name,'url':full,'status':status,'content_type':ctype,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
 except Exception as e:result={'source':name,'url':full,'error':str(e),'type':type(e).__name__}
 statuses.append(result);print(json.dumps(result),flush=True);time.sleep(.5)
(out/'https-probe-status.json').write_text(json.dumps(statuses,indent=2)+'\n')
