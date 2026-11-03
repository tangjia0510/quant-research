from pathlib import Path
import json,hashlib
import numpy as np,pandas as pd
P=Path(__file__).resolve().parents[1];O=P/'outputs';names={x['id'] for x in json.loads((P/'research-plan.json').read_text())['candidates']}
s=json.loads((O/'selection.json').read_text());a=s['primary_family_all6'];b=s['secondary_family_all12']
assert len(a)==6 and {(x['candidate'],x['horizon']) for x in a}=={(n,5) for n in names}
assert len(b)==12 and {(x['candidate'],x['horizon']) for x in b}=={(n,h) for n in names for h in [1,10]}
d=pd.read_csv(O/'direct-daily-development.csv',parse_dates=['date']);cov=pd.read_csv(O/'direct-coverage-development.csv',parse_dates=['date']);checks=[]
for (seg,h),g in cov.groupby(['segment','horizon']):
 expected=set(g.loc[g.label_n>=100,'date']);z=d[(d.segment==seg)&(d.horizon==h)]
 for n in names:
  x=z[z.candidate==n];assert set(x.date)==expected;assert np.isfinite(x[['pearson_ic','rank_ic']]).all().all()
  checks.append({'segment':seg,'horizon':int(h),'candidate':n,'measurable_dates':len(x),'nonfinite_ic':0,'missing_expected_dates':0})
out={'family_primary6_secondary12_verified':True,'checks':checks,'analysis_script_sha256':hashlib.sha256((P/'scripts/analyze_supplementary.py').read_bytes()).hexdigest(),'selection_sha256':hashlib.sha256((O/'selection.json').read_bytes()).hexdigest(),'note':'Daily HAC uses measured dates; maturity/purge tails outside segment are excluded; no nonfinite or dropped expected daily IC.'}
(O/'selection-integrity.json').write_text(json.dumps(out,indent=2));print('PASS complete 6/12 families, finite IC and expected dates')
