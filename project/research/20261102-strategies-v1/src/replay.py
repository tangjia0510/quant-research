#!/usr/bin/env python3
"""Offline, raw-input replay adapter. All calculated outputs go to --work-dir."""
import argparse,hashlib,importlib.util,json,sys,re
from pathlib import Path

def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--project-root',required=True);parser.add_argument('--work-dir',required=True);a=parser.parse_args()
 P=Path(a.project_root).resolve();R=Path(__file__).resolve().parents[1];O=Path(a.work_dir).resolve()
 # Protect immutable project payload and every external input from output writes.
 if O==P or not O.is_relative_to(P/'work'):raise ValueError('work-dir must be below project/work')
 spec=importlib.util.spec_from_file_location('portable_project',((P.parent if json.loads((P/'project.json').read_text()).get('skill_source') == '..' else P/'skill')/'scripts/project.py'));mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
 binding=json.loads((R/'evidence/replay-inputs.json').read_text());resolved=mod.resolve(P,binding['catalog_id']);E=Path(resolved['path'])
 if O.is_relative_to(E) or E.is_relative_to(O):raise ValueError('output overlaps external archive')
 if O.exists() and any(O.iterdir()):raise ValueError('Refuse nonempty work-dir; use a fresh replay attempt directory')
 if sha(R/'protocol.json')!=binding['protocol_sha256']:raise ValueError('Protocol identity mismatch')
 for rel,h in binding['code_sha256'].items():
  if sha(R/rel)!=h:raise ValueError('Code identity mismatch: '+rel)
 for x in binding['inputs']:
  p=E/x['path']
  if not p.is_file() or p.stat().st_size!=x['bytes'] or sha(p)!=x['sha256']:raise ValueError('Raw input identity mismatch: '+x['path'])
 import pandas as pd,numpy as np
 from bs4 import BeautifulSoup
 O.mkdir(parents=True,exist_ok=True)
 cal0=[x[0] for x in json.loads((E/'sources/calendar-2018.json').read_text())['data']['sh000001']['day'] if '2018-01-01'<=x[0]<'2019-01-01']
 cal=sorted(set(cal0+(E/'sources/calendar-observed-2019-2026.txt').read_text().splitlines()));cal=[d for d in cal if '2018-01-01'<=d<='2026-10-30'];rows=[]
 # Exact original normalization; no already-normalized external file consumed.
 for x in binding['inputs']:
  if not re.fullmatch(r'sources/510300-20\d\d-raw.json',x['path']):continue
  p=E/x['path'];receipt=json.loads(p.with_suffix('.receipt.json').read_text())
  if sha(p)!=receipt['sha256']:raise ValueError('Raw receipt mismatch')
  for z in json.loads(p.read_text())['data']['sh510300']['day']:
   if receipt['requested_start']<=z[0]<=receipt['requested_end']:rows.append(dict(date=z[0],open=float(z[1]),close=float(z[2]),high=float(z[3]),low=float(z[4]),volume_lots=float(z[5]),amount_cny=float(z[8])*10000))
 b=pd.DataFrame(rows).set_index('date').sort_index();assert b.index.is_unique and b.index.tolist()==cal
 assert np.isfinite(b.to_numpy()).all() and (b.volume_lots>0).all() and (b.high>b.low).all()
 b.to_csv(O/'510300-raw-normalized.csv')
 soup=BeautifulSoup((E/'sources/510300-distributions.html').read_bytes(),'html.parser');events=[];splits=[]
 for table in soup.find_all('table'):
  txt=table.get_text(' ',strip=True)
  for tr in table.find_all('tr'):
   td=[x.get_text(' ',strip=True) for x in tr.find_all('td')]
   if '权益登记日' in txt and len(td)==5 and re.match(r'20\d\d年',td[0]):events.append(dict(record_date=td[1],ex_date=td[2],cash_per_unit=float(re.search(r'现金([0-9.]+)元',td[3]).group(1))/10,pay_date=td[4]))
   if '拆分折算日' in txt and len(td)==4:splits.append(td)
 assert not any('2018-01-01'<=x[1]<='2026-10-30' for x in splits)
 e=pd.DataFrame(events).sort_values('ex_date');e.to_csv(O/'510300-dividends.csv',index=False)
 for rel,h in binding['derived_hashes'].items():
  if sha(O/Path(rel).name)!=h:raise ValueError('Reconstructed normalization differs: '+rel)
 # Match original CSV parse step (floating point round-trip included).
 b=pd.read_csv(O/'510300-raw-normalized.csv',index_col='date');e=pd.read_csv(O/'510300-dividends.csv')
 sys.path.insert(0,str(R/'src/legacy'));from strategy import signals,simulate
 from evaluate import metrics,hac
 sig,tr=signals(b,e);sig.to_csv(O/'monthly-signals.csv',index=False);tr.to_csv(O/'signal-total-return-index.csv');results=[]
 for bp in [0,10,30]:
  monthly={}
  for kind in ['strategy','benchmark']:
   d,t,k=simulate(b,e,sig,kind,bp);stem=f'{kind}-{bp}bp';d.to_csv(O/f'{stem}-daily.csv',index=False);t.to_csv(O/f'{stem}-trades.csv',index=False);k.to_csv(O/f'{stem}-blocked.csv',index=False)
   results.append(dict(kind=kind,total_friction_bp=bp,blocked_orders=len(k),**metrics(d,t)))
   di=d.set_index(pd.to_datetime(d.date));end=di.equity.resample('ME').last();mr=end.pct_change(fill_method=None);mr.iloc[0]=end.iloc[0]/100000-1;monthly[kind]=mr
  results.append(dict(kind='active_monthly_hac',total_friction_bp=bp,**hac(monthly['strategy']-monthly['benchmark'])))
 expected=json.loads((R/'evidence/outputs/summary.json').read_text())['results']
 def compare(x,y,path='results'):
  if isinstance(x,dict):
   assert x.keys()==y.keys(),path
   for k in x:compare(x[k],y[k],path+'.'+k)
  elif isinstance(x,list):
   assert len(x)==len(y),path
   for i,(u,v) in enumerate(zip(x,y)):compare(u,v,path+f'[{i}]')
  elif isinstance(x,(int,float)) and not isinstance(x,bool):assert np.isclose(x,y,rtol=1e-11,atol=1e-11), (path,x,y)
  else:assert x==y,(path,x,y)
 compare(results,expected)
 out=dict(replay_status='verified_against_frozen_results',results=results,raw_input_count=len(binding['inputs']),normalized_data_rebuilt=True,old_results_consumed_for_calculation=False,comparison_tolerance=1e-11)
 (O/'summary.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({'status':out['replay_status'],'output':str(O),'scenarios':6,'rows':len(b)},indent=2))
if __name__=='__main__':main()
