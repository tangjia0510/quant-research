from pathlib import Path
import sys,requests,json,hashlib,datetime,re,shutil
import pandas as pd,numpy as np
from bs4 import BeautifulSoup
R=Path(__file__).resolve().parents[1];S=R/'sources';O=R/'outputs';sys.path.insert(0,str(Path.cwd()/'a-share-data-lake/catalog'));from host_gate import host_gate
p=S/'calendar-2018.json'
if not p.exists():
 with host_gate('tencent'):
  r=requests.get('https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get',params={'param':'sh000001,day,2018-01-01,2019-12-31,640,'},timeout=30)
 p.write_bytes(r.content);p.with_suffix('.receipt.json').write_text(json.dumps({'url':r.url,'status':r.status_code,'sha256':hashlib.sha256(r.content).hexdigest(),'acquired_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()},indent=2));r.raise_for_status()
cal0=[x[0] for x in json.loads(p.read_text())['data']['sh000001']['day'] if '2018-01-01'<=x[0]<'2019-01-01']
cp=Path('a-share-data-lake/reference/normalized/trading-calendar-observed-2019-2026.txt');shutil.copyfile(cp,S/'calendar-observed-2019-2026.txt');cal=sorted(set(cal0+cp.read_text().splitlines()));cal=[d for d in cal if '2018-01-01'<=d<='2026-10-30']
(S/'calendar.csv').write_text('date\n'+'\n'.join(cal)+'\n')
frames={}
for basis in ['raw','hfq']:
 rows=[]
 for p in sorted(S.glob(f'510300-20*-{basis}.json')):
  rc=json.loads(p.with_suffix('.receipt.json').read_text());assert hashlib.sha256(p.read_bytes()).hexdigest()==rc['sha256']
  d=json.loads(p.read_text())['data']['sh510300'];key='day' if basis=='raw' else 'hfqday'
  for x in d[key]:
   if rc['requested_start']<=x[0]<=rc['requested_end']:rows.append(dict(date=x[0],open=float(x[1]),close=float(x[2]),high=float(x[3]),low=float(x[4]),volume_lots=float(x[5]),amount_cny=float(x[8])*10000))
  # Quote snapshots may be newer than source end and are never used.
 f=pd.DataFrame(rows).set_index('date').sort_index();assert f.index.is_unique;assert f.index.tolist()==cal,(basis,len(f),len(cal),set(cal)-set(f.index))
 assert np.isfinite(f.to_numpy()).all();assert (f[['open','close','high','low']]>0).all().all();assert (f.high>=f[['open','close']].max(axis=1)).all();assert(f.low<=f[['open','close']].min(axis=1)).all()
 f.to_csv(S/f'510300-{basis}-normalized.csv');frames[basis]=f
raw=frames['raw'];vwap=raw.amount_cny/(raw.volume_lots*100);assert ((vwap>=raw.low*.99)&(vwap<=raw.high*1.01)).all()
soup=BeautifulSoup((S/'510300-distributions.html').read_bytes(),'html.parser');events=[];splits=[]
for table in soup.find_all('table'):
 txt=table.get_text(' ',strip=True)
 if '权益登记日' in txt:
  for tr in table.find_all('tr'):
   td=[x.get_text(' ',strip=True) for x in tr.find_all('td')]
   if len(td)==5 and re.match(r'20\d\d年',td[0]):events.append(dict(record_date=td[1],ex_date=td[2],cash_per_unit=float(re.search(r'现金([0-9.]+)元',td[3]).group(1))/10,pay_date=td[4]))
 if '拆分折算日' in txt:
  for tr in table.find_all('tr'):
   td=[x.get_text(' ',strip=True) for x in tr.find_all('td')]
   if len(td)==4:splits.append(td)
assert not any('2018-01-01'<=x[1]<='2026-10-30' for x in splits)
ev=pd.DataFrame(events).sort_values('ex_date');ev.to_csv(S/'510300-dividends.csv',index=False)
nav=pd.read_csv('a-share-data-lake/macro/normalized/funds/510300-nav.csv');navdates=set(nav.loc[nav.distribution_note.fillna('').str.contains('分红'),'date']);assert navdates==set(ev.loc[ev.ex_date.between('2019-01-01','2026-10-30'),'ex_date'])
ident=[]
for p in sorted(S.iterdir()):
 if p.is_file():ident.append({'path':str(p.relative_to(R)),'size':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
(O/'input-manifest.json').write_text(json.dumps({'files':ident},indent=2));(O/'data-quality.json').write_text(json.dumps({'rows':len(raw),'first':cal[0],'last':cal[-1],'missing_calendar_rows':0,'duplicate_rows':0,'ohlc_bounds_pass':True,'volume_unit':'source lots *100 verified amount/VWAP within OHLC1% tolerance','dividend_nav_event_dates_match':True,'dividend_events_2019_2026':len(navdates),'splits_as_published':splits,'quote_snapshots_ignored':True,'strategy_results_not_computed':True},indent=2));print((O/'data-quality.json').read_text())
