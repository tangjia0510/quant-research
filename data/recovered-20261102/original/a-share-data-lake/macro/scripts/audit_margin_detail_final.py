import pathlib,json,hashlib,gzip,datetime
import pandas as pd
R=pathlib.Path(__file__).resolve().parents[1];coverage=json.loads((R/'logs/margin-detail-coverage.json').read_text());receipts={};issues=[];parts=[]
for line in (R/'logs/margin-detail-receipts.jsonl').read_text().splitlines():
 x=json.loads(line);receipts[x['file']]=x
for fn,x in receipts.items():
 p=R/fn
 if not p.exists():issues.append({'file':fn,'issue':'missing_raw'});continue
 stored=p.read_bytes();raw=gzip.decompress(stored)
 if hashlib.sha256(stored).hexdigest()!=x['stored_sha256'] or hashlib.sha256(raw).hexdigest()!=x['raw_sha256']:issues.append({'file':fn,'issue':'raw_hash_mismatch'})
for x in coverage:
 p=R/x['file'];d=pd.read_parquet(p);dup=int(d.duplicated(['DATE','SCODE']).sum());wrong=int((~d.DATE.str.startswith(x['month'])).sum());code=int((~d.SCODE.astype(str).str.fullmatch(r'\d{6}')).sum());sha=hashlib.sha256(p.read_bytes()).hexdigest()==x['sha256'];ok=len(d)==x['rows']==x['expected'] and not dup and not wrong and not code and sha
 item={'month':x['month'],'rows':len(d),'duplicate_keys':dup,'wrong_month':wrong,'invalid_code':code,'sha_match':sha,'expected_count_match':len(d)==x['expected'],'market_coverage':d.groupby('MARKET').agg(rows=('SCODE','size'),securities=('SCODE','nunique'),dates=('DATE','nunique'),min_date=('DATE','min'),max_date=('DATE','max')).reset_index().to_dict('records')};parts.append(item)
 if not ok:issues.append({'file':x['file'],'issue':'normalized_validation_failed','detail':item})
obj={'generated_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'state':'all_94_months_validated' if len(parts)==94 and not issues else 'partial_or_issues','raw_receipts_checked':len(receipts),'completed_months':len(parts),'rows':sum(x['rows'] for x in parts),'issues':issues,'partitions':parts,'scope':'Source-reported row counts, raw and Parquet SHA, unique date/security keys and partition dates. Not proof every historically listed instrument or exchange release date was complete. Underlying source may publish markets on different days.'};p=R/'logs/margin-detail-final-audit.json';p.write_text(json.dumps(obj,ensure_ascii=False,indent=2));print({k:v for k,v in obj.items() if k!='partitions'})
