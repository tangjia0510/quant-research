import csv,json,hashlib,datetime,collections
from pathlib import Path
B=Path(__file__).resolve().parents[1];u=B/'catalog/universe-batches/003-frozen-combined-5917.csv';universe=list(csv.DictReader(u.open()));ids={r['code']+'.'+r['exchange'].upper():r['instrument'] for r in universe}
# Derive explicit provider key from canonical instrument instead of guessing provider market field.
ids={r['instrument'].split('.')[1]+'.'+r['instrument'].split('.')[0].upper():r['instrument'] for r in universe}
p=B/'normalized/equity-all.csv';out=B/'normalized/equity-universe.csv';counts=collections.Counter();future=0;recent=0;dates=[];excluded=0
with p.open() as src,out.open('w',newline='') as dst:
 reader=csv.DictReader(src);writer=csv.DictWriter(dst,fieldnames=['instrument']+reader.fieldnames);writer.writeheader()
 for r in reader:
  instrument=ids.get(r['SECUCODE'])
  if instrument is None:excluded+=1;continue
  writer.writerow({'instrument':instrument,**r});counts[instrument]+=1;day=r['END_DATE'][:10];dates.append(day);future+=day>'2026-10-30';recent+='2019-01-01'<=day<='2026-10-30'
r={'generated_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'universe_sha256':hashlib.sha256(u.read_bytes()).hexdigest(),'output_sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'target_securities':len(ids),'matched_securities':len(counts),'matched_rows':sum(counts.values()),'excluded_nonmatching_rows':excluded,'events_2019_through_cutoff':recent,'future_effective_rows_after_cutoff':future,'first_effective':min(dates),'last_effective':max(dates),'missing_securities':sorted(set(ids.values())-set(counts)),'limits':['Exact current code.exchange match only; BSE historical aliases not automatically stitched.','Source includes non-A instruments; excluded rows retained in equity-all.csv.','Current snapshot is not vintage history; effective and announcement date both required for as-of use.']}
(B/'catalog/equity-universe.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));print(json.dumps({k:v for k,v in r.items() if k not in ['missing_securities','limits']}))
