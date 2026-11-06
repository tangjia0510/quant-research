"""Coverage-only source union. Never merge, overwrite or reconcile financial values."""
from pathlib import Path
import csv,gzip,json,datetime,collections
import pyarrow.parquet as pq
from margin_snapshot_selection import select_latest
R=Path(__file__).resolve().parents[1]
FIELDS=['financing_balance_cny','financing_buy_cny','financing_repay_cny','lending_quantity','lending_sell_quantity','lending_repay_quantity','lending_balance_cny','combined_margin_balance_cny']
VM=['RZYE','RZMRE','RZCHE','RQYL','RQMCL','RQCHL','RQYE','RZRQYE']
SM=['本日融资余额(元)','本日融资买入额(元)','本日融资偿还额(元)','本日融券余量','本日融券卖出量','本日融券偿还量',None,None]
ZM=['融资余额(元)','融资买入额(元)',None,'融券余量(股/份)','融券卖出量(股/份)',None,'融券余额(元)','融资融券余额(元)']
markets={};sources={};files=[];snapshots=select_latest(R)
def accept(m,date,code,row,fields,source):
 g=markets.setdefault(m,{}).setdefault(date,{})
 mask=sum(1<<i for i,f in enumerate(fields) if f and row.get(f) not in (None,'','--','-'))
 g[code]=g.get(code,0)|mask
 s=sources.setdefault(source,{}).setdefault(m,{}).setdefault(date,{'rows':0,'nonnull_field_rows':[0]*len(FIELDS)})
 s['rows']+=1
 for i in range(len(FIELDS)):s['nonnull_field_rows'][i]+=bool(mask&(1<<i))
for market,folder,cfield,mapping in [('SSE','sse_margin_bulk','标的证券代码',SM),('SZSE','szse_margin_bulk','证券代码',ZM)]:
 for p in sorted((R/'macro/normalized'/folder).glob('*.csv.gz')):
  if '.tmp' in p.name:continue
  with gzip.open(p,'rt',encoding='utf-8-sig',newline='') as f:
   for row in csv.DictReader(f):accept(market,row['date'][:10],row[cfield].zfill(6),row,mapping,'official_daily')
  files.append(str(p.relative_to(R)))
for p in sorted((R/'macro/normalized/official_margin_gapfills').glob('sse-*.csv.gz')):
 with gzip.open(p,'rt',encoding='utf-8-sig',newline='') as f:
  for row in csv.DictReader(f):accept('SSE',row['date'][:10],row['标的证券代码'].zfill(6),row,SM,'official_API_gapfill')
 files.append(str(p.relative_to(R)))
late_manifest=R/'macro/logs/szse-oct30-export-direct-refresh.json'
if late_manifest.exists():
 late=json.loads(late_manifest.read_text());p=R/'macro'/late['normalized_file']
 if late.get('state')=='downloaded_pure_data_parsed' and __import__('hashlib').sha256(p.read_bytes()).hexdigest()==late['normalized_sha256']:
  with p.open(encoding='utf-8-sig',newline='') as f:
   for row in csv.DictReader(f):accept('SZSE',row['date'][:10],row['证券代码'].zfill(6),row,ZM,'official_latest_export')
  files.append(str(p.relative_to(R)))
for p in sorted((R/'macro/normalized/margin_detail').glob('*.parquet')):
 for row in pq.read_table(p,columns=['DATE','SCODE','MARKET']+VM).to_pylist():
  if row['DATE'][:10] in snapshots:continue
  market={'融资融券_沪证':'SSE','融资融券_深证':'SZSE','融资融券_北证':'BSE'}.get(row['MARKET'],row['MARKET'])
  accept(market,row['DATE'][:10],str(row['SCODE']).zfill(6),row,VM,'vendor_completed_month')
 files.append(str(p.relative_to(R)))
for day,snap in snapshots.items():
 for row in pq.read_table(snap['file'],columns=['DATE','SCODE','MARKET']+VM).to_pylist():
  market={'融资融券_沪证':'SSE','融资融券_深证':'SZSE','融资融券_北证':'BSE'}.get(row['MARKET'],row['MARKET'])
  accept(market,row['DATE'][:10],str(row['SCODE']).zfill(6),row,VM,'vendor_latest_day_snapshot')
 files.append(str(snap['file'].relative_to(R)))
result={}
for market,dates in markets.items():
 daily=[]
 for date,keys in sorted(dates.items()):
  counts={f:sum(bool(mask&(1<<i)) for mask in keys.values()) for i,f in enumerate(FIELDS)}
  daily.append({'date':date,'unique_security_keys':len(keys),'nonnull_union_field_key_counts':counts})
 result[market]={'observed_dates':len(daily),'earliest':daily[0]['date'],'latest':daily[-1]['date'],'unique_security_date_keys':sum(x['unique_security_keys'] for x in daily),'daily':daily,'field_totals':{f:sum(x['nonnull_union_field_key_counts'][f] for x in daily) for f in FIELDS}}
source_summary={s:{m:{'observed_dates':len(ds),'earliest':min(ds),'latest':max(ds),'rows':sum(x['rows'] for x in ds.values()),'fields_with_nonnull_values':[f for i,f in enumerate(FIELDS) if any(x['nonnull_field_rows'][i] for x in ds.values())]} for m,ds in ms.items()} for s,ms in sources.items()}
d={'generated_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'markets':result,'latest_day_replacement_manifests':[x['manifest'] for x in snapshots.values()],'source_summary':source_summary,'files':files,'scope':'Unique market/date/security availability union for eight explicitly mapped fields. Vendor completed-month files plus official daily and explicitly separated API gapfill files only; excludes overlapping official-monthly and vendor-shard derivatives. Validated latest full-day snapshots replace the same vendor DATE; deltas excluded. No values merged; conflicts not tested globally; counts not complete eligibility proof.','source_date_field_units':'CNY monetary values; lending quantities shares/units (funds included).','full_2019_latest_complete':False}
p=R/'catalog/margin-union-coverage.json';tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(d,ensure_ascii=False,indent=2));tmp.replace(p)
print(json.dumps(source_summary,ensure_ascii=False))
