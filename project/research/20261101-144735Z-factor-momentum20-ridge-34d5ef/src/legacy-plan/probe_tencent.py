import json,urllib.request,urllib.parse,hashlib,time
from pathlib import Path
p=Path(__file__).parent;q=p/'tencent-probe';q.mkdir(exist_ok=True)
assert (p/'selection.json').exists() and (p/'source-amendment.json').exists()
receipts=[]
for code in ['sh600000','sz000005']:
 for adj in ['', 'hfq']:
  url='https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get?'+urllib.parse.urlencode({'param':f'{code},day,2019-01-01,2020-12-31,640,{adj}'})
  name=code+'-'+(adj or 'raw')+'.json'
  try:
   with urllib.request.urlopen(url,timeout=20) as r:b=r.read();status=r.status
   (q/name).write_bytes(b);d=json.loads(b);data=d.get('data',{}).get(code,{});key=next((k for k in ['hfqday' if adj else 'day','day'] if k in data),None);rows=data.get(key,[])
   receipt={'file':name,'url':url,'status':status,'sha256':hashlib.sha256(b).hexdigest(),'code':d.get('code'),'keys':list(data),'rows':len(rows),'first':rows[:1],'last':rows[-1:]}
  except Exception as e:receipt={'file':name,'url':url,'error':str(e),'type':type(e).__name__}
  receipts.append(receipt);print(json.dumps(receipt,ensure_ascii=False),flush=True);time.sleep(.3)
(q/'receipt.json').write_text(json.dumps(receipts,ensure_ascii=False,indent=2)+'\n')
