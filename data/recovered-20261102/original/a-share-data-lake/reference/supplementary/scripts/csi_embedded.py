import urllib.request,urllib.parse,json,time,hashlib,re
from pathlib import Path
from datetime import datetime,timezone
B=Path(__file__).resolve().parents[1];R=B/'raw/csi-embedded';R.mkdir(exist_ok=True);known={x.get('url') for x in json.load(open(B.parent/'csi-history-receipts.json'))};jobs=[]
for p in (B.parent/'raw/csi-history').glob('detail*'):
 d=json.load(open(p))['data']
 for u in re.findall(r'href=[\"\x27]([^\"\x27]+)',d.get('content','')):
  if u.startswith('https://oss-ch.csindex.com.cn/') and re.search(r'\.(xlsx?|pdf)(?:\?|$)',u):
   u=urllib.parse.quote(u,safe=':/?=&%')
   if u not in known:jobs.append((str(d['id']),u));known.add(u)
rec=[]
for i,(nid,u) in enumerate(jobs):
 time.sleep(1);ext=u.split('?')[0].split('.')[-1];p=R/f'{nid}-{i}.{ext}';r=dict(notice_id=nid,url=u,file=str(p.relative_to(B)),acquired_at=datetime.now(timezone.utc).isoformat())
 try:
  b=urllib.request.urlopen(u,timeout=25).read();p.write_bytes(b);r.update(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
 except Exception as e:r['error']=str(e)
 rec.append(r);(B/'csi-embedded-receipts.json').write_text(json.dumps(rec,indent=2));print(i+1,len(jobs),nid,r.get('bytes',r.get('error')),flush=True)
