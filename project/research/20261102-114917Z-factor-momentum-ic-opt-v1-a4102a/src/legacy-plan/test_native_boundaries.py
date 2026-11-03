from pathlib import Path
import sys,json,hashlib
import numpy as np,pandas as pd
P=Path(__file__).resolve().parents[1];W=P.parents[2];sys.path.insert(0,str(W/'quant-research/scripts'))
from quantlib.engine import scale_train_only,split_masks,labels_for
calendar=pd.bdate_range('2024-12-02','2026-01-30');idx=pd.MultiIndex.from_product([calendar,['A','B']],names=['datetime','instrument']);bars=pd.DataFrame({'open':np.arange(len(idx))+100.},index=idx)
label,ends,c=labels_for(bars,{'price':'open','entry_lag':1,'horizon':5});splits=json.loads((P/'research-plan.json').read_text())['splits'];m=split_masks(idx,ends,splits,'discovery');dates=idx.get_level_values('datetime')
assert (ends[m['train']]<pd.Timestamp(splits['valid'][0])).all();assert (ends[m['valid']]<pd.Timestamp(splits['discovery'][0])).all()
f=pd.DataFrame({'x':np.arange(len(idx),dtype=float)},index=idx);mask=dates<pd.Timestamp('2025-01-01');a,med,iqr=scale_train_only(f,mask);changed=f.copy();changed.loc[~mask,'x']=1e15;b,med2,iqr2=scale_train_only(changed,mask);pd.testing.assert_series_equal(med,med2);pd.testing.assert_series_equal(iqr,iqr2);pd.testing.assert_frame_equal(a[mask],b[mask]);f.loc[idx[0],'x']=np.nan;scaled,_,_=scale_train_only(f,mask);assert scaled.loc[idx[0],'x']==0
out={'train_only_scaler_future_perturbation':True,'median_missing_imputation':True,'train_and_validation_label_purging':True,'engine_sha256':hashlib.sha256((W/'quant-research/scripts/quantlib/engine.py').read_bytes()).hexdigest(),'fixture':'synthetic unit-test only, NOT empirical study results'}
(P/'outputs/native-boundary-tests.json').write_text(json.dumps(out,indent=2));print('PASS native preprocessing and label boundary unit tests')
