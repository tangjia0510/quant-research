import urllib.request,urllib.parse,json,time,hashlib,pandas as pd
from pathlib import Path
from datetime import datetime,timezone
B=Path(__file__).resolve().parents[1];rec=[];rows=[]
for name,params in [('main-risk',{'sqlId':'PL_SSGSXX_FXJSBGPLB','domesticIndicator':'S','productType':'0'}),('main-delisting-period',{'sqlId':'PL_SSGSXX_FXJSBGPLB','domesticIndicator':'P','productType':'0'}),]:
 time.sleep(1);u='https://query.sse.com.cn/commonSoaQuery.do?'+urllib.parse.urlencode(params);r={'url':u,'acquired_at':datetime.now(timezone.utc).isoformat(),'file':'raw/sse-'+name+'.json'}
 try:
  b=urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'Mozilla/5.0','Referer':'https://www.sse.com.cn/'}),timeout=30).read();(B/r['file']).write_bytes(b);data=json.loads(b).get('result',[]);r.update(rows=len(data),sha256=hashlib.sha256(b).hexdigest());rows.extend(dict(x,snapshot_acquired_at=r['acquired_at'],source_file=r['file'],list_type=name) for x in data)
 except Exception as e:r['error']=str(e)
 rec.append(r);(B/'sse-risk-retry-receipts.json').write_text(json.dumps(rec,ensure_ascii=False,indent=2));print(name,r.get('rows',r.get('error')),flush=True)
pd.DataFrame(rows).to_csv(B/'normalized/sse-current-risk-main-retry.csv',index=False)
