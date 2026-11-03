import csv,json,pathlib,hashlib,datetime,collections
p=pathlib.Path(__file__).parent;n=p/'normalized'; ev=p/'supplemental-notices'
rows=list(csv.DictReader((n/'missing-sessions.csv').open())); h={(x['instrument'],x['date']):x for x in csv.DictReader((p/'suspension-evidence-helper/classification.csv').open())}
rec=[]
for f in ['receipts.json','terminal-receipts.json','retry-receipts.json','newspaper-receipts.json']:
 if (ev/f).exists():rec+=json.loads((ev/f).read_text())
for r in rec:
 if r['status']=='downloaded':assert hashlib.sha256(pathlib.Path(r['path']).read_bytes()).hexdigest()==r['sha256']
for r in rows:
 key=(r['instrument'],r['date']);r.update(classification='unresolved',source_url='',evidence_sha256='',note='No price filled; not automatically assumed suspended')
 if key in h:
  z=h[key];r.update(classification=z['classification'],source_url=z['source_url'],note=z['note'])
 for z in rec:
  if z['instrument']==r['instrument'] and z['start']<=r['date']<=z['end']:
   if z['status']=='downloaded':
    cls='documented_delisted_date' if z['reason'].startswith('delisted') else 'issuer_documented_suspension'
    r.update(classification=cls,source_url=z['url'],evidence_sha256=z['sha256'],note=z['reason'])
   elif r['classification']=='unresolved':r.update(source_url=z['url'],note='Primary document search text confirms suspension; local download failed; not yet treated fully verified')
 if key==('sz.000004','2019-11-06'):r['note']='Annual report lists dated suspension/resumption announcements and secondary records agree; direct original not downloaded. Preserve unresolved warmup NaN.'
with (n/'missing-classification.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
summary=dict(created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),original_missing_count=len(rows),counts=dict(collections.Counter(r['classification'] for r in rows)),unresolved=[r for r in rows if r['classification']=='unresolved'],original_quality_sha256=hashlib.sha256((n/'quality.json').read_bytes()).hexdigest(),no_prices_filled=True,acceptance='Limited exploratory registration; original protocol allowed preserved missing observations. No changes to selection, model, candidate, split or outcome gate. Decision before evaluation.',limitations=['Not an independently certified PIT dataset','Mixed vendor factor series and observed index calendar','ST/board price limits and delisting liquidation not fully modeled'])
(n/'missing-classification-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
m=json.loads((n/'metadata.json').read_text());m['missing_classification']=summary;m['quality_summary']['originally_unknown_missing_sessions']=m['quality_summary'].pop('unknown_missing_sessions');m['quality_summary']['unresolved_missing_sessions']=len(summary['unresolved']);m['provenance_plan']='plans/momentum20-v1';(n/'registration-metadata.json').write_text(json.dumps(m,ensure_ascii=False,indent=2));print(json.dumps(summary,ensure_ascii=False,indent=2))
