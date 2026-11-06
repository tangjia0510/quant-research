# PUBLIC SANITIZED COPY (2026-11-06): machine paths generalized; see provenance/publication_transformations.json.
import json,csv,hashlib,shutil
from pathlib import Path
from datetime import datetime,timezone
BASE=Path(__file__).resolve().parents[1];OLD=BASE.parents[1]/'fin_data/legacy-inputs/source-review'
rows=[];receipts=[]
def date(x):
 x=str(x or '').strip()
 if x in ('','-','nan'):return ''
 if len(x)==8 and x.isdigit():return f'{x[:4]}-{x[4:6]}-{x[6:]}'
 return x[:10]
for name,status in [('sse-active','active'),('sse-delisted','delisted')]:
 p=OLD/(name+'.bin');out=BASE/'raw'/p.name;shutil.copy2(p,out)
 d=json.loads(p.read_bytes());assert len(d['result'])==int(d['pageHelp']['total'])
 for r in d['result']:
  code=r.get('A_STOCK_CODE') or r.get('COMPANY_CODE')
  if not code or not code.startswith(('60','68')):continue
  rows.append(dict(instrument='sh.'+code,exchange='SSE',code=code,name=r.get('COMPANY_ABBR'),ipo_date=date(r.get('LIST_DATE')),delist_date=date(r.get('DELIST_DATE')),status=status,board='STAR' if code.startswith('68') else 'MAIN',industry=r.get('CSRC_CODE_DESC',''),source_file=out.name))
 receipts.append(dict(file=out.name,sha256=hashlib.sha256(out.read_bytes()).hexdigest(),origin=str(p),reused_cached_source=True))
for name,status in [('szse-active','active'),('szse-delisted','delisted')]:
 p=OLD/(name+'.csv');out=BASE/'raw'/p.name;shutil.copy2(p,out)
 raw=OLD/(name+'.bin');shutil.copy2(raw,BASE/'raw'/raw.name)
 for r in csv.DictReader(p.open()):
  code=r.get('A股代码') or r.get('证券代码')
  if not code or not code.startswith(('00','30')):continue
  rows.append(dict(instrument='sz.'+code,exchange='SZSE',code=code,name=r.get('A股简称') or r.get('证券简称'),ipo_date=date(r.get('A股上市日期') or r.get('上市日期')),delist_date=date(r.get('终止上市日期')),status=status,board='CHINEXT' if code.startswith('30') else 'MAIN',industry=r.get('所属行业',''),source_file=out.name))
 receipts.append(dict(file=out.name,sha256=hashlib.sha256(out.read_bytes()).hexdigest(),origin=str(p),reused_cached_source=True))
extras=BASE/'normalized/extras.json'
if extras.exists():rows+=json.loads(extras.read_text())
seen={};conflicts=[]
for r in rows:
 if r['instrument'] in seen:conflicts.append([seen[r['instrument']],r])
 else:seen[r['instrument']]=r
rows=sorted(seen.values(),key=lambda r:r['instrument'])
# Retain all listings; eligible price universe includes delisted since2019.
for name,data in [('security-master.csv',rows),('price-universe.csv',[r for r in rows if not r['delist_date'] or r['delist_date']>='2019-01-01'])]:
 with (BASE/'normalized'/name).open('w') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(data)
(BASE/'catalog.json').write_text(json.dumps(dict(generated_at=datetime.now(timezone.utc).isoformat(),counts={'master':len(rows),'price_universe':sum(not r['delist_date'] or r['delist_date']>='2019-01-01' for r in rows)},sources=receipts,conflicts=conflicts,limitations=['Current plus terminal listings union; not point-in-time eligibility','SSE STAR included; BSE financial/disclosure inferred, official master blocked, aliases effective dates unknown','Cached officialsource receipts retained; see original probe receipts']),ensure_ascii=False,indent=2))
print(len(rows),len(conflicts))
