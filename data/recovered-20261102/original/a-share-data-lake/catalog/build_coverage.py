#!/usr/bin/env python3
"""Read branch metadata and publish an evidence-limited, atomic coverage snapshot.
Does not download, mutate, fill, normalize or certify underlying branch data.
"""
import argparse, collections, csv, datetime, gzip, hashlib, json, os, shutil
from pathlib import Path
SCHEMA=1
BRANCHES=('reference','market','actions','fundamentals','macro','intraday')
FLOOR=15*1024**3

def now(): return datetime.datetime.now(datetime.timezone.utc).isoformat()
def read_json(path, issues):
    if not path.exists(): return None
    try:
        if path.stat().st_size > 64*1024**2: raise ValueError('Metadata exceeds 64 MiB audit bound')
        return json.loads(path.read_text())
    except (ValueError,OSError) as e:
        issues.append({'file':str(path),'kind':'metadata_unreadable','detail':str(e)[:200]})
        return None

def files_info(root):
    size=count=0
    for p in root.rglob('*') if root.exists() else []:
        if p.is_file() and not p.is_symlink():
            try: size+=p.stat().st_size; count+=1
            except FileNotFoundError: pass
    return {'file_count':count,'bytes':size}

def minmax(vals):
    vals=[str(v) for v in vals if v and str(v)!='1900-01-01']
    return {'first_observed_date':min(vals) if vals else None,'last_observed_date':max(vals) if vals else None}

def universe(path,issues):
    if not path.exists(): return {'file':str(path),'count':None,'duplicates':None}
    try:
        with path.open(newline='',encoding='utf-8-sig') as f: rows=list(csv.DictReader(f))
        ids=[r.get('instrument') for r in rows]
        counts=collections.Counter(ids)
        return {'file':str(path),'count':len(rows),'unique_instruments':len(counts),'duplicates':[k for k,n in counts.items() if n>1], 'by_exchange':dict(collections.Counter(r.get('exchange','unknown') for r in rows)),'by_status':dict(collections.Counter(r.get('status','unknown') for r in rows)), 'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    except (OSError,ValueError) as e:
        issues.append({'file':str(path),'kind':'csv_unreadable','detail':str(e)[:200]});return {'count':None}

def progress_counts(expected,states,terminal):
    attempted=sum(states.values())
    valid_expected=isinstance(expected,int) and expected>=0
    return {'expected':expected if valid_expected else None,'attempted':attempted,'unattempted':max(expected-attempted,0) if valid_expected else None,'by_status':dict(states),'terminal_results':sum(n for s,n in states.items() if s in terminal),'scope_complete':False}

def reference(root,issues):
    d=read_json(root/'catalog.json',issues) or {}
    master=universe(root/'normalized/security-master.csv',issues)
    price=universe(root/'normalized/price-universe.csv',issues)
    return {'state':'partial' if master.get('count') else 'running','source_manifest':str(root/'catalog.json'),'security_master':master,'price_universe':price,'limitations':d.get('limitations',[]),'pit_eligibility_certified':False,'counts_are_instrument_codes_not_unique_issuers':True,'alias_mapping_available':(root/'normalized/bse-code-alias-candidates.csv').exists(),'unknown_code_switch_dates_not_filled':True,'manifest':d,'supplementary':read_json(root/'supplementary/catalog.json',issues)}

def market(root,issues):
    progress=read_json(root/'progress.json',issues) or {}
    job=read_json(root/'manifests/job.json',issues) or {}
    statuses=[]
    for p in sorted((root/'status').glob('*.json')):
        d=read_json(p,issues)
        if isinstance(d,dict): statuses.append(d)
    states=collections.Counter(s.get('state','unknown') for s in statuses)
    expected=progress.get('universe_count',job.get('count'))
    state='blocked' if progress.get('state')=='blocked' else ('paused' if str(progress.get('state','')).startswith('paused') else 'running')
    if progress.get('state')=='completed_bounded_pass': state='partial' # An attempted pass is not complete market coverage.
    return {'state':state,'source_manifest':str(root/'progress.json'),'counts':progress_counts(expected,states,set(states)), 'rows':sum(s.get('row_count',0) for s in statuses),'missing_session_count':sum(s.get('missing_session_count',0) for s in statuses),'validation_issue_count':sum(len(s.get('validation_issues',[])) for s in statuses),**minmax([s.get(k) for s in statuses for k in ('first_date','last_date')]),'scope':progress.get('scope',job.get('requested_date_range')), 'download_state_does_not_prove_complete_sessions':True,'date_basis':'actual normalized daily-price dates','price_basis':'unadjusted','volume_unit':'source/security-specific contract required: mainboard lots×100; STAR raw shares evidenced in local audit, repair/normalization status must be checked per file','volume_unit_audit':read_json(root.parent/'catalog/volume-unit-hypothesis-audit.json',issues),'star_normalization_correction':read_json(root/'star-normalization-correction.json',issues),'star_repair_verification':read_json(root.parent/'catalog/star-repair-verification.json',issues),'quarantined_alternative_sources':{'hf_features':{'audit':read_json(root/'hf_features/audit.json',issues),'quarantine':read_json(root/'hf_features/quarantine.json',issues),'included_in_research_ready_counts':False}},'source_progress':progress,'requested_segment_counts':dict(collections.Counter((s.get('requested_start') or 'unknown')+'..'+(s.get('requested_end') or 'unknown') for s in statuses)),'rows_are_tencent_partition_only_not_cross_source_union':True,'blocked':read_json(root/'blocked.json',issues),'latest_lag_review':read_json(root/'latest-lag-review.json',issues),'gap_review_completion':read_json(root/'gap-review-completion-manifest.json',issues),'observed_key_union':read_json(root/'observed-coverage-union.json',issues),'completion_manifest':read_json(root/'completion-manifest.json',issues),'independent_final_manifest_audit':read_json(root.parent/'catalog/market-final-manifest-audit.json',issues),'final_integrity_audit':read_json(root/'final-integrity-audit.json',issues),'raw_integrity_audit':read_json(root/'raw-integrity-audit.json',issues),'expanded_overlap_audit':read_json(root/'expanded-overlap-audit.json',issues),'bulk_source_partitions':{'hf_bulk':{'calendar_audit':read_json(root/'hf_bulk/calendar-audit.json',issues),'progress':read_json(root/'hf_bulk/progress.json',issues),'audit':read_json(root/'hf_bulk/audit.json',issues),'normalized_manifest':read_json(root/'hf_bulk/normalized-manifest.json',issues),'duplicates':read_json(root/'hf_bulk/duplicate-audit.json',issues)}}}

def actions(root,issues):
    p=root/'catalog/factor-status.json'; d=read_json(p,issues) or {};items=d.get('items',{})
    if not isinstance(items,dict): issues.append({'file':str(p),'kind':'invalid_items'});items={}
    states=collections.Counter(v.get('status','unknown') for v in items.values() if isinstance(v,dict))
    vals=[v for v in items.values() if isinstance(v,dict)]
    return {'state':('partial' if d.get('stop_reason')=='pass_finished' else 'blocked') if d.get('stop_reason') else 'running','source_manifest':str(p),'factor_counts':progress_counts(d.get('target_count'),states,{'complete','unavailable','failed','retry_exhausted'}),'factor_events_including_initial_sentinels':sum(v.get('events',0) for v in vals), **minmax([v.get(k) for v in vals for k in ('first_event','last_event')]),'date_basis':'factor-event metadata; 1900-01-01 is a vendor sentinel, not historical market coverage','independent_final_factor_audit':read_json(root.parent/'catalog/factors-final-independent-audit.json',issues),'historical_factor_pit_certified':False,'stop_reason':d.get('stop_reason'),'updated_at':d.get('updated_at'),'corporate_actions_are_not_covered_by_factor_success':True,'branch_summary':read_json(root/'catalog/branch-status.json',issues),'coverage_gaps':read_json(root/'catalog/coverage-gaps.json',issues),'event_field_quality':read_json(root/'catalog/event-field-quality.json',issues),'rate_contract':read_json(root/'catalog/rate-contract.json',issues),'additional_family_progress':{n:read_json(root/'catalog'/n,issues) for n in ('sharebonus-status.json','equity-status.json','suspensions-status.json','rights-status.json','hf-price-limits.json','hf-status-audit.json','equity-universe.json','raw-page-integrity.json','factor-two-gaps-review.json','factor-basis-provenance.json') if (root/'catalog'/n).exists()}}

def fundamentals(root,issues):
    p=root/'catalog/progress.json';d=read_json(p,issues) or {};tasks=d.get('tasks',[])
    if not isinstance(tasks,list):tasks=[]
    states=collections.Counter(t.get('status','unknown') for t in tasks if isinstance(t,dict))
    counts=progress_counts(d.get('expected_tasks'),states,{'success','failed','unavailable','retry_exhausted'})
    asof=datetime.datetime.now(datetime.timezone.utc).astimezone(datetime.timezone(datetime.timedelta(hours=8))).date().isoformat()
    future=[{'report':t.get('report'),'period':t.get('period'),'notice_date_max':t.get('notice_date_max'),'future_notice_rows_at_acquisition':t.get('future_notice_dates')} for t in tasks if (t.get('future_notice_dates',0)>0 if 'future_notice_dates'in t else str(t.get('notice_date_max') or '')[:10]>asof)]
    for row in future: issues.append({'kind':'future_dated_financial_notice','branch':'fundamentals',**row})
    return {'state':'partial' if counts['unattempted']==0 else 'running','source_manifest':str(p),'final_artifacts':read_json(root/'catalog/final-artifacts.json',issues),'independent_final_audit':read_json(root.parent/'catalog/fundamentals-final-independent-audit.json',issues),'valuation_final_audit':read_json(root/'valuations/catalog/final-audit.json',issues),'alternate_valuation_coverage':read_json(root/'catalog/alternate-valuation-coverage.json',issues),'report_period_counts':counts,'reported_rows':sum(t.get('rows',0) for t in tasks),'row_count_basis':'vendor rows; may include B shares and OTC listings; not pure A-share coverage','missing_notice_dates':sum(t.get('notice_date_missing',0) for t in tasks),'duplicate_keys':sum(t.get('duplicate_keys',0) for t in tasks),'future_dated_notice_tasks':future,'requested_periods':d.get('expected_periods'),'rows_are_latest_vendor_vintage_not_PIT':True,'as_of_comparison_date_shanghai':asof,'tasks':tasks,'derived_views':read_json(root/'views/manifest.json',issues),'disclosure_pagination_repairs':read_json(root/'catalog/disclosure-pagination-repairs.json',issues),'full_statements_independent_final_audit':read_json(root.parent/'catalog/fundamentals-full-final-audit.json',issues),'core_independent_final_audit':read_json(root.parent/'catalog/fundamentals-core-final-audit.json',issues),'disclosure_id_audit':read_json(root/'catalog/disclosure-id-audit.json',issues),'disclosure_effective_coverage':read_json(root/'catalog/disclosure-effective-coverage.json',issues),'pagination_repairs':read_json(root/'catalog/pagination-repairs.json',issues),'latest_refresh_comparison':read_json(root/'catalog/latest-refresh-comparison.json',issues),'observed_schemas':read_json(root/'catalog/observed-schemas.json',issues),'job_definitions':read_json(root/'catalog/jobs.json',issues),'subbranch_progress':{n:read_json(root/n/'catalog/progress.json',issues) for n in ('disclosures','valuations','supplemental','full_statements','special_financials') if (root/n/'catalog/progress.json').exists()}}

def csv_stats(path):
    opener=gzip.open if path.name.endswith('.gz') else open
    with opener(path,'rt',newline='',encoding='utf-8-sig') as f:
        reader=csv.DictReader(f); fields=reader.fieldnames or [];n=0; first=last=None
        datefield=next((x for x in ('date','trade_date','TRADE_DATE','report_date','REPORT_DATE','END_DATE','STATISTICS_DATE','showDateCN') if x in fields),None)
        for r in reader:
            n+=1;v=r.get(datefield) if datefield else None
            if v: first=v if first is None else min(first,v);last=v if last is None else max(last,v)
    return {'file':str(path),'rows':n,'fields':fields,'date_field':datefield,'first_observed_value':first,'last_observed_value':last,'date_format_unverified':True}

def generic(root,issues):
    manifests={}
    for name in ('catalog.json','manifest.json','progress.json','coverage.json','catalog/manifest.json','catalog/progress.json','catalog/coverage.json','logs/flow-coverage.json','logs/northbound-unit-validation.json','logs/fund-progress.json','logs/hkex-holdings-coverage.json','logs/margin-detail-progress.json','logs/margin-detail-coverage.json','logs/margin-detail-final-audit.json','logs/margin-calendar-gap-check.json','logs/margin-latest-calendar-coverage.json','logs/margin-latest-month-view.json','logs/margin-latest-refresh-final-audit.json','logs/branch-freeze.json','logs/margin-category-status.json','logs/official-margin-monthly-coverage.json','logs/sse-margin-probe-comparison.json','logs/szse-margin-probe-comparison.json','logs/szse-margin-oct30-availability.json','logs/szse-oct30-export-direct-refresh.json','logs/sse-margin-bulk-progress.json','logs/szse-margin-bulk-progress.json','logs/nbs-coverage.json','logs/nbs-normalization.json','logs/nbs-final-raw-audit.json','logs/fund-audit.json','logs/money-fund-audit.json','logs/fund-resolution-status.json','logs/fund-late-observations.json','logs/fund-holdings-audit.json','logs/sse-margin-official-api-gapfill.json','logs/official-margin-combined-status.json','logs/official-margin-raw-hash-audit.json','logs/official-margin-source-anomalies.json','logs/official-margin-normalized-audit.json','logs/margin-shard-coverage.json'):
        p=root/name;d=read_json(p,issues)
        if d is not None: manifests[name]=d
    tables=[]
    for p in sorted((root/'normalized').glob('*.csv'))+sorted((root/'normalized').glob('*.csv.gz')):
        if any(x in p.name for x in ('.tmp.','.partial.','.part.')): continue
        try: tables.append(csv_stats(p))
        except (OSError,ValueError) as e: issues.append({'file':str(p),'kind':'normalized_unreadable','detail':str(e)[:200]})
    return {'state':'running','source_manifests':manifests,'normalized_tables':tables,'final_independent_audit':read_json(root.parent/'catalog/macro-final-independent-audit.json',issues),'vendor_margin_date_gaps':read_json(root.parent/'catalog/margin-vendor-date-gap-audit.json',issues),'latest_margin_independent_audit':read_json(root.parent/'catalog/margin-latest-final-independent-audit.json',issues),'vendor_margin_independent_audit':read_json(root.parent/'catalog/margin-vendor-final-independent-audit.json',issues),'official_margin_independent_audit':read_json(root.parent/'catalog/official-margin-final-independent-audit.json',issues),'margin_union_coverage':read_json(root.parent/'catalog/margin-union-coverage.json',issues),'margin_per_market_freshness':read_json(root.parent/'catalog/margin-per-market-freshness.json',issues),'publication_time_or_revision_history_not_inferred':True,'unverified_counts_not_promoted_to_complete':True}

def intraday(root,issues):
    p=read_json(root/'catalog/progress.json',issues) or {}
    return {'state':'running' if p.get('pending',1) else 'partial','source_progress':p,'run_contract':read_json(root/'catalog/run-contract.json',issues),'research_contract':read_json(root/'catalog/research-contract.json',issues),'independent_final_audit':read_json(root.parent/'catalog/intraday-final-independent-audit.json',issues),'audit':read_json(root/'catalog/audit.json',issues),'unit_probe':read_json(root/'catalog/probe-unit-audit.json',issues),'scope':'Recent provider-limited one-minute window only. Not2019fullminutehistory, tick, orderbook or complete240bar-day proof.','rows':p.get('normalized_rows'),'counts':progress_counts(p.get('expected_instruments'),p.get('counts',{}),set(p.get('counts',{})))}

def audit(root):
    root=root.resolve();issues=[];branches={}
    for name in BRANCHES:
        p=root/name
        fn={'reference':reference,'market':market,'actions':actions,'fundamentals':fundamentals,'intraday':intraday}.get(name,generic)
        branches[name]={**fn(p,issues),**files_info(p)}
    disk=shutil.disk_usage(root)
    ref=branches['reference']['price_universe']; market_n=branches['market']['counts']['expected']
    if ref.get('count') and market_n and market_n<ref['count']:
        issues.append({'kind':'market_universe_revision_pending','market_expected':market_n,'current_reference_count':ref['count']})
    d={'schema_version':SCHEMA,'generated_at_utc':now(),'scope':{'requested_start':'2019-01-01','requested_end':'2026-10-30','universe':'SH/SZ/BJ listed and delisted where publicly retrievable','all_quant_data_complete':False},'status':'running','disk':{'total_bytes':disk.total,'used_bytes':disk.used,'free_bytes':disk.free,'free_floor_bytes':FLOOR,'below_floor':disk.free<FLOOR},'branches':branches,'issues':issues,'uncovered_or_unverified_domains':[{'domain':x,'status':'not_established_by_current_downloads'} for x in ['minute_and_tick_history','level2_order_book','complete_historical_ST_and_price_limits','complete_point_in_time_constituents','financial_statement_revision_vintages','complete_dividend_payment_dates','news_and_alternative_data','historical_security_code_change_crosswalk']], 'audit_limits':['Read-only summary of branch manifests and actual normalized files; not full validation of every source response','Running files may change after this snapshot; missing/partial metadata is not treated as zero data','Coverage completeness, legal redistribution rights and point-in-time validity are separate claims','Current security lists and reported fiscal dates are not automatically point-in-time data']}
    final=read_json(root/'catalog/finalization.json',issues) or {}
    d['finalization']=final
    d['storage_accounting']={'branch_file_bytes':sum(b['bytes'] for b in branches.values()),'branch_file_count':sum(b['file_count'] for b in branches.values()),'basis':'Stored files across six branches including raw, normalized, archived and derived copies. Not unique observation volume; excludes runtime and catalog/.'}
    if final.get('all_acquisition_queues_terminal_verified'):
        d['status']='bounded_first_passes_terminal_with_documented_gaps'
        for name,b in branches.items():
            b['acquisition_pass_terminal']=True
            if b['state']=='running':b['state']='partial'
    return d

def markdown(d):
    lines=['# A-share data lake coverage', '',f"Snapshot: {d['generated_at_utc']}",'',f"**Status: {d['status']}. Not all quant data is complete.**",'',f"Disk free: {d['disk']['free_bytes']/1024**3:.2f} GiB (floor 15 GiB)",'']
    for name,b in d['branches'].items():
        lines+=['## '+name,f"State: {b['state']}; {b['file_count']} files; {b['bytes']/1024**2:.2f} MiB."]
        if name=='reference': lines+=[f"Master: {b['security_master'].get('count')}; price universe: {b['price_universe'].get('count')}. Current + delisted union, not PIT eligibility."]
        if name=='market': lines+=[f"Instrument codes: {b['counts']['attempted']} attempted / {b['counts']['expected']} expected; {b['rows']} rows; {b['missing_session_count']} unfilled missing sessions. {b['first_observed_date']} to {b['last_observed_date']}."]
        if name=='market':
            hf=b.get('bulk_source_partitions',{}).get('hf_bulk',{}).get('normalized_manifest') or {}
            if hf: lines += ['### Independent HF historical partition', f"{hf.get('rows')} normalized deduplicated rows; {hf.get('codes')} instrument codes; {hf.get('earliest')} to {hf.get('asof')}. Separate vendor source. Do not add overlapping Tencent/HF rows as unique coverage."]
        if name=='market':
            union=b.get('observed_key_union') or {}
            if union:lines += [f"2019起跨源观察键去重并集：{union.get('observed_unique_code_dates')} 股日 / {union.get('codes_with_rows')} 有观察代码；{union.get('codes_observed_target_date')} 只末日达 Oct30；适用观察日历内缺 {union.get('within_scope_missing_code_dates')} 股日（可能停牌或源缺失，不填造）。含 needs-review 行，仅观察覆盖，不是可交易/质量认证；不混合OHLC数值。"]
            lag=b.get('latest_lag_review') or {}
            if lag:lines += [f"末日未观察247只的独立复查分类：{lag.get('exclusive_categories')}。6只active有vendor非交易证据，不当官方停牌认证；未知BJ生命周期仍待核。两HF整日缺口补齐后剩12/5个股日，两独立日线源均无记录，不伪造停牌价格。"]
            ca=b.get('bulk_source_partitions',{}).get('hf_bulk',{}).get('calendar_audit') or {}
            overlap=(b.get('expanded_overlap_audit') or {}).get('unmatched_tencent_overlap',{})
            if ca.get('global_zero_observation_dates'):lines += [f"HF calendar gaps affecting all codes: {ca['global_zero_observation_dates']}. Independent Tencent supplement currently {overlap.get('rows')} rows / {overlap.get('codes')} codes; source-specific lineage retained, not proof all historical gaps are repaired."]
        if name=='actions': lines+=[f"Factors: {b['factor_counts']['attempted']} attempted / {b['factor_counts']['expected']} expected. Factor availability does not establish dividend/payment/status completeness."]
        if name=='actions':
            fa=b.get('independent_final_factor_audit') or {}
            if fa:lines += [f"因子首遍来源可用性已终态：{fa.get('states')}；共 {fa.get('events_including_basis_sentinels')} 行，其中 {fa.get('basis_sentinels_present_in_raw_source')} 个 basis sentinel 逐条确认来自原始供应商响应（非自行补默认值）。去 sentinel 后 {fa.get('non_sentinel_rows')} 行，不等于完整公司行动事件数。两缺失代码保留原始空响应、无伪造 normalized 文件。"]
            st=b.get('additional_family_progress',{}).get('hf-status-audit.json') or {}
            if st: lines += [f"Partial vendor daily ST flags: {st.get('accepted_keys')} unique security-days / {st.get('securities')} codes, {st.get('first_date')} to {st.get('last_date')}. Not exchange/PIT certified; no forward fill to latest date. All-zero pause flags do not establish suspension history."]
        if name=='fundamentals': lines+=[f"Report-type × quarter tasks: {b['report_period_counts']['attempted']} attempted / {b['report_period_counts']['expected']} expected; {b['reported_rows']} rows. Latest-vintage values, not PIT. Future-dated notice tasks: {len(b['future_dated_notice_tasks'])}."]
        if name=='intraday':lines += [f"近期1分钟：{b['counts']['attempted']} 已尝试 / {b['counts']['expected']} 目标，{b['rows']} bar；{b['source_progress'].get('counts')}。仅供应商返回有限窗口，分钟量单位 shares，不照搬腾讯日线×100；非2019全历史分钟、tick或order book，BSE单位一致性warning保留。"]
        if name=='macro':
            mm=b.get('source_manifests',{})
            agg=next((x for x in (mm.get('logs/flow-coverage.json') or []) if x.get('family')=='margin_accounts'),{})
            detail=mm.get('logs/margin-detail-progress.json') or {}
            lines += [f"两融全市场汇总：{agg.get('rows')} 日，{agg.get('min_date')} 至 {agg.get('max_date')}；状态 {agg.get('state')}，仅该 API 响应收全，不代表逐证券明细齐全。",f"逐证券两融明细（股票 + ETF/基金）：已完成 {detail.get('completed_months')} / 94 月，已完成月合计 {detail.get('completed_rows')} 行；状态 {detail.get('state')}。不与汇总表混称；近期分片与月表不可重复计数。"]
            gap=b.get('vendor_margin_date_gaps') or {}
            if gap:lines += [f"vendor已收全94月API分区，但明确缺4整日：{gap.get('missing_vendor_dates_both_SH_SZ')}。定向源API仍空，官方core字段覆盖而额外vendor字段缺口保留；不是完整PIT/交易日字段覆盖。"]
            union=b.get('margin_union_coverage') or {}
            if union:lines += [f"两融跨源去重覆盖独立快照时间：{union.get('generated_at_utc')}（可能早于本汇总生成时间；实时下载数量参见分支 progress）。"]
            for source,markets in union.get('source_summary',{}).items():
                for market,g in markets.items():lines += [f"- 两融独立来源 {source}/{market}：{g['observed_dates']} 个观察日，{g['earliest']} 至 {g['latest']}，{g['rows']} 源记录；可用核心字段 {g['fields_with_nonnull_values']}。"]
            for market,g in union.get('markets',{}).items():lines += [f"- 两融覆盖去重并集 {market}：{g['unique_security_date_keys']} 个证券日键；仅字段可用性去重统计，不合并源值、不代表全历史/全资格池齐全。"]
            margin=b.get('margin_per_market_freshness') or {}
            for market,g in margin.get('markets',{}).items():lines += [f"- 逐证券 {market}：最新观察 {g['latest_observed_date']}；目标日 2026-10-30 行数 {g['rows_on_target_date']}。{g['status']}。"]
            lines += ['汇总表没有逐交易所维度，汇总 max date 不能证明沪深北明细均已到最新；API 返回收全不等于市场日期覆盖完整。']
            nbs=b.get('source_manifests',{}).get('logs/nbs-normalization.json') or {}
            if nbs: lines += [f"NBS normalized snapshot: {nbs.get('rows')} rows; statistical periods {nbs.get('min_period_start')} to {nbs.get('max_period_end')}. Non-null values through {nbs.get('max_nonnull_period_end')}; {nbs.get('null_numeric_values')} null rows. Period dates are not publication dates."]
        if 'normalized_tables'in b:
            lines += [f"- {Path(t['file']).name}: {t['rows']} rows; date values {t['first_observed_value']} to {t['last_observed_value']} (format/availability not certified)." for t in b['normalized_tables']]
        lines+=['']
    lines+=['## Gaps and interpretation','No missing prices are imputed by this audit. Final source manifests and per-file receipts retain limitations. Minute/tick, order book, complete PIT history, revision vintages and several action/status fields remain unestablished.','',f"Audit issues: {len(d['issues'])}. See coverage.json for details."]
    return '\n'.join(lines)+'\n'

def atomic(path,text):
    tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(text);os.replace(tmp,path)
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--root',default=str(Path(__file__).resolve().parents[1]));a=ap.parse_args();root=Path(a.root);d=audit(root);out=root/'catalog';out.mkdir(exist_ok=True)
    atomic(out/'coverage.json',json.dumps(d,ensure_ascii=False,indent=2)+'\n');atomic(out/'coverage.md',markdown(d));print(json.dumps({'status':d['status'],'generated_at':d['generated_at_utc'],'issues':len(d['issues']),'free_gib':round(d['disk']['free_bytes']/1024**3,2)}))
