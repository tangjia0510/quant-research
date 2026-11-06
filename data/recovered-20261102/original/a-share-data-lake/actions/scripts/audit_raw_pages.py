import json,hashlib,datetime
from pathlib import Path
B=Path(__file__).resolve().parents[1];out={}
for folder in sorted((B/'raw').glob('eastmoney_*')):
 issues=[];times=[];pages=0;rows=0;declared=set();page_counts=set()
 for receipt in sorted(folder.glob('page-*.receipt.json')):
  r=json.loads(receipt.read_text());payload=receipt.with_name(receipt.name.replace('.receipt.json','.json'))
  b=payload.read_bytes();pages+=1
  if hashlib.sha256(b).hexdigest()!=r['sha256']:issues.append([payload.name,'sha_mismatch'])
  if r.get('bytes') is not None and len(b)!=r['bytes']:issues.append([payload.name,'byte_mismatch'])
  times.append(r.get('retrieved_at',r.get('at','')))
  d=json.loads(b).get('result',{});rows+=len(d.get('data',[]));declared.add(d.get('count'));page_counts.add(d.get('pages'))
 out[folder.name]={'pages':pages,'rows':rows,'source_declared_counts':sorted(declared,key=str),'source_declared_page_counts':sorted(page_counts,key=str),'retrieval_min':min(times) if times else None,'retrieval_max':max(times) if times else None,'issues':issues}
r={'audited_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'datasets':out};(B/'catalog/raw-page-integrity.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));print(json.dumps(r))
