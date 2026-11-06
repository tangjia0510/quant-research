#!/usr/bin/env python3
"""Local whole-market normalized integrity validation, no price fixing/network."""
import csv,datetime as dt,gzip,hashlib,io,json,math
from collections import Counter
from pathlib import Path
M=Path(__file__).resolve().parents[1];manifest=M/'manifests/universe-sharded-with-bse.csv';expected={r['instrument'].replace('.','') for r in csv.DictReader(manifest.open())}
errors=[];states=Counter();latest=Counter();rows=0;files=0;sourcehashes=[]
for p in sorted((M/'status').glob('*.json')):
 s=json.loads(p.read_text());code=s['instrument']
 if code not in expected:continue
 states[s['state']]+=1;latest[s.get('last_date') or '<none>']+=1
 f=M/s['normalized_file'];z=f.read_bytes();b=gzip.decompress(z)
 for label,want,actual in [('gzip_sha',s['normalized_gzip_sha256'],hashlib.sha256(z).hexdigest()),('csv_sha',s['normalized_csv_sha256'],hashlib.sha256(b).hexdigest())]:
  if want!=actual:errors.append({'instrument':code,'kind':label})
 data=list(csv.DictReader(io.StringIO(b.decode())));dates=[r['date'] for r in data];rows+=len(data);files+=1
 if len(data)!=s['row_count']:errors.append({'instrument':code,'kind':'row_count'})
 if dates!=sorted(set(dates)):errors.append({'instrument':code,'kind':'date_order_unique'})
 if dates and (dates[0]!=s['first_date'] or dates[-1]!=s['last_date']):errors.append({'instrument':code,'kind':'date_bounds'})
 for r in data:
  if r['instrument']!=code:errors.append({'instrument':code,'kind':'wrong_instrument','date':r['date']})
  if not math.isclose(float(r['volume_lots'])*100,float(r['volume_shares']),rel_tol=1e-12,abs_tol=1e-6):errors.append({'instrument':code,'kind':'normalized_volume_units','date':r['date']})
  if r['amount_10k_cny'] and not math.isclose(float(r['amount_10k_cny'])*10000,float(r['amount_cny']),rel_tol=1e-12,abs_tol=.01):errors.append({'instrument':code,'kind':'normalized_amount_units','date':r['date']})
 if code.startswith(('sh688','sh689')) and s.get('source_volume_to_shares_multiplier')!=1:errors.append({'instrument':code,'kind':'STAR_unit_contract'})
 sourcehashes.append({'instrument':code,'status_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'csv_sha256':hashlib.sha256(b).hexdigest()})
 if files%500==0:print(files,rows,len(errors),flush=True)
out={'generated_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'expected':len(expected),'audited':files,'not_yet_audited':len(expected)-files,'rows':rows,'status_counts':dict(states),'last_date_distribution':dict(sorted(latest.items())),'errors':errors,'source_hashes':sourcehashes,'validation_scope':['Full gzip+CSV digest, row count, code/date order/bounds, normalized unit identities, STAR raw unit contract','Source economic correctness, PIT rights, suspension completeness not certified','Needs-review rows retained, not silently repaired']}
p=M/'final-integrity-audit.json';tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');tmp.replace(p);print(json.dumps({k:v for k,v in out.items() if k not in ['source_hashes','last_date_distribution']},ensure_ascii=False),flush=True)
