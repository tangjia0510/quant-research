import json,re,hashlib,csv,subprocess
from pathlib import Path
from bs4 import BeautifulSoup
import pandas as pd
B=Path(__file__).resolve().parents[1]; R=B/'raw/csi-history'; O=B/'normalized/csi-history';O.mkdir(exist_ok=True)
TARGET={'沪深300':'000300','中证500':'000905','中证1000':'000852','上证50':'000016','科创50':'000688','中证A500':'000510'}
rows=[];notices=[];issues=[]
def code(x):
 s=str(x).strip().removesuffix('.0');return s.zfill(6) if re.fullmatch(r'\d{1,6}',s) else ''
for p in sorted(R.glob('detail-*.json')):
 d=json.loads(p.read_text()).get('data') or {};nid=str(d.get('id')); soup=BeautifulSoup(d.get('content') or '', 'html.parser');txt=soup.get_text(' ',strip=True)
 (O/f'{nid}-notice.txt').write_text(txt)
 dates=re.findall(r'(\d{4})年(\d{1,2})月(\d{1,2})日(?:收市|收盘)后生效',txt)
 eff='-'.join([dates[0][0],dates[0][1].zfill(2),dates[0][2].zfill(2)]) if len(set(dates))==1 else ''
 n={'notice_id':nid,'publish_date':d.get('publishDate'),'effective_after_close':eff,'title':d.get('title'),'source_file':str(p.relative_to(B)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()};notices.append(n)
 def add(idx,action,c,name,src):
  c=code(c)
  if idx in TARGET.values() and c:rows.append(dict(notice_id=nid,publish_date=n['publish_date'],effective_after_close=eff,index_code=idx,action=action,security_code=c,security_name=str(name),source_file=src,historical_availability_verified=False))
 for table in soup.find_all('table'):
  context=''
  for sib in table.previous_siblings:
   t=sib.get_text(' ',strip=True) if hasattr(sib,'get_text') else str(sib)
   if getattr(sib,'name',None)=='table':break
   context=t+' '+context
   if '指数' in t or len(context)>600:break
  idx=next((v for k,v in TARGET.items() if k in context),None)
  if not idx or '备选' in context[-100:]:continue
  trs=[[td.get_text(' ',strip=True) for td in tr.find_all(['td','th'])] for tr in table.find_all('tr')]
  header=' '.join(' '.join(x) for x in trs[:2])
  if '调出' not in header or '调入' not in header:continue
  for r in trs:
   if len(r)==4:add(idx,'remove',r[0],r[1],str(p.relative_to(B)));add(idx,'add',r[2],r[3],str(p.relative_to(B)))
 for f in R.glob(nid+'-attachment-*'):
  if f.suffix in ('.xls','.xlsx'):
   try:
    sheets=pd.read_excel(f,sheet_name=None,header=None,dtype=str).items()
    for sheet,df in sheets:
     if '备选' in sheet:continue
     for vals in df.fillna('').values.tolist():
      if len(vals)<4:continue
      idx=code(vals[0]);src=str(f.relative_to(B))+'#'+sheet
      if '调入' in sheet or '换入' in sheet:add(idx,'add',vals[2],vals[3],src)
      elif '调出' in sheet or '换出' in sheet:add(idx,'remove',vals[2],vals[3],src)
      elif len(vals)==6:add(idx,'remove',vals[2],vals[3],src);add(idx,'add',vals[4],vals[5],src)
      elif len(vals)==10:
       for z in (2,4):add(idx,'remove',vals[z],vals[z+1],src)
       for z in (6,8):add(idx,'add',vals[z],vals[z+1],src)
      else:issues.append({'file':src,'reason':'unsupported_excel_layout','columns':len(vals)});break
   except Exception as e:issues.append({'file':str(f.relative_to(B)),'error':str(e)})
  elif f.suffix=='.pdf':
   result=subprocess.run(['pdftotext','-layout',str(f),str(O/(f.stem+'.txt'))],capture_output=True)
   if result.returncode:issues.append({'file':str(f.relative_to(B)),'reason':'pdf_conversion_failed','exit':result.returncode});continue
   current=None;parsed=0
   for line in (O/(f.stem+'.txt')).read_text().splitlines():
    compact=re.sub(r'\s+','',line)
    if '指数' in compact and ('名单' in compact or '调整' in compact):
     current=next((v for k,v in TARGET.items() if compact.startswith(k+'指数') and '备选' not in compact),None)
    if current:
     m=re.match(r'^\s*(\d{6})\s+(.+?)\s+(\d{6})\s+(.+?)\s*$',line)
     if m:
      add(current,'remove',m[1],m[2],str(f.relative_to(B)));add(current,'add',m[3],m[4],str(f.relative_to(B)));parsed+=2
   issues.append({'file':str(f.relative_to(B)),'reason':'pdf_two_column_parser_partial_requires_review','parsed_rows':parsed})
# Preserve separately sourced duplicate evidence; one row per notice/index/action/security/source.
rows=list({tuple(r.values()):r for r in rows}.values())
with (O/'rebalance-action-evidence.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
(O/'notices.json').write_text(json.dumps(notices,ensure_ascii=False,indent=2));(O/'parse-limitations.json').write_text(json.dumps(issues,ensure_ascii=False,indent=2))
print('notices',len(notices),'action_evidence',len(rows),'unique_actions',len({(r['notice_id'],r['index_code'],r['action'],r['security_code']) for r in rows}),'issues',len(issues))
