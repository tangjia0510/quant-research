from pathlib import Path
import hashlib,json,datetime,zipfile,shutil
P=Path(__file__).resolve().parents[1];BASE=P.parents[2];D=BASE/'deliverables/published-amplitude-ovnt-20261102';D.mkdir(parents=True,exist_ok=True)
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def seal():
 dest=P/'final-artifact-manifest.json';assert not dest.exists();files=[]
 for p in sorted(P.rglob('*')):
  if p.is_file() and '__pycache__' not in p.parts and p!=dest:files.append({'path':str(p.relative_to(P)),'bytes':p.stat().st_size,'sha256':sha(p)})
 dest.write_text(json.dumps({'sealed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'research_kind':'supplementary published-factor monthly adaptation','native_model_trials':0,'files':files,'total_files':len(files),'total_bytes':sum(x['bytes'] for x in files)},ensure_ascii=False,indent=2))
 result={'manifest':str(dest),'sha256':sha(dest),'files':len(files),'bytes':sum(x['bytes'] for x in files)};(D/'seal-result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
def package():
 assert (P/'final-artifact-manifest.json').exists();items={}
 for p in sorted(P.rglob('*')):
  if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ['.parquet','.pyc'] and p.name!='RESEARCH_CARDS.md':items[str(Path('research')/p.relative_to(P))]=p
 audit=BASE/'quant-research-library/engineering-audits/paper-amplitude-ovnt-v1'
 for p in sorted(audit.glob('*')):
  if p.is_file() and p.suffix in ['.json','.py','.md']:items[str(Path('independent-audit')/p.name)]=p
 for p in [BASE/'quant-research/SKILL.md',BASE/'quant-research/references/research-modes.md',BASE/'quant-research/references/factor-validation.md',BASE/'quant-research/references/temporal-design.md']:
  items[str(Path('skill-methodology')/p.name)]=p
 zip_path=D/'文献因子复现-理想振幅与隔夜趋势-20261102.zip';entries=[{'path':n,'bytes':p.stat().st_size,'sha256':sha(p)} for n,p in items.items()]
 with zipfile.ZipFile(zip_path,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
  for name,p in items.items():z.write(p,name)
  z.writestr('PACKAGE-MANIFEST.json',json.dumps({'created_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'full_local_parquets_excluded':True,'files':entries},ensure_ascii=False,indent=2))
 with zipfile.ZipFile(zip_path) as z:assert z.testzip() is None
 result={'path':str(zip_path),'bytes':zip_path.stat().st_size,'files':len(items)+1,'sha256':sha(zip_path)};(D/'package-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':
 import sys
 {'seal':seal,'package':package}[sys.argv[1]]()
