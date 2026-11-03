"""Fresh public-data batch; preserves every response and bounded failure evidence."""
import urllib.request,urllib.parse,json,hashlib,time,re,sys
from pathlib import Path
p=Path(__file__).parent; selection=json.loads((p/'selection.json').read_text())
assert hashlib.sha256((p/'selection.json').read_bytes()).hexdigest()=='81dbc821e5ec90177f02dc97077b6356629dd76a6bc024cc5e564c4f64c689cc'
assert (p/'source-amendment-2.json').exists()
out=p/'mixed-source';out.mkdir(exist_ok=True);ledger=out/'receipts.jsonl'
def get(url,file):
 path=out/file
 if path.exists():return path.read_bytes()
 for attempt in range(2):
  try:
   req=urllib.request.Request(url)
   with urllib.request.urlopen(req,timeout=25) as r:b=r.read();status=r.status
   if not b:raise ValueError('Empty response')
   path.write_bytes(b)
   with ledger.open('a') as f:f.write(json.dumps({'url':url,'file':file,'status':status,'sha256':hashlib.sha256(b).hexdigest(),'bytes':len(b),'attempt':attempt+1})+'\n')
   time.sleep(.6);return b
  except Exception as e:
   with ledger.open('a') as f:f.write(json.dumps({'url':url,'file':file,'error':str(e),'attempt':attempt+1})+'\n')
   if isinstance(e,urllib.error.HTTPError) and e.code in [401,403,429,567]:raise
   if attempt:raise
   time.sleep(2)
def price(code,start,end):
 url='https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get?'+urllib.parse.urlencode({'param':f'{code},day,{start},{end},640,'})
 b=get(url,code+'-'+start[:4]+'.json');d=json.loads(b)
 if d.get('code')!=0:raise ValueError(str(d))
 part=d.get('data',{}).get(code,{})
 if 'day' not in part:raise ValueError('No unadjusted day key: '+code)
 return part['day']
# Query index first to resolve actual end from observations, no future calendar assumption.
index=[]
for start,end in [('2019-01-01','2020-12-31'),('2021-01-01','2022-12-31'),('2023-01-01','2024-12-31'),('2025-01-01','2026-11-01')]:index+=price('sh000001',start,end)
calendar=sorted({r[0] for r in index if '2019-01-01'<=r[0]<='2026-11-01'})
assert calendar and calendar[0]<='2019-01-04'
end=calendar[-1];(out/'calendar.txt').write_text('\n'.join(calendar)+'\n')
print('CALENDAR',len(calendar),calendar[0],end,flush=True)
for i,r in enumerate(selection['selected']):
 code=r['code'].replace('.','');bars=[]
 for start,stop in [('2019-01-01','2020-12-31'),('2021-01-01','2022-12-31'),('2023-01-01','2024-12-31'),('2025-01-01',end)]:
  if r['outDate'] and r['outDate']<start:continue
  bars+=price(code,start,min(stop,r['outDate'] or stop))
 b=get(f'https://finance.sina.com.cn/realstock/company/{code}/hfq.js',code+'-factor.js')
 # JSON parse only, never evaluate downloaded JavaScript.
 text=b.decode('utf-8');data=json.JSONDecoder().raw_decode(text[text.index('{'):])[0]
 if not data.get('data'):raise ValueError('Missing factor: '+code)
 filtered=[v for v in bars if '2019-01-01'<=v[0]<=end and (not r['outDate'] or v[0]<=r['outDate'])]
 if not filtered:raise ValueError('No selected stock history: '+code)
 print(i+1,code,'rawrows',len(filtered),'factors',len(data['data']),flush=True)
print('ACQUISITION_COMPLETE',flush=True)
