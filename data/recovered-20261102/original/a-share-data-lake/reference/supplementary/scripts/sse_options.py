import urllib.request,urllib.parse,json,time,hashlib,pandas as pd
from pathlib import Path
from datetime import datetime,timezone
B=Path(__file__).resolve().parents[1];rec=[];rows=[]
for page in range(1,21):
 time.sleep(1);p={'isPagination':'true','expireDate':'','securityId':'','sqlId':'SSE_ZQPZ_YSP_GGQQZSXT_XXPL_DRHY_SEARCH_L','pageHelp.pageSize':1000,'pageHelp.pageNo':page,'pageHelp.beginPage':page,'pageHelp.endPage':page,'pageHelp.cacheSize':1};u='https://query.sse.com.cn/commonQuery.do?'+urllib.parse.urlencode(p);r=dict(url=u,file=f'raw/sse-options-current-{page}.json',acquired_at=datetime.now(timezone.utc).isoformat())
 try:
  b=urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'Mozilla/5.0','Referer':'https://www.sse.com.cn/'}),timeout=30).read();(B/r['file']).write_bytes(b);d=json.loads(b);data=d.get('result',[]);r.update(rows=len(data),total=d.get('pageHelp',{}).get('total'),sha256=hashlib.sha256(b).hexdigest());rows.extend(dict(x,source_file=r['file'],acquired_at=r['acquired_at']) for x in data)
 except Exception as e:r['error']=str(e)
 rec.append(r);(B/'sse-options-receipts.json').write_text(json.dumps(rec,indent=2));print(r.get('rows',r.get('error')),flush=True)
 if 'error' in r or not data or len(rows)>=int(r.get('total') or 0):break
pd.DataFrame(rows).to_csv(B/'normalized/sse-current-option-contracts.csv',index=False)
