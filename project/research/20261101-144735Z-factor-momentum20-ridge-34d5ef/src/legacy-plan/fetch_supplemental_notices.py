import pathlib,json,urllib.request,hashlib,datetime,concurrent.futures
root=pathlib.Path(__file__).parent
out=root/'supplemental-notices';out.mkdir(exist_ok=True)
def fetch(t):
 code,start,end,url,reason=t
 name=code+'_'+start+('.pdf' if '.pdf' in url.lower() else '.html');p=out/name
 try:
  b=urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'}),timeout=35).read()
  if name.endswith('.pdf') and not b.startswith(b'%PDF'):raise ValueError('not pdf')
  p.write_bytes(b)
  return dict(instrument=code,start=start,end=end,url=url,reason=reason,path=str(p),sha256=hashlib.sha256(b).hexdigest(),bytes=len(b),retrieved_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),status='downloaded')
 except Exception as e:return dict(instrument=code,start=start,end=end,url=url,reason=reason,status='failed',error=repr(e))
rows=list(concurrent.futures.ThreadPoolExecutor(max_workers=4).map(fetch,json.loads((root/'supplemental-notices.json').read_text())))
(out/'receipts.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
print(json.dumps(rows,ensure_ascii=False,indent=2))
