import gzip,hashlib,json,datetime as dt
from pathlib import Path
M=Path(__file__).resolve().parents[1];seen={};errors=[];size=0
for p in sorted((M/'status').glob('*.json')):
 for r in json.loads(p.read_text()).get('raw_receipts',[]):
  key=r['raw_file']
  if key in seen:
   if seen[key]!=r['sha256']:errors.append({'file':key,'kind':'conflicting_expected_sha'})
   continue
  b=gzip.decompress((M/key).read_bytes());size+=len(b);h=hashlib.sha256(b).hexdigest();seen[key]=h
  if h!=r['sha256']:errors.append({'file':key,'kind':'digest_mismatch'})
  if json.loads(b).get('code')!=0:errors.append({'file':key,'kind':'source_response_code'})
out={'generated_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'unique_raw_files':len(seen),'uncompressed_bytes':size,'errors':errors,'validation_scope':'All terminal stock raw response payload SHA256 against per-stock source receipts; JSON source response code0; no data repair'}
(M/'raw-integrity-audit.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out))
