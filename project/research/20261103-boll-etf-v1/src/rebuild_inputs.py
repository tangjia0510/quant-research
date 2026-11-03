"""Rebuild input caches from immutable provider responses; no network or copied dataset."""
import json,re
import pandas as pd
from bs4 import BeautifulSoup

def rebuild(project,resolve,out):
 def source(name): return resolve(project,'boll-source-'+name.replace('.','-'))
 rows=[]
 for y in [2018,2020,2022,2024,2026]:
  # Response may include extra historical rows; only requested window is admissible.
  start=f'{y}-01-01';end=f'{y+1}-12-31' if y<2026 else '2026-10-30'
  for x in json.loads(source(f'510300-{y}-raw.json').read_text())['data']['sh510300']['day']:
   if start<=x[0]<=end:rows.append(dict(date=x[0],open=float(x[1]),close=float(x[2]),high=float(x[3]),low=float(x[4]),volume_lots=float(x[5]),amount_cny=float(x[8])*10000))
 bars=pd.DataFrame(rows).set_index('date').sort_index()
 first=[x[0] for x in json.loads(source('calendar-2018.json').read_text())['data']['sh000001']['day'] if '2018-01-01'<=x[0]<'2019-01-01']
 dates=sorted(set(first+source('calendar-observed-2019-2026.txt').read_text().splitlines()));dates=[d for d in dates if '2018-01-01'<=d<='2026-10-30']
 assert bars.index.is_unique and bars.index.tolist()==dates,'Calendar/duplicate mismatch'
 soup=BeautifulSoup(source('510300-distributions.html').read_bytes(),'html.parser');events=[];splits=[]
 for table in soup.find_all('table'):
  txt=table.get_text(' ',strip=True)
  for tr in table.find_all('tr'):
   td=[x.get_text(' ',strip=True) for x in tr.find_all('td')]
   if '权益登记日' in txt and len(td)==5 and re.match(r'20\d\d年',td[0]):events.append(dict(record_date=td[1],ex_date=td[2],cash_per_unit=float(re.search(r'现金([0-9.]+)元',td[3]).group(1))/10,pay_date=td[4]))
   if '拆分折算日' in txt and len(td)==4:splits.append(td)
 assert not any('2018-01-01'<=x[1]<='2026-10-30' for x in splits),'Unhandled split'
 dividends=pd.DataFrame(events).sort_values('ex_date');out.mkdir(parents=True,exist_ok=True)
 bars.to_csv(out/'510300-raw-normalized.csv');dividends.to_csv(out/'510300-dividends.csv',index=False);(out/'calendar.csv').write_text('date\n'+'\n'.join(dates)+'\n')
 # The cache bytes are reproduced under locked dependency versions, not assumed.
 import hashlib
 for suffix,name in [('bars','510300-raw-normalized.csv'),('dividends','510300-dividends.csv'),('calendar','calendar.csv')]:
  catalog=json.loads((project/'data-catalog'/f'boll-510300-{suffix}-20261102.json').read_text())
  assert hashlib.sha256((out/name).read_bytes()).hexdigest()==catalog['sha256'],f'Rebuilt input identity differs: {name}'
 return bars,dividends
