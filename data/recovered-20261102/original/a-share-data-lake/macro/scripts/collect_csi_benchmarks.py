import pathlib,json,requests,time,hashlib,datetime
import pandas as pd
R=pathlib.Path(__file__).resolve().parents[1];O=R/'raw/csi';O.mkdir(exist_ok=True);recs=[];coverage=[];errors=[]
cal=set((R.parent/'reference/normalized/trading-calendar-observed-2019-2026.txt').read_text().split())
for code in ['000300','000905','000852','000016','000688','000510']:
 p=O/(code+'.json');url='https://www.csindex.com.cn/csindex-home/perf/index-perf';params={'indexCode':code,'startDate':'20190101','endDate':'20261030'}
 try:
  if p.exists():d=json.loads(p.read_text())
  else:
   time.sleep(1.1);r=requests.get(url,params=params,headers={'Referer':'https://www.csindex.com.cn/'},timeout=45)
   if r.status_code in [401,403,429]:raise PermissionError(str(r.status_code))
   r.raise_for_status();d=r.json();p.write_bytes(r.content)
   recs.append({'file':str(p.relative_to(R)),'url':r.url,'retrieved_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'sha256':hashlib.sha256(r.content).hexdigest()})
  df=pd.DataFrame(d['data']);df['date']=pd.to_datetime(df.tradeDate,format='%Y%m%d').dt.strftime('%Y-%m-%d');df['observed_reference_calendar_match']=df.date.isin(cal);df['source_index_type']='price_index_not_total_return';df['publication_timestamp']=None
  out=R/'normalized'/('csi_benchmark_'+code+'.csv');df.to_csv(out,index=False)
  coverage.append({'code':code,'rows':len(df),'min_date':df.date.min(),'max_date':df.date.max(),'duplicate_dates':int(df.date.duplicated().sum()),'calendar_unmatched_dates':df.loc[~df.observed_reference_calendar_match,'date'].tolist(),'file':str(out.relative_to(R)),'status':'downloaded_with_calendar_validation_flags','note':'Official API includes anomalous 2019-01-01 duplicate of 2019-01-02 for CSI300; retain raw and flag, not silently repair. Calendar reference is observed history not authoritative scheduled calendar. Volume/value/peg raw fields retained without inferred rescaling.'});print(code,len(df),flush=True)
 except Exception as e:
  errors.append({'code':code,'error':str(e)})
  if isinstance(e,PermissionError):break
 finally:
  (R/'logs/csi-benchmark-receipts.json').write_text(json.dumps(recs,indent=2));(R/'logs/csi-benchmark-coverage.json').write_text(json.dumps(coverage,ensure_ascii=False,indent=2));(R/'logs/csi-benchmark-failures.json').write_text(json.dumps(errors,indent=2))
