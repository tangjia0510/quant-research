from pathlib import Path
import hashlib,json,zipfile,datetime,sys
R=Path(__file__).resolve().parents[1];BASE=Path.cwd();D=BASE/'deliverables/faber-strategy-20261102';D.mkdir(parents=True,exist_ok=True)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
if sys.argv[1]=='seal':
 assert (R/'report/qa-report.json').exists(),'report QA required'
 files=[p for p in sorted(R.rglob('*')) if p.is_file() and '__pycache__' not in p.parts and p.name!='artifacts-manifest.json']
 m={'sealed_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'files':[{'path':str(p.relative_to(R)),'bytes':p.stat().st_size,'sha256':sha(p)} for p in files]};(R/'artifacts-manifest.json').write_text(json.dumps(m,indent=2));out={'files':len(files),'bytes':sum(p.stat().st_size for p in files),'manifest_sha256':sha(R/'artifacts-manifest.json')};(D/'seal-result.json').write_text(json.dumps(out,indent=2));print(out)
elif sys.argv[1]=='package':
 assert (R/'artifacts-manifest.json').exists()
 # Keep non-CC source PDF and its full extraction local; deliver source URL/card/hash only.
 excluded={'faber_2013_taa.pdf','faber-native-extracted.txt'}
 files=[p for p in sorted(R.rglob('*')) if p.is_file() and '__pycache__' not in p.parts and p.name not in excluded and not any(part in ['rendered','qa-pages','render'] for part in p.parts)]
 audit=BASE/'quant-research-library/engineering-audits/strategies-v1'
 entries=[(p,str(p.relative_to(R))) for p in files]+[(p,'independent-audit/'+p.name) for p in sorted(audit.glob('*.json'))]
 dest=D/'完整策略验证-Faber十月均线与沪深300ETF-20261102.zip'
 with zipfile.ZipFile(dest,'w',zipfile.ZIP_DEFLATED,6) as z:
  for p,n in entries:z.write(p,n)
  z.writestr('PACKAGE-MANIFEST.json',json.dumps({'files':[{'path':n,'bytes':p.stat().st_size,'sha256':sha(p)} for p,n in entries],'exclusions':'Original Faber copyrighted full PDF/text retained locally; official source URL/citation and hash supplied. No whole market data, no Site, no executable live trading.'},indent=2))
 result={'path':str(dest),'bytes':dest.stat().st_size,'files':len(entries)+1,'sha256':sha(dest)};(D/'package-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False))
else:raise ValueError('seal|package')
