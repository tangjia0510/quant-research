from pathlib import Path
import sys,json,time,hashlib
import numpy as np,pandas as pd
P=Path(__file__).resolve().parents[1];W=P.parents[2];sys.path.insert(0,str(W/'quant-research/scripts'))
from quantlib.data import _eligibility as old
from eligibility_performance_patch import eligibility_grouped as new
cal=pd.bdate_range('2024-01-01',periods=100);idx=pd.MultiIndex.from_product([cal,['a','b','c']],names=['datetime','instrument']);frame=pd.DataFrame({'close':1.},index=idx)
base=pd.DataFrame([['a','2024-01-03','2024-01-05'],['a','2024-01-10','2024-02-01'],['b','2024-01-01','2024-05-01'],['absent','2024-01-01','2024-05-01']],columns=['instrument','start','end']);cases=[('none',None),('multiple_intervals',base),('duplicate_intervals',pd.concat([base,base])),('single_day',base.iloc[:1].assign(end='2024-01-03')),('empty_intervals',base.iloc[:0]),('all_absent',base.iloc[-1:]),('invalid_reverse',base.iloc[:1].assign(end='2023-01-01')),('invalid_null',base.iloc[:1].assign(start=None)),('missing_column',base.drop(columns='end'))];results=[]
for name,intervals in cases:
 for unordered in [False,True]:
  f=frame.sample(frac=1,random_state=2) if unordered else frame;v=[]
  for fn in [old,new]:
   try:v.append(('ok',fn(f,intervals)))
   except Exception as e:v.append(('error',type(e).__name__,str(e)))
  assert v[0][0]==v[1][0],(name,v)
  if v[0][0]=='ok':pd.testing.assert_frame_equal(v[0][1],v[1][1])
  else:assert v[0]==v[1],(name,v)
  results.append({'case':name,'unordered':unordered,'status':v[0][0],'equivalent':True})
for seed in range(10):
 rng=np.random.default_rng(seed);rows=[]
 for _ in range(50):
  a,b=sorted(rng.choice(cal,size=2));rows.append([rng.choice(['a','b','c','none']),a,b])
 intervals=pd.DataFrame(rows,columns=base.columns);pd.testing.assert_frame_equal(old(frame,intervals),new(frame,intervals))
# Small but realistic benchmark, not research outcome data.
ids=[f's{i:04}' for i in range(200)];idx=pd.MultiIndex.from_product([pd.bdate_range('2019-01-01',periods=1900),ids],names=['datetime','instrument']);f=pd.DataFrame({'close':1.},index=idx);u=pd.DataFrame({'instrument':ids,'start':'2020-01-01','end':'2025-01-01'});timing={};values=[]
for name,fn in [('legacy',old),('grouped',new)]:
 t=time.monotonic();values.append(fn(f,u));timing[name]=time.monotonic()-t
pd.testing.assert_frame_equal(*values)
out={'synthetic_unit_and_benchmark_only':True,'edge_cases':results,'randomized_equivalence_cases':10,'benchmark_rows':len(f),'benchmark_securities':len(ids),'seconds':timing,'original_module_sha256':hashlib.sha256((W/'quant-research/scripts/quantlib/data.py').read_bytes()).hexdigest(),'patch_sha256':hashlib.sha256((P/'scripts/eligibility_performance_patch.py').read_bytes()).hexdigest()};(P/'outputs/eligibility-performance-tests.json').write_text(json.dumps(out,indent=2));print(json.dumps(out))
