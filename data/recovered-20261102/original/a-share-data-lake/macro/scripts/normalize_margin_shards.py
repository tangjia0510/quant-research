import pathlib,json,re,gzip,hashlib,datetime
import pandas as pd
R=pathlib.Path(__file__).resolve().parents[1];O=R/'normalized/margin_detail_shards';O.mkdir(exist_ok=True);groups={};reports=[]
for p in (R/'raw/margin_detail').glob('*.json.gz'):
 m=re.fullmatch(r'(\d{4}-\d{2}-d\d{2})-(\d{4})\.json\.gz',p.name)
 if m:groups.setdefault(m.group(1),{})[int(m.group(2))]=p
for key,files in groups.items():
 if 1 not in files:continue
 first=json.loads(gzip.decompress(files[1].read_bytes()))['result'];pages=int(first['pages']);expected=int(first['count'])
 if not all(i in files for i in range(1,pages+1)):continue
 out=O/(key+'.parquet');rows=[]
 for i in range(1,pages+1):rows+=json.loads(gzip.decompress(files[i].read_bytes()))['result']['data']
 d=pd.DataFrame(rows);dup=int(d.duplicated(['DATE','SCODE']).sum());ok=len(d)==expected and dup==0
 if ok:
  tmp=out.with_suffix('.tmp.parquet');d.to_parquet(tmp,index=False);tmp.replace(out)
 reports.append({'shard':key,'state':'complete_api_response' if ok else 'validation_failed','rows':len(d),'expected_count':expected,'pages':pages,'duplicates':dup,'min_date':d.DATE.min(),'max_date':d.DATE.max(),'file':str(out.relative_to(R)) if ok else None,'sha256':hashlib.sha256(out.read_bytes()).hexdigest() if ok else None})
(R/'logs/margin-shard-coverage.json').write_text(json.dumps({'generated_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'shards':reports,'note':'Overlaps monthly aggregates; never concatenate shard and month files together. Amounts CNY, quantity shares, closingprice CNY/share, ZDF vendor percent.'},ensure_ascii=False,indent=2));print(len(reports),sum(x['rows'] for x in reports))
