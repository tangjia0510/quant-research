#!/usr/bin/env python3
"""Evidence-only freshness matrix. Event/period age is not publication lag."""
import collections,csv,datetime,json,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
TARGET='2026-10-30'
ASOF='2026-11-01' # Collection date. The target is the latest completed observed A-share session.

def load(p,default=None):
 try:return json.loads((ROOT/p).read_text())
 except (OSError,ValueError):return default

def maxval(values):return max((str(v) for v in values if v),default=None)
def last_receipt(path,filter_text=None):
 p=ROOT/path
 try:
  data=[json.loads(x) for x in p.read_text().splitlines() if x.strip()] if p.suffix=='.jsonl' else json.loads(p.read_text())
  if not isinstance(data,list):return None
  rows=[x for x in data if not filter_text or filter_text in str(x.get('file',''))]
  return maxval(x.get('retrieved_at_utc') or x.get('retrieved_at') or x.get('acquired_at') or x.get('finished_utc') or x.get('at') for x in rows)
 except (OSError,ValueError):return None

def receipt_directory_latest(path,pattern='*.json'):
    values=[]
    for p in (ROOT/path).rglob(pattern):
        try:
            d=json.loads(p.read_text())
            if isinstance(d,dict):values.append(d.get('acquired_utc') or d.get('acquired_at') or d.get('retrieved_at_utc') or d.get('retrieved_at'))
        except (OSError,ValueError):pass
    return maxval(values)

def row(name,freq,latest,expected=None,source=None,retrieved=None,state=None,**extras):
 # Only independently supplied observation/period targets are used. No fabricated publication timestamp.
 if state is None:state='expected_latest_unverified' if expected is None else ('observed_target_reached' if latest and latest>=expected else 'observation_behind_target')
 return {'dataset':name,'frequency':freq,'actual_latest_observation_or_period_end':latest,'expected_latest_observation_or_period_end':expected,'latest_expected_source_publication_at':None,'source_publication_schedule_status':'not_independently_verified_unless_stated_in_notes','retrieved_at_utc':retrieved,'freshness_state':state,'source_evidence':source,'publication_lag_inferred_from_age':False,**extras}

def market_freshness_counts(stocks,universe):
 """Mutually exclusive groups; an old delisted quote is not stale-active data."""
 by_id={x.get('instrument','').replace('.',''):x for x in stocks}
 counts=collections.Counter()
 for ref in universe:
  st=by_id.get(ref.get('instrument','').replace('.',''))
  if st is None:kind='unattempted_or_nonterminal'
  else:
   last=st.get('last_date');life=ref.get('status')
   if last and last>TARGET:kind='future_observation_needs_review'
   elif last==TARGET:kind='observed_target_reached'
   elif life=='delisted':kind='delisted_older_or_no_observation'
   elif life=='active':kind='known_active_before_target_or_no_observation'
   else:kind='lifecycle_unknown_before_target_or_no_observation'
  counts[kind]+=1
 return dict(counts)

def build():
 rows=[];mp=load('market/progress.json',{}) or {};stocks=[]
 for p in (ROOT/'market/status').glob('*.json'):
  try:stocks.append(json.loads(p.read_text()))
  except (OSError,ValueError):pass
 latest=maxval(x.get('last_date') for x in stocks)
 last_counts=dict(collections.Counter(x.get('last_date') or 'no_rows' for x in stocks))
 with (ROOT/'reference/normalized/price-universe.csv').open() as f:universe=list(csv.DictReader(f))
 lifecycle_counts=market_freshness_counts(stocks,universe)
 rows.append(row('Tencent daily-price requested partitions','daily',latest,TARGET,'market/progress.json',receipt_directory_latest('market/raw','*.receipt.json'), 'incomplete_universe' if mp.get('pending_count',1) else 'bounded_pass_completed_check_per_security_gaps',completed_instruments=len(stocks),expected_instruments=mp.get('universe_count'),last_observation_date_distribution=last_counts,whole_universe_freshness_groups=lifecycle_counts,focused_latest_lag_review=load('market/latest-lag-review.json',{}),latest_local_completion_at=maxval(x.get('completed_utc') for x in stocks),notes='A single max date is not whole-universe freshness. Delisted/security-lifecycle and unattempted targets are distinct from stale active prices.'))
 ip=load('intraday/catalog/progress.json',{}) or {};ist=[]
 for p in (ROOT/'intraday/catalog/status').glob('*.json'):
  try:ist.append(json.loads(p.read_text()))
  except (OSError,ValueError):pass
 if ip:rows.append(row('近期1分钟有限窗口','1minute_recent_only',maxval(x.get('latest_day') for x in ist),TARGET,'intraday/catalog/progress.json',maxval(x.get('retrieved_at_utc') for x in ist),state='recent_window_pass_running' if ip.get('pending') else 'recent_window_pass_terminal_not_full_history',attempted_instruments=ip.get('attempted_terminal'),source_status_counts=ip.get('counts'),expected_instruments=ip.get('expected_instruments'),last_observation_date_distribution=dict(collections.Counter(x.get('latest_day') or 'no_rows' for x in ist)),notes='Finite1970barresponse, not entire2019..latest intraday history. A latest-day bar does not certify complete sessions/auction bars or volume validity.'))
 hf=load('market/hf_bulk/normalized-manifest.json',{}) or {};hp=load('market/hf_bulk/progress.json',{}) or {}
 rows.append(row('HF historical daily prices','daily',hf.get('asof'),TARGET,'market/hf_bulk/normalized-manifest.json',maxval(x.get('finished_utc') for x in hp.get('results',[])),state='historical_partition_not_current',notes='Intentional historical source shard. Tencent tail is separate; combined coverage must be validated by instrument-date.'))
 fs=load('fundamentals/catalog/progress.json',{}) or {};tasks=fs.get('tasks',[])
 good=[t for t in tasks if t.get('status')=='success'];latest=maxval(t.get('period') for t in good)
 rows.append(row('Financial statements and earnings summaries','quarterly_fiscal_period',latest,'2026-09-30','fundamentals/catalog/progress.json',receipt_directory_latest('fundamentals/receipts'),state=('bounded_core_acquisition_complete_latest_vintage_not_PIT' if fs.get('status')=='complete' else 'partial_acquisition_latest_vintage_not_PIT'),successful_tasks=len(good),attempted_tasks=len(tasks),task_status_counts=dict(collections.Counter(t.get('status','unknown') for t in tasks)),expected_tasks=fs.get('expected_tasks'),latest_local_completion_at=maxval(t.get('completed_at') for t in good),notes='Latest fiscal quarter is not the publication time. Future NOTICE_DATE and missing disclosure dates are excluded only in date-screened views; historic revised values remain not PIT.'))
 vp=load('fundamentals/valuations/catalog/progress.json',{}) or {};vt=vp.get('tasks',[]);vcounts=dict(collections.Counter(t.get('status','unknown') for t in vt))
 rows.append(row('Daily valuations and share history','daily',maxval(str(t.get('max_date') or '')[:10] for t in vt),TARGET,'fundamentals/valuations/catalog/progress.json',receipt_directory_latest('fundamentals/valuations/receipts'),state='incomplete_universe' if len(vt)<vp.get('expected_tasks',1) else 'bounded_pass_check_gaps',attempted_instruments=len(vt),successful_with_data_instruments=vcounts.get('success',0),unavailable_empty_instruments=vcounts.get('unavailable',0),failed_or_other_instruments=sum(v for k,v in vcounts.items() if k not in ('success','unavailable')),terminal_status_counts=vcounts,expected_instruments=vp.get('expected_tasks'),latest_local_completion_at=maxval(t.get('completed_at') for t in vt),last_observation_date_distribution=dict(collections.Counter(str(t.get('max_date') or 'no_rows')[:10] for t in vt)),notes='Vendor identity backmapping and revised valuation inputs are not certified point-in-time.'))
 for branch in ('disclosures','supplemental','full_statements','special_financials'):
  p=f'fundamentals/{branch}/catalog/progress.json';d=load(p,{}) or {}
  if not d:continue
  repairs=load('fundamentals/catalog/pagination-repairs.json',{}) or {}
  effective_state=repairs.get('effective_status') if branch=='supplemental' else d.get('status')
  if branch=='disclosures':
   de=load('fundamentals/catalog/disclosure-effective-coverage.json',{}) or {}
   if de.get('effective_success')==de.get('expected_windows') and de.get('expected_windows'):effective_state='complete_with_replacements'
  ts=d.get('tasks',[]);maxperiod=maxval(t.get('period') for t in ts if isinstance(t,dict) and t.get('status')=='success')
  rows.append(row('Financial '+branch,'publication_window' if branch=='disclosures' else 'quarterly_fiscal_period',maxperiod,None,p,receipt_directory_latest(f'fundamentals/{branch}/receipts'),state='running_or_partial' if effective_state not in ('complete','complete_with_gaps','complete_with_replacements')else 'bounded_pass_check_gaps',notes='See branch per-task actual publication/observation boundaries; request windows alone are not data freshness.'))
 st=load('actions/catalog/hf-status-audit.json',{}) or {}
 if st:rows.append(row('Vendor historical daily ST flags','daily_status',st.get('last_date'),TARGET,'actions/catalog/hf-status-audit.json',state='partial_historical_partition_not_current',securities=st.get('securities'),unique_security_days=st.get('accepted_keys'),notes='Only structurally audited flag projection is accepted. Full feature table remains quarantined. ST after2025-04-23 and before2021-01-04 not established; zero pause flag does not prove no suspensions.'))
 af=load('actions/catalog/factor-status.json',{}) or {};av=list(af.get('items',{}).values())
 ev=load('actions/catalog/event-field-quality.json',{}) or {}
 rows.append(row('Adjustment factors','event_driven',maxval(x.get('last_event') for x in av),None,'actions/catalog/factor-status.json',last_receipt('actions/logs/factor-receipts.jsonl'),state='event_dates_not_freshness',completed_instruments=sum(x.get('status')=='complete' for x in av),expected_instruments=af.get('target_count'),notes='Latest event date can be old because no corporate action occurred. Vendor basis sentinel is not market history. Future effective events must not be applied to earlier prices.'))
 for name,report in (ev.get('reports',{}) or {}).items():
  dates=report.get('date_fields',{});future=sum(x.get('after_collection_date_2026_11_01',0) for x in dates.values())
  rows.append(row('Corporate action '+name,'event_driven',None,None,'actions/catalog/event-field-quality.json',state='event_dates_not_freshness',event_date_field_ranges=dates,future_date_field_occurrences=future,notes='Announcement, plan, record, ex-date and payment dates are different. Future plan dates are not completed events or data freshness.'))
 nu=load('macro/logs/northbound-unit-validation.json',{}) or {}
 for x in nu.get('coverage',[]):rows.append(row('北向CNY规范化净流量 '+x['series'],'daily_disclosure_limited',x.get('latest_nonnull_net_flow_date'),None,'macro/logs/northbound-unit-validation.json',state='latest_nonnull_directional_flow_before_disclosure_break',coverage_snapshot_generated_at_utc=nu.get('generated_at_utc'),normalized_file=x.get('file'),notes='Derived CNY view distinct from original vendor units. Post2024-08-19 directional values remain null, not zero and not latest-date complete.'))
 mf=load('macro/logs/freshness.json',{}) or {};series=mf.get('series',[])
 for t in series:
  name=t.get('series','unknown');freq=t.get('frequency');latest=t.get('latest_available_observation_or_period_end');expected=TARGET if freq=='daily' else None
  receipt='macro/logs/rates-receipts.json';filter_text='shibor' if name=='shibor_daily'else 'lpr' if name=='lpr'else None
  if name=='chinabond_yield_curves':receipt='macro/logs/yield-receipts.json'
  if name.startswith('csi_'):receipt='macro/logs/csi-benchmark-receipts.json'
  if name.startswith(('northbound','shanghai_connect','shenzhen_connect','margin_')):receipt='macro/logs/flow-receipts.json'
  if name.startswith('hkex_'):continue # Aggregate quarters below; old retained snapshots are not stale.
  if name.lower().startswith('nbs') or name.startswith('fund_nav_'):continue
  state=None
  if name.startswith('margin_detail_'):state='api_response_complete_check_market_date_gaps'
  if 'connect' in name or 'northbound' in name:state='row_current_but_directional_flow_not_disclosed'
  display_name='两融全市场汇总 / market aggregate' if name=='margin_accounts' else ('逐证券两融明细（股票 + ETF/基金） '+name if name.startswith('margin_detail_') else 'Macro '+name)
  rows.append(row(display_name,freq,latest,expected,'macro/'+str(t.get('file')),t.get('retrieved_at_utc') or last_receipt(receipt,filter_text),state=state,notes=t.get('caveat','')))
 mu=load('catalog/margin-union-coverage.json',{}) or {}
 moc=load('macro/logs/official-margin-combined-status.json',{}) or {}
 official_state={x.get('exchange'):x.get('state') for x in moc.get('sources',[])}
 for g in moc.get('sources',[]):
  market=g.get('exchange')
  rows.append(row('官方逐证券两融 '+str(market),'daily',g.get('latest_date'),TARGET,'macro/logs/official-margin-combined-status.json',state=g.get('state'),coverage_snapshot_generated_at_utc=moc.get('generated_at_utc'),earliest_observed=g.get('earliest_date'),observed_dates=g.get('completed_dates_total'),notes='Official exports plus separately verified API/direct-export gapfills. Source core fields differ across SSE/SZSE. Latest export availability can differ from JSON endpoint; raw source discrepancy retained.'))
 margin=load('catalog/margin-per-market-freshness.json',{}) or {}
 for market,g in margin.get('markets',{}).items():rows.append(row('逐证券两融 '+market,'daily',g.get('latest_observed_date'),TARGET,'catalog/margin-per-market-freshness.json',state=g.get('status'),coverage_snapshot_generated_at_utc=margin.get('generated_at_utc'),rows_on_target_date=g.get('rows_on_target_date'),notes='Stocks and funds. Full vendor API response is not complete per-market dates. Aggregate max date does not establish detail freshness. Initial SZ official JSON Oct30 query returned zero, but later official XLSX export and vendor day snapshot yielded data; retain both source receipts and use latest validated snapshot, not old availability metadata.'))
 ms=load('macro/logs/margin-shard-coverage.json',{}) or {};shards=ms.get('shards',[])
 if shards:rows.append(row('逐证券两融已核验分片（股票 + ETF/基金）','daily',maxval(str(x.get('max_date') or '')[:10] for x in shards),TARGET,'macro/logs/margin-shard-coverage.json',state='partial_history_recent_shards_current',completed_shards=shards,notes='Full API response within individual shard only. Recent rows do not establish all history. Shards overlap monthly partitions and must not be concatenated without security-date deduplication.'))
 hk=load('macro/logs/hkex-holdings-coverage.json',{}) or {};hc=hk.get('coverage',[])
 for market in ('sh','sz'):
  dates=[x.get('date','').replace('/','-') for x in hc if x.get('market')==market and x.get('state')=='downloaded']
  rows.append(row('HKEX northbound holdings '+market,'quarterly',maxval(dates),'2026-09-30','macro/logs/hkex-holdings-coverage.json',last_receipt('macro/logs/hkex-holdings-receipts.json'),retained_quarters=sorted(dates),notes='Latest completed quarter published fifth northbound trading day after quarter end under verified disclosure rule. 12-month website retention; not daily holdings or full historical coverage.'))
 nbs=load('macro/logs/nbs-normalization.json',{}) or {}
 rows.append(row('NBS national indicators','mixed_monthly_quarterly_annual',nbs.get('max_nonnull_period_end'),None,'macro/logs/nbs-normalization.json',last_receipt('macro/logs/nbs-receipts.json'),state='publication_schedule_and_per_indicator_freshness_unverified',max_requested_or_present_period_end=nbs.get('max_period_end'),null_numeric_values=nbs.get('null_numeric_values'),notes='Uses latest NON-NULL period, not future/null period labels. Individual indicators differ; no publication time or vintage completeness claim.'))
 fund=load('macro/logs/fund-progress.json',{}) or {}
 fundres=load('macro/logs/fund-resolution-status.json',{}) or {}
 funda=load('macro/logs/fund-audit.json',{}) or {}
 fundseries=[t for t in series if t.get('series','').startswith('fund_nav_')]
 rows.append(row('ETF/fund NAV snapshots','fund_dependent_daily',maxval(t.get('latest_available_observation_or_period_end') for t in fundseries),None,'macro/logs/freshness.json',last_receipt('macro/logs/fund-receipts.jsonl'),state=('identities_processed_sparse_or_partial_histories_remain' if fundres.get('pending_codes')==0 else 'incomplete_current_universe_see_per_fund_dates'),identity_resolution=fundres,downloaded=fund.get('downloaded'),zero_NAV_response_count=funda.get('funds_with_zero_nav_rows'),one_NAV_response_count=funda.get('funds_with_one_nav_row'),source_sparse_caveat=funda.get('sparse_history_caveat'),universe=fund.get('universe'),last_observation_date_distribution=dict(collections.Counter(t.get('latest_available_observation_or_period_end') or 'no_observation' for t in fundseries)),notes='Per-fund latest NAV/retrieval date is in macro freshness matrix. Current pool omits delisted funds; NAV publication lags and overseas holidays can differ. Expanded pool includes REITs with sparse NAV; download success and zero/one row do not establish daily history completeness.'))
 late=load('macro/logs/fund-late-observations.json',{}) or {}
 if late:rows.append(row('基金初始行情截止日之后的源观察','fund_dependent_including_weekends',maxval(x.get('max_date') for x in late.get('files',[])),None,'macro/logs/fund-late-observations.json',maxval(x.get('retrieved_at_utc') for x in late.get('files',[])),state='later_observations_separate_from_initial_cutoff_views',funds=late.get('funds_with_later_observations'),field_observation_records=late.get('rows'),coverage_snapshot_generated_at_utc=late.get('generated_at_utc'),notes='Weekend money-fund observations may be newer than last exchange trading session. Rows are field observations, not necessarily unique fund-days or NAV.'))
 money=load('macro/logs/money-fund-audit.json',{}) or {}
 if money:rows.append(row('货币ETF每万份收益与七日年化','fund_dependent_income',maxval(x.get('max_date') for x in money.get('series',[])),None,'macro/logs/money-fund-audit.json',state='separate_income_series_not_NAV_or_realized_total_return',funds=money.get('money_funds'),rows=money.get('income_rows'),coverage_snapshot_generated_at_utc=money.get('generated_at_utc'),last_observation_date_distribution=dict(collections.Counter(x.get('max_date') for x in money.get('series',[]))),notes='Money-market fund income/yield records have different semantics from NAV; annualized yield is not realized strategy return.'))
 ref=load('reference/catalog.json',{}) or {}
 rows.append(row('Security identity and current reference snapshots','snapshot',None,None,'reference/catalog.json',state='snapshot_currentness_requires_source_dates',latest_local_catalog_generation=ref.get('generated_at'),notes='Collection time is not effective membership date. BJ inferred codes and unknown switch dates remain uncertified.'))
 return {'schema_version':1,'generated_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'initial_collection_date_shanghai':ASOF,'snapshot_date_shanghai':datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).date().isoformat(),'latest_completed_A_share_session_target':TARGET,'target_basis':'Latest observed complete A-share session before Sunday2026-11-01; does not apply mechanically to every dataset frequency.','rows':rows,'margin_official_availability':{'initial_JSON_probe':load('macro/logs/szse-margin-oct30-availability.json',{}),'later_direct_export':load('macro/logs/szse-oct30-export-direct-refresh.json',{})},'branch_freshness':{'fundamentals':load('fundamentals/catalog/freshness.json',{}),'macro_matrix_path':'macro/logs/freshness.json'},'bounded_acquisition_pass_finalization':load('catalog/finalization.json',{}),'all_data_latest_complete':False,'limitations':['A new download can contain stale, backfilled, revised or future-dated source data.','Unknown latest publication point remains null, not guessed.','Actual max date alone does not prove every instrument or field is current.','Historic fixtures/retained quarterly snapshots are not a claim of current daily data.']}

def md(d):
 out=['# Data freshness matrix','',f"Generated: {d['generated_at_utc']}",f"A-share daily target: {TARGET}. All data latest/complete: **No**.",'','Observation date, fiscal/statistical period, source publication time and retrieval time are distinct. Unknown publication targets remain unknown.','']
 for x in d['rows']:
  out += ['- **'+x['dataset']+'**: actual latest '+str(x['actual_latest_observation_or_period_end'])+'; observation/period target '+str(x['expected_latest_observation_or_period_end'])+'; '+x['freshness_state']+'. Retrieval UTC: '+str(x['retrieved_at_utc'])+'.']
  if x.get('terminal_status_counts'):out+=['  Attempted: '+str(x.get('attempted_instruments'))+' / '+str(x.get('expected_instruments'))+'; successful with data: '+str(x.get('successful_with_data_instruments'))+'; source empty: '+str(x.get('unavailable_empty_instruments'))+'; failed/other: '+str(x.get('failed_or_other_instruments'))+'.']
  if x.get('coverage_snapshot_generated_at_utc'):out+=['  Coverage evidence snapshot: '+x['coverage_snapshot_generated_at_utc']+'; may precede this matrix generation time.']
  if x.get('whole_universe_freshness_groups'):out+=['  Per-security groups: '+json.dumps(x['whole_universe_freshness_groups'],ensure_ascii=False)+'.']
  if x.get('notes'):out+=['  '+x['notes']]
 return '\n'.join(out)+'\n'
if __name__=='__main__':
 d=build();p=ROOT/'catalog'
 for name,text in [('freshness.json',json.dumps(d,ensure_ascii=False,indent=2)+'\n'),('freshness.md',md(d))]:
  dest=p/name;tmp=dest.with_suffix(dest.suffix+'.tmp');tmp.write_text(text);os.replace(tmp,dest)
 print(json.dumps({'rows':len(d['rows']),'all_data_latest_complete':False}))
