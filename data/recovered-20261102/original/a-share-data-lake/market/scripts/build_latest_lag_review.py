"""Bounded lag classification; no interpolation or rewritten price partitions."""
import csv,gzip,hashlib,json,datetime as dt
from collections import Counter
from pathlib import Path
M=Path(__file__).resolve().parents[1];ref=M.parent/'reference/normalized/security-master.csv';current={r['instrument'].replace('.',''):r for r in csv.DictReader(ref.open())};sina_path=M/'gap_review/sina-focused-review.json';sina=json.loads(sina_path.read_text());bycode={r['instrument']:r for r in sina['results']};items=[];counts=Counter()
for p in sorted((M/'status').glob('*.json')):
 s=json.loads(p.read_text());code=s['instrument'];last=s.get('last_date')
 if last=='2026-10-30':continue
 r=s['source_list_record'];cr=current.get(code,{});end=cr.get('delist_date') or r.get('delist_date');known=bool(end and end<='2026-10-30')
 category=('known_delisted_with_earlier_rows' if last else 'known_delisted_no_rows_in_requested_window') if known else ('active_vendor_nontrading_at_target' if r.get('status')=='active' else ('unknown_lifecycle_earlier_rows' if last else 'unknown_lifecycle_no_rows'))
 record={'instrument':code,'name':r.get('name'),'category':category,'source_state':s['state'],'observed_last_date':last,'official_delist_date':end or None,'frozen_master':r,'current_reference_record':cr,'market_status_file':str(p.relative_to(M)),'market_status_sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
 if not known:
  rr=s.get('raw_receipts',[])[-1] if s.get('raw_receipts') else None
  if rr:
   q=json.loads(gzip.decompress((M/rr['raw_file']).read_bytes())).get('data',{}).get(code,{}).get('qt',{}).get(code,[])
   if len(q)>41:record['target_quote_evidence']={'timestamp':q[30],'status_marker_index40':q[40],'close':q[3],'previous_close':q[4],'open':q[5],'volume_raw':q[6],'raw_file':rr['raw_file'],'sha256':rr['sha256'],'inference':'Current dated quote with S marker and zero open/volume corroborates nontrading; not official exchange suspension proof'}
   if category=='active_vendor_nontrading_at_target':
    assert len(q)>41 and q[30].startswith('20261030') and q[40]=='S' and float(q[5])==0 and float(q[6])==0
  record['independent_sina_daily_check']=bycode.get(code)
 counts[category]+=1;items.append(record)
gaps={r['instrument']:set(r['missing_dates']) for r in json.loads((M/'observed-coverage-gaps.json').read_text())};hf=list(csv.DictReader((M/'hf_bulk/coverage.csv').open()));hfdates=[]
for date in ['2025-05-27','2025-11-18']:
 eligible=[];missing=[]
 for r in hf:
  code=r['code'][-2:].lower()+r['code'][:6]
  if code not in gaps or not r['min_date']<=date<=r['max_date']:continue
  eligible.append(code)
  if date not in gaps[code]:continue
  sr=bycode[code];assert sr['state']=='observed' and sr['first_date']<=date<=sr['last_date']
  assert sr['targets'][date] is None
  missing.append({'instrument':code,'source_scope':'within_HF_and_Sina_observed_span','target_date':date,'independent_sina_check':'no target daily row, within returned span','classification':'absent_in_two_independent_daily_sources_possible_suspension_not_officially_certified','sina_raw_receipt':sr['receipt'],'last_date':sr['last_date']})
 hfdates.append({'date':date,'eligible_universe_codes_within_hf_observed_span':len(eligible),'observed_in_union':len(eligible)-len(missing),'unresolved_observed_price_absence':len(missing),'not_automatically_a_vendor_hole':True,'remaining':missing})
out={'generated_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'scope':'Only247 stocks without Oct30 daily row and2globally missingHF dates; no whole-universe rerun','target_date':'2026-10-30','market_universe':5818,'observed_at_target':5571,'not_observed_at_target':len(items),'exclusive_categories':dict(counts),'no_rows_in_requested_scope_total':sum(s['source_state']=='unavailable' for s in items),'new_independent_api_queries':sina['attempted'],'independent_source_checks_completed':True,'new_observed_missing_target_rows':0,'price_patch_required':False,'remaining_hf_global_gap_dates':hfdates,'per_stock':items,'reference_master_sha256':hashlib.sha256(ref.read_bytes()).hexdigest(),'sina_review_sha256':hashlib.sha256(sina_path.read_bytes()).hexdigest(),'limitations':['Known delisting prevents expecting future trade prices; no forward filling','Six active target-day nontrading cases supported by target-dated vendor quotes and independent daily source, not certified official suspension dates','Unknown BSE lifecycle retained even when names include retirement markers','17 historical keys absent in Tencent and independently Sina; no inferred OHLC or automatic error label','29478 union missingstockdays are not all missing-source errors; suspension and lifecycle evidence remain distinct','Unavailable within requested2019+ scope does not mean company absent or no historical source bars']}
p=M/'latest-lag-review.json';p.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items() if k not in ['per_stock','remaining_hf_global_gap_dates']},ensure_ascii=False))
