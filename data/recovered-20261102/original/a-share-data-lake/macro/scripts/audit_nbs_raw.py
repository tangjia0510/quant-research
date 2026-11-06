import pathlib,json,hashlib,datetime
R=pathlib.Path(__file__).resolve().parents[1];rr=json.loads((R/'logs/nbs-receipts.json').read_text());bad=[]
for x in rr:
 p=R/x['file']
 if not p.exists() or hashlib.sha256(p.read_bytes()).hexdigest()!=x['sha256']:bad.append(x['file'])
cs=json.loads((R/'logs/nbs-coverage.json').read_text());obj={'generated_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'raw_receipts_checked':len(rr),'unique_raw_files':len({x['file'] for x in rr}),'hash_mismatches_or_missing':bad,'catalog_leaves_attempted':len(cs),'catalog_leaves_with_rows':sum(x['rows']>0 for x in cs),'raw_catalog_reported_rows':sum(x['rows'] for x in cs),'frequency_row_counts':{f:sum(x['rows'] for x in cs if x['frequency']==f) for f in ['monthly','quarterly','annual']},'scope':'All monthly/quarterly national branches, selected annual economy/finance branches; not all NBS local/regional datasets or vintage archives','errors':json.loads((R/'logs/nbs-failures.json').read_text())};(R/'logs/nbs-final-raw-audit.json').write_text(json.dumps(obj,ensure_ascii=False,indent=2));print(obj)
