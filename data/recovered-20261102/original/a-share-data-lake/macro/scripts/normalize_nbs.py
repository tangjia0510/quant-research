import json,pathlib,re,calendar,datetime,hashlib
import pandas as pd
R=pathlib.Path(__file__).resolve().parents[1];cs=json.loads((R/'logs/nbs-coverage.json').read_text());rows=[];sources=[]
def dates(code):
 if re.fullmatch(r'\d{6}MM',code):
  y,m=int(code[:4]),int(code[4:6]);return f'{y}-{m:02}-01',f'{y}-{m:02}-{calendar.monthrange(y,m)[1]:02}'
 if re.fullmatch(r'\d{6}SS',code):
  y,q=int(code[:4]),int(code[4:6]);m=(q-1)*3+1;e=m+2;return f'{y}-{m:02}-01',f'{y}-{e:02}-{calendar.monthrange(y,e)[1]:02}'
 if re.fullmatch(r'\d{4}YY',code):return code[:4]+'-01-01',code[:4]+'-12-31'
 return None,None
for c in cs:
 if not c.get('source_file'):continue
 p=R/c['source_file'];d=json.loads(p.read_text());sources.append({'file':c['source_file'],'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
 for period in d.get('data',[]):
  code=period.get('code','');start,end=dates(code)
  for v in period.get('values',[]):
   raw=v.get('value');num=pd.to_numeric(raw,errors='coerce');rows.append({'frequency':c['frequency'],'catalog_id':c['cid'],'catalog_path':c['path'],'period_code':code,'period_label':period.get('name'),'period_start':start,'period_end':end,'indicator_id':v.get('_id'),'indicator_name':v.get('i_showname') or v.get('ek_dp_name') or v.get('_name'),'unit':v.get('du_name') or v.get('unit_name') or v.get('unit') or 'unknown','value_raw':None if raw is None else str(raw),'value_numeric':num,'publication_date':None,'source_file':c['source_file'],'vintage':'latest_revised_as_retrieved_not_PIT'})
df=pd.DataFrame(rows);snapshot_duplicate_keys=int(df.duplicated(['frequency','catalog_id','period_code','indicator_id']).sum());p=R/'normalized/nbs_national_normalized.parquet'
if p.exists():
 old=pd.read_parquet(p);df=pd.concat([old,df],ignore_index=True).drop_duplicates(['frequency','catalog_id','period_code','indicator_id'],keep='last')
sources=[{'file':f,'sha256':hashlib.sha256((R/f).read_bytes()).hexdigest()} for f in sorted(df.source_file.dropna().unique())]
tmp=p.with_suffix('.tmp.parquet');df.to_parquet(tmp,index=False);tmp.replace(p)
keys=['frequency','catalog_id','period_code','indicator_id'];receipt={'generated_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'state':('complete_selected_catalog_first_pass' if (R/'logs/nbs-progress.log').read_text().rstrip().splitlines()[-1].startswith('DONE ') and not json.loads((R/'logs/nbs-failures.json').read_text()) else 'snapshot_of_running_or_partial_download'),'rows':len(df),'catalog_leaves':int(df[['frequency','catalog_id']].drop_duplicates().shape[0]),'duplicate_keys':int(df.duplicated(keys).sum()),'source_snapshot_duplicate_keys':snapshot_duplicate_keys,'min_period_start':df.period_start.dropna().min(),'max_period_end':df.period_end.dropna().max(),'source_files':sources,'output_file':str(p.relative_to(R)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'min_nonnull_period_start':df.loc[df.value_numeric.notna(),'period_start'].dropna().min(),'max_nonnull_period_end':df.loc[df.value_numeric.notna(),'period_end'].dropna().max(),'publication_date_known':0,'null_numeric_values':int(df.value_numeric.isna().sum())};(R/'logs/nbs-normalization.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2));print({k:v for k,v in receipt.items() if k!='source_files'})
