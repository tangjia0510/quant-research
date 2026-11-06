import pathlib,json,hashlib,gzip,datetime
R=pathlib.Path(__file__).resolve().parents[1];reports=[]
for market in ['sse','szse']:
 p=R/f'logs/{market}-margin-bulk-receipts.jsonl'
 if not p.exists():continue
 recs={}
 for line in p.read_text().splitlines():
  x=json.loads(line);recs[x['date']]=x
 bad=[]
 for day,x in recs.items():
  rawp=R/x['raw_file'];n=R/x['normalized_file']
  if not rawp.exists() or not n.exists():bad.append({'date':day,'issue':'missing_file'});continue
  b=rawp.read_bytes();raw=gzip.decompress(b) if market=='sse' else b
  if hashlib.sha256(b).hexdigest()!=x['stored_sha256'] or hashlib.sha256(raw).hexdigest()!=x['raw_sha256'] or hashlib.sha256(n.read_bytes()).hexdigest()!=x['normalized_sha256']:bad.append({'date':day,'issue':'sha_mismatch'})
 reports.append({'exchange':market.upper(),'receipt_dates_checked':len(recs),'reported_rows':sum(x['rows'] for x in recs.values()),'earliest_date':min(recs,default=None),'latest_date':max(recs,default=None),'issues':bad})
gap=R/'logs/sse-margin-official-api-gapfill.json'
if gap.exists():
 x=json.loads(gap.read_text());bad=[]
 for field,shafield in [('raw_file','raw_sha256'),('normalized_file','normalized_sha256')]:
  if hashlib.sha256((R/x[field]).read_bytes()).hexdigest()!=x[shafield]:bad.append({'issue':'sha_mismatch','file':x[field]})
 reports.append({'exchange':'SSE_official_API_gapfill','receipt_dates_checked':1,'reported_rows':x['rows'],'earliest_date':x['date'],'latest_date':x['date'],'issues':bad})
terminal=all(json.loads((R/f'logs/{m}-margin-bulk-progress.json').read_text())['state']!='running' for m in ['sse','szse'])
obj={'generated_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'state':'terminal_first_pass_audit' if terminal else 'snapshot_of_running_collectors','sources':reports,'scope':'Receipt SHA of original/decompressed raw, stored raw, normalized CSV. Not a claim historical values or release timestamps independently verified.'};(R/'logs/official-margin-raw-hash-audit.json').write_text(json.dumps(obj,indent=2));print(reports)
