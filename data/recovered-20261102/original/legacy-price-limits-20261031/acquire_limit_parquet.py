# PUBLIC SANITIZED COPY (2026-11-06): machine paths generalized; see provenance/publication_transformations.json.
import requests,json,time,hashlib,concurrent.futures
from pathlib import Path
B=Path('fin_data/legacy-work/status_limits');D=Path('fin_data/legacy-inputs/hf_limits_raw');D.mkdir(exist_ok=True)
j=json.load(open('fin_data/legacy-inputs/hfparquet.json'));(B/'hf_parquet_manifest.json').write_text(json.dumps(j,indent=2))
def get(x):
 t=time.time();p=D/x['filename'];r=requests.get(x['url'],stream=True,timeout=(15,120));r.raise_for_status();h=hashlib.sha256();n=0
 with p.open('wb') as f:
  for b in r.iter_content(4*1024*1024):f.write(b);h.update(b);n+=len(b)
 assert n==x['size'],(n,x['size']);v={**x,'sha256':h.hexdigest(),'download_seconds':time.time()-t};print(v,flush=True);return v
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:o=list(ex.map(get,j['parquet_files']))
(B/'hf_download_manifest.json').write_text(json.dumps(o,indent=2))
