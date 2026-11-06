import pandas as pd,json,re,csv,hashlib
from pathlib import Path
B=Path(__file__).resolve().parents[1];T={'000300','000905','000852','000016','000688','000510'};rows=[];issues=[]
def code(s):
 s=str(s).strip().removesuffix('.0');return s.zfill(6) if re.fullmatch(r'\d{1,6}',s) else ''
for f in sorted((B/'raw/csi-embedded').glob('*')):
 nid=f.name.split('-')[0];n=json.load(open(B.parent/f'raw/csi-history/detail-{nid}.json'))['data'];txt=re.sub('<[^>]+>','',n.get('content',''));eff='';timing=''
 m=re.findall(r'自(\d{4})年(\d{1,2})月(\d{1,2})日起',txt)
 if len(set(m))==1:eff='-'.join([m[0][0],m[0][1].zfill(2),m[0][2].zfill(2)]);timing='start_of_day'
 else:
  m=re.findall(r'(\d{4})年(\d{1,2})月(\d{1,2})日(?:收市|收盘)后生效',txt)
  if len(set(m))==1:eff='-'.join([m[0][0],m[0][1].zfill(2),m[0][2].zfill(2)]);timing='after_close'
 def add(idx,act,c,name,sheet):
  c=code(c)
  if idx in T and c:rows.append(dict(notice_id=nid,publish_date=n['publishDate'],effective_date=eff,effective_timing=timing,index_code=idx,action=act,security_code=c,security_name=str(name),source_file=str(f.relative_to(B)),sheet=sheet,source_sha256=hashlib.sha256(f.read_bytes()).hexdigest(),historical_available_at_unverified=True))
 try:
  for sheet,d in pd.read_excel(f,sheet_name=None,header=None,dtype=str).items():
   if '备选' in sheet:continue
   for r in d.fillna('').values.tolist():
    if len(r)==7 and not r[0]:r=r[1:]
    if len(r)<4:continue
    idx=code(r[0])
    if idx not in T:continue
    if '调入' in sheet or '换入' in sheet:add(idx,'add',r[2],r[3],sheet)
    elif '调出' in sheet or '换出' in sheet:add(idx,'remove',r[2],r[3],sheet)
    elif len(r)==6:add(idx,'remove',r[2],r[3],sheet);add(idx,'add',r[4],r[5],sheet)
    else:issues.append(dict(file=str(f.relative_to(B)),sheet=sheet,columns=len(r),reason='unsupported_target_row'))
 except Exception as e:issues.append(dict(file=str(f.relative_to(B)),error=str(e)))
pd.DataFrame(rows).to_csv(B/'normalized/csi-embedded-rebalance-evidence.csv',index=False);(B/'csi-embedded-parse-issues.json').write_text(json.dumps(issues,ensure_ascii=False,indent=2));print(len(rows),len(issues))
