import pathlib,json,datetime,csv
R=pathlib.Path(__file__).resolve().parents[1];today=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).date();rows=[]
def add(name,date,file,frequency,caveat=''):
 try:lag=(today-datetime.date.fromisoformat(date[:10])).days if date else None
 except ValueError:lag=None
 rows.append({'series':name,'latest_available_observation_or_period_end':date,'age_calendar_days':lag,'observation_age_is_not_update_delay':True,'frequency':frequency,'file':file,'caveat':caveat})
for name in ['shibor_daily','lpr','chinabond_yield_curves','margin_accounts','northbound_total_disclosure_aware','shanghai_connect_disclosure_aware','shenzhen_connect_disclosure_aware']:
 p=R/'normalized'/(name+'.csv')
 if not p.exists():continue
 rr=list(csv.DictReader(p.open()));dates=[r.get('date') or r.get('TRADE_DATE') or r.get('STATISTICS_DATE') for r in rr];dates=[x[:10] for x in dates if x]
 add(name,max(dates) if dates else None,str(p.relative_to(R)),'monthly' if name=='lpr' else 'daily','Northbound row date is not availability of daily net flow after2024-08-19' if 'disclosure' in name else ('Vendor aggregate date only; component-market cutoffs not exposed/verified' if name=='margin_accounts' else ''))
for p in (R/'normalized').glob('csi_benchmark_*.csv'):
 rr=list(csv.DictReader(p.open()));add(p.stem,max(r['date'] for r in rr),str(p.relative_to(R)),'daily','price index; flagged boundary anomaly and retrospective history retained')
for p in (R/'normalized').glob('hkex_northbound_*.csv'):
 add(p.stem,p.stem[-10:],str(p.relative_to(R)),'quarterly','Published on fifth Northbound trading day after quarter end; no daily holdings inference')
fp=R/'logs/fund-receipts.jsonl';fund={}
if fp.exists():
 for line in fp.read_text().splitlines():
  d=json.loads(line);fund[d['code']]=d
for code,d in fund.items():
 add('fund_nav_'+code,d['nav_max_date'],f'normalized/funds/{code}-nav.csv','fund-specific NAV disclosure','Retrieved listing union includes aliases and inactive instruments; suspended/overseas funds may have disclosure lag; latest source data need not equal latest A-share trading day')
 rows[-1]['retrieved_at_utc']=d['retrieved_at_utc'];rows[-1]['data_kind']=d.get('data_kind','unit_nav')
 if d.get('data_kind')=='money_fund_income':
  add('fund_money_income_'+code,d.get('money_income_max_date'),f'normalized/funds/{code}-money-income.csv','fund-specific income disclosure','Per10000unit income and seven-day annualized yield are not unit NAV or automatically daily total-return data');rows[-1]['retrieved_at_utc']=d['retrieved_at_utc']
p=R/'logs/nbs-normalization.json'
if p.exists():
 d=json.loads(p.read_text());add('NBS_all_current_snapshot',d.get('max_nonnull_period_end'),'normalized/nbs_national_normalized.parquet','monthly/quarterly/annual','Non-null reported-period endpoint, not publication timestamp. Individual indicators have different latest dates.')
cp=R/'logs/margin-detail-coverage.json'
if cp.exists():
 for c in json.loads(cp.read_text()):
  if c['status']=='complete_api_response':add('margin_detail_'+c['month'],c['max_date'][:10],c['file'],'daily','Monthly partition completed and count/unique-key validated; includes stock and fund securities')
for market in ['sse','szse']:
 q=R/f'logs/{market}-margin-bulk-progress.json'
 if q.exists():
  c=json.loads(q.read_text());add(market+'_official_margin',c['latest_date'],f'normalized/{market}_margin_bulk','daily','Completed daily exports only; same-date availability differs across exchanges')
q=R/'logs/fund-nav-repair-501023.json'
if q.exists():
 c=json.loads(q.read_text());add('fund_nav_501023_API_supplement',c['max_date'],c['file'],'fund-specific NAV disclosure','Separate source variant; does not imply active fund today')
q=R/'logs/fund-alias-retrieval.json'
if q.exists():
 for c in json.loads(q.read_text()):
  add('fund_money_income_alias_'+c['exchange_subscription_code'],c['max_date'],c['normalized_file'],'fund-specific income disclosure',c['identity_caveat']);rows[-1]['retrieved_at_utc']=c['retrieved_at_utc']
q=R/'logs/fund-holdings-audit.json'
if q.exists():
 add('selected_9_ETF_top10_holdings','2026-09-30','normalized/fund_holdings','quarterly','2570rows in257quarter groups, ten reported holdings each; not full portfolios; report period not publication date')
q=R/'logs/fund-late-observations.json'
if q.exists():
 for c in json.loads(q.read_text())['files']:
  add('fund_late_observations_'+c['code'],c['max_date'],c['file'],'fund-specific disclosure','Source-field-specific observations after initial Oct30 cutoff; weekend money-fund income is not an exchange trading day');rows[-1]['retrieved_at_utc']=c['retrieved_at_utc']
refreshes=sorted((R/'logs').glob('margin-latest-refresh-*.json'))
if refreshes:
 c=json.loads(refreshes[-1].read_text());v=c.get('sources',{}).get('vendor',{})
 if v.get('state')=='count_key_date_validated':
  for market in v['markets']:
   add('margin_latest_refresh_'+market['MARKET'],market['latest_date'][:10],v['files'][0]['file'],'daily','Latest verified day snapshot replaces this date only; historical month remains immutable. Not all markets necessarily published.');rows[-1]['retrieved_at_utc']=c['generated_at_utc']
q=R/'logs/szse-oct30-export-direct-refresh.json'
if q.exists():
 c=json.loads(q.read_text())
 if c.get('state')=='downloaded_pure_data_parsed':
  add('szse_official_margin_latest_refresh','2026-10-30',c.get('canonical_parquet_file',c['normalized_file']),'daily','Official XLSX published2118rows while JSON metadata stillzero; new day extends historicalOct29 cutoff');rows[-1]['retrieved_at_utc']=c['retrieved_at_utc']
receipt_specs=[('rates-receipts.json','rates'),('yield-receipts.json','yield'),('flow-receipts.json','flows'),('hkex-holdings-receipts.json','hkex'),('csi-benchmark-receipts.json','csi'),('nbs-receipts.json','nbs')]
receipt_groups={}
for fn,k in receipt_specs:
 q=R/'logs'/fn
 if q.exists():receipt_groups[k]=json.loads(q.read_text())
for row in rows:
 name=row['series'];group=None;match=lambda x:True
 if name=='shibor_daily':group='rates';match=lambda x:'shibor-' in x['file']
 elif name=='lpr':group='rates';match=lambda x:'lpr-' in x['file']
 elif name=='chinabond_yield_curves':group='yield'
 elif 'disclosure_aware' in name or name=='margin_accounts':group='flows';match=lambda x:name.replace('_disclosure_aware','') in x['file']
 elif name.startswith('csi_benchmark_'):group='csi';match=lambda x:name[-6:] in x['file']
 elif name.startswith('hkex_northbound_'):group='hkex';match=lambda x:name.replace('hkex_northbound_','').replace('_','-') in x['file']
 elif name.startswith('NBS'):group='nbs'
 times=[x.get('retrieved_at_utc') for x in receipt_groups.get(group,[]) if match(x) and x.get('retrieved_at_utc')]
 if times:row['source_retrieval_range_utc']=[min(times),max(times)]
 row['expected_latest_publicly_available_verified']=None
 row['expected_latest_note']='No independent release-calendar completeness assertion; compare reported observation with source-specific schedule.'
out={'generated_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'latest_completed_A_share_date_target':'2026-10-30','observation_age_not_publication_lag':True,'age_calendar_timezone':'Asia/Shanghai','as_of_date_local':today.isoformat(),'series':rows};p=R/'logs/freshness.json';t=p.with_suffix('.tmp');t.write_text(json.dumps(out,ensure_ascii=False,indent=2));t.replace(p);print(len(rows))
