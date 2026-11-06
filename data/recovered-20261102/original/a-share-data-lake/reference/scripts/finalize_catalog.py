# PUBLIC SANITIZED COPY (2026-11-06): machine paths generalized; see provenance/publication_transformations.json.
from pathlib import Path
import json,csv,hashlib,shutil
from datetime import datetime,timezone
import pandas as pd
B=Path(__file__).resolve().parents[1]
old=B.parents[1]/'fin_data/legacy-inputs/source-review'
for f in old.glob('*probe*json'):shutil.copy2(f,B/'raw'/('original-'+f.name))
# Scope labels correct rather than overclaim all SZSE funds or one placeholder as security.
p=B/'normalized/szse-listed-all-funds.csv'
if p.exists():p.rename(B/'normalized/szse-funds-catalog1945-scope-unverified.csv')
p=B/'normalized/szse-innovation-convertibles.csv'
if p.exists() and '没有找到符合条件' in p.read_text():p.write_text(p.read_text().splitlines()[0]+'\n')
c=json.load(open(B/'catalog.json'));c['generated_at']=datetime.now(timezone.utc).isoformat();c['status']='first_pass_completed_with_explicit_gaps'
c['limitations']=['Current plus terminal listing union is NOT point-in-time eligibility or historical industry','SH/SZ official listings include STAR; BSE official master blocked by CDN challenge, no bypass attempted','357 BJ identifiers are financial/disclosure inferred, unknown IPO and official active status; 248 code aliases share CNINFO orgId but effective dates unknown','Observed trading calendar derived from index quotes, not exchange-certified calendar','CSI current constituent/weight files are current snapshots only; do not backfill historically','CSI history actions are parsed evidence, not a complete certified event ledger: PDF patterns partially supported, announcement replacement/attachment dates may differ from original publish date','Cached CSI300 reconstruction is independently sourced prior reference data, not certified exhaustive daily PIT; scope2021-06-01 to2026-10-30','Official SZ fund catalog1945_GP is stock-fund subset; catalog1945 broader scope unverified, not all funds','Initial legacy CSI URLs returned HTML masquerading as XLS; those raw files are invalid_content and excluded from normalized outputs']
m=pd.read_csv(B/'normalized/security-master.csv',dtype=str).fillna('');c['master_breakdown']={str(k):int(v) for k,v in m.groupby(['exchange','status']).size().items()}
a=pd.read_csv(B/'normalized/csi-history/rebalance-action-evidence.csv',dtype=str);u=a.drop_duplicates(['notice_id','index_code','action','security_code'])
c['products']={
 'security_master':{'path':'normalized/security-master.csv','rows':len(m),'unique_key':'instrument'},
 'price_universe':{'path':'normalized/price-universe.csv','rows':5818,'unknown_ipo_not_assumed_2019':True},
 'bse_alias_candidates':{'path':'normalized/bse-code-alias-candidates.csv','rows':248,'effective_dates_known':False},
 'cninfo_orgmap':{'path':'normalized/cninfo-security-orgmap.csv','rows':6262},
 'trading_calendar':{'path':'normalized/trading-calendar-observed-2019-2026.txt','rows':1897,'start':'2019-01-02','end':'2026-10-30','type':'observed_index_quotes'},
 'csi_current':{'codes':['000300','000905','000852','000016','000688','000510'],'constituents':2400,'weights':2400,'valuation_rows':120,'receipts':['index-api-receipts.json','index-weight-receipts.json']},
 'csi_rebalance':{'path':'normalized/csi-history/rebalance-action-evidence.csv','notices':54,'evidence_rows':len(a),'unique_action_keys':len(u),'review_status':'provisional_parser_evidence_not_certified_ledger','by_index':{k:{'notices':int(v.notice_id.nunique()),'actions':len(v),'min_publish_date':v.publish_date.min(),'max_publish_date':v.publish_date.max()} for k,v in u.groupby('index_code')}},
 'csi300_cached_reconstruction':{'path':'cached-source/csi300-reconstruction-20261031','member_days':393900,'trading_days':1313,'start':'2021-06-01','end':'2026-10-30','pit_certified':False},
 'sse_funds':{'path':'normalized/sse-listed-funds.csv','rows':1256,'scope':'official_listed_funds'},
 'szse_stock_funds':{'path':'normalized/szse-listed-funds.csv','rows':797,'scope':'official_stock_fund_catalog1945_GP'},
 'szse_innovation_convertibles':{'path':'normalized/szse-innovation-convertibles.csv','rows':0,'status':'official_no_matching_data_placeholder_excluded'},
}
p=B/'normalized/eastmoney-convertible-master.csv'
if p.exists():c['products']['convertible_bonds']={'path':str(p.relative_to(B)),'rows':len(pd.read_csv(p)),'scope':'vendor_all_reported_convertibles_including_matured_not_exchange_certified'}
c['receipt_files']=sorted(p.name for p in B.glob('*receipt*.json'))
(B/'catalog.json').write_text(json.dumps(c,ensure_ascii=False,indent=2))
files=[]
for p in sorted(B.rglob('*')):
 if p.is_file() and p.name!='artifact-manifest.json':files.append({'path':str(p.relative_to(B)),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
(B/'artifact-manifest.json').write_text(json.dumps({'generated_at':c['generated_at'],'files':files,'bytes':sum(x['bytes'] for x in files),'immutable_raw_policy':'Raw bytes retained; receipt sourceURL/acquisition time preserved separately; derived outputs versioned by hashes.'},ensure_ascii=False,indent=2))
print(json.dumps({'files':len(files),'bytes':sum(x['bytes'] for x in files),'products':c['products']},ensure_ascii=False))
