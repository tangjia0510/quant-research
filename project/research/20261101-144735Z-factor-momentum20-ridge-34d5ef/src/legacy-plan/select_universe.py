"""Freeze deterministic pre-price sample using the approved provider adapter."""
import hashlib,json,sys
from pathlib import Path
sys.path.insert(0,str(Path('${ORIGINAL_WORKSPACE}/quant-research/scripts')))
from quantlib.sources.baostock import BaoStockSource
folder=Path(__file__).parent
if (folder/'selection.json').exists():
    raise RuntimeError('Selection already frozen; inspect rather than replace')
with BaoStockSource(delay=.2,timeout=30,retries=2) as source:
    raw=source.fetch_instruments()
raw.to_csv(folder/'stock-basic-raw.csv',index=False)
rows=raw[(raw['type'].astype(str)=='1') & (raw.ipoDate.astype(str)<='2018-12-31') & raw.ipoDate.astype(str).str.fullmatch(r'\d{4}-\d{2}-\d{2}')].copy()
rows=rows[rows.outDate.isna() | rows.outDate.astype(str).str.strip().eq('') | (rows.outDate.astype(str)>='2019-01-01')]
selection=[]
for pattern in [r'sh\.60\d{4}',r'sz\.00\d{4}',r'sz\.30\d{4}']:
    part=rows[rows.code.astype(str).str.fullmatch(pattern)].sort_values('code').head(10)
    if len(part)!=10:raise RuntimeError('Insufficient stratum: '+pattern)
    selection.extend(part.to_dict('records'))
payload={'price_data_fetched':False,'rule_file_sha256':hashlib.sha256((folder/'preregistration.json').read_bytes()).hexdigest(),'source_basic_sha256':hashlib.sha256((folder/'stock-basic-raw.csv').read_bytes()).hexdigest(),'selected':selection,'instruments':[r['code'] for r in selection]}
(folder/'selection.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
(folder/'instruments.txt').write_text('\n'.join(payload['instruments'])+'\n')
print(json.dumps(payload,ensure_ascii=False))
