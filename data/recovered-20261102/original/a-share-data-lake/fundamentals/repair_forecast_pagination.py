"""Keep failed original snapshot; independently reacquire with a deterministic composite sort."""
from pathlib import Path
import acquire_supplemental as a
ORIGINAL_GET=a.SESSION.get
def stable_get(url,**kwargs):
    params=dict(kwargs.get('params',{}))
    params.update(sortColumns='SECURITY_CODE,PREDICT_FINANCE_CODE,NOTICE_DATE',sortTypes='1,1,1')
    kwargs['params']=params
    return ORIGINAL_GET(url,**kwargs)
a.SESSION.get=stable_get
a.ROOT=Path(__file__).resolve().parent/'pagination_repairs'/'forecast-stable-v1'
a.ROOT.mkdir(parents=True,exist_ok=True)
a.REPORTS={'forecast':'RPT_PUBLIC_OP_NEWPREDICT'}
import json
progress=json.loads((Path(__file__).resolve().parent/'supplemental/catalog/progress.json').read_text())
a.PERIODS=sorted(set(['2025-06-30']+[x['period'] for x in progress['tasks'] if x.get('report')=='forecast' and x.get('status')=='failed' and 'pagination_invalid' in x.get('error','')]))
if __name__=='__main__':a.main()
