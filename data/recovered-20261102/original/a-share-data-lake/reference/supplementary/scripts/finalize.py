import pandas as pd,json,hashlib
from pathlib import Path
from datetime import datetime,timezone
B=Path(__file__).resolve().parents[1]
def read(name):
 p=B/'normalized'/name
 return pd.read_csv(p,dtype=str).fillna('') if p.exists() and p.stat().st_size>1 else pd.DataFrame()
x=read('cffex-monthend-contract-snapshots.csv')
if len(x):
 # Preserve observed contract versions rather than forcing changes into one row.
 cols=[c for c in ['PRODUCT_ID','INSTRUMENT_ID','INSTRUMENT_MONTH','OPEN_DATE','END_TRADING_DAY'] if c in x]
 contracts=x[cols].drop_duplicates();contracts.to_csv(B/'normalized/cffex-contract-identities-expiry.csv',index=False)
 equity=x[x.PRODUCT_ID.isin(['IF','IH','IC','IM','IO','HO','MO'])]
 equity.to_csv(B/'normalized/cffex-equity-monthend-snapshots.csv',index=False)
else:contracts=pd.DataFrame();equity=pd.DataFrame()
risks=pd.concat([read('sse-current-risk-master.csv'),read('szse-current-risk-master.csv')],ignore_index=True);risks.to_csv(B/'normalized/exchange-current-risk-union.csv',index=False)
reb=read('csi-embedded-rebalance-evidence.csv');industry=read('exchange-reported-industry.csv');options=read('sse-current-option-contracts.csv')
rec=json.load(open(B/'cffex-monthly-receipts.json'))
c={'generated_at':datetime.now(timezone.utc).isoformat(),'status':'bounded_supplementary_first_pass_complete','products':{'industry':{'rows':len(industry),'nonempty_industry':int((industry.industry_name!='').sum()),'path':'normalized/exchange-reported-industry.csv','point_in_time':False},'risk_snapshot':{'rows':len(risks),'a_share_rows':int((risks.is_a_share.str.lower()=='true').sum()),'path':'normalized/exchange-current-risk-union.csv','effective_dates_known':False},'sse_options_current':{'rows':len(options),'path':'normalized/sse-current-option-contracts.csv','source_dates':options.TIMESAVE.unique().tolist() if len(options) else []},'cffex':{'requested_monthends':len(rec),'successful_monthends':sum('rows' in r for r in rec),'failed_monthends':sum('error' in r for r in rec),'snapshot_rows':len(x),'identity_expiry_versions':len(contracts),'equity_snapshot_rows':len(equity),'paths':['normalized/cffex-monthend-contract-snapshots.csv','normalized/cffex-contract-identities-expiry.csv','normalized/cffex-equity-monthend-snapshots.csv'],'products':x.PRODUCT_ID.value_counts().to_dict() if len(x) else {}},'additional_csi_rebalance':{'rows':len(reb),'notices':int(reb.notice_id.nunique()) if len(reb) else 0,'path':'normalized/csi-embedded-rebalance-evidence.csv','provisional':True}},'limitations':['Exchange industry is current/terminal listing snapshot, mixed granularity; no historical industry PIT inferred','SW public endpoints503; CNINFO industry requires authorization; CITIC documented data requires token; see industry-coverage.json','Risk lists are acquisition-time official snapshot; no date-effective ST history inferred; include3 Bshares flagged separately','CFFEX data sampled on94 observed calendar monthends; contracts appearing and expiring wholly within month may be missing','Last trading/expiration dates are source fields, NOT main-contract turnover dates or a recommended trading roll strategy','CFFEX canonical published endpoint HTTP, not cryptographically transport-authenticated; raw SHA256 preserved','Historical CSI embedded attachments parsed separately; publish dates do not verify vintage availability; may duplicate core evidence; join on notice/index/action/code and retain all sources','Supplementary manifest intentionally independent of already-audited core reference manifest'], 'csi_reconciliation':json.load(open(B/'csi-evidence-reconciliation.json')), 'receipts':sorted(p.name for p in B.glob('*receipt*.json'))}
if len(reb):c['products']['additional_csi_rebalance']['by_index']={k:{'rows':len(v),'min_publish_date':v.publish_date.min(),'max_publish_date':v.publish_date.max()} for k,v in reb.groupby('index_code')}
(B/'catalog.json').write_text(json.dumps(c,ensure_ascii=False,indent=2))
files=[]
for p in sorted(B.rglob('*')):
 if p.is_file() and p.name!='artifact-manifest.json':files.append(dict(path=str(p.relative_to(B)),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
(B/'artifact-manifest.json').write_text(json.dumps(dict(generated_at=c['generated_at'],files=files,bytes=sum(x['bytes'] for x in files)),indent=2));print(json.dumps(c,ensure_ascii=False))
