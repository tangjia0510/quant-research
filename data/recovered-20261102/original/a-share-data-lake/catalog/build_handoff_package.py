# PUBLIC SANITIZED COPY (2026-11-06): machine paths generalized; see provenance/publication_transformations.json.
"""Build a credential-free CODE+INDEX bundle. Never includes raw/normalized data."""
from pathlib import Path
import json,hashlib,datetime,zipfile,re,urllib.parse
R=Path(__file__).resolve().parents[1];OUT=R/'catalog/delivery';OUT.mkdir(exist_ok=True)
name='a-share-CODE-INDEX-handoff-20261102.zip';target=OUT/name
OMIT={'headers','request_headers','response_headers','cookies','cookie','authorization','raw_receipts','receipts','raw_text','raw_response','source_response','http_response','raw_body','body','examples','pre1990_sentinel_examples'}
counts={};omissions=[]
def scrub_string(s):
 def urlfix(m):
  u=m.group(0)
  try:
   x=urllib.parse.urlsplit(u)
   if x.query or x.fragment:
    counts['URL_query_or_fragment_removed']=counts.get('URL_query_or_fragment_removed',0)+1
    return urllib.parse.urlunsplit((x.scheme,x.netloc,x.path,'',''))
  except ValueError:pass
  return u
 return re.sub(r'https?://[^\s<>"\)]+',urlfix,s)
def scrub(o):
 if isinstance(o,dict):
  d={}
  for k,v in o.items():
   if k.lower() in OMIT or re.search(r'(?i)(signed.?url|access.?token|refresh.?token|password|secret|api.?key)',k):
    counts['omitted_key:'+k]=counts.get('omitted_key:'+k,0)+1;continue
   d[k]=scrub(v)
  return d
 if isinstance(o,list):return [scrub(x)for x in o]
 return scrub_string(o)if isinstance(o,str)else o
selected=set()
for p in (R/'catalog').glob('*.json'):
 if p.name not in ('package-build-report.json',):selected.add(p)
for n in ['README.md','HANDOFF.md','FINAL_SUMMARY.md','coverage.md','freshness.md']:
 p=R/'catalog'/n
 if p.exists():selected.add(p)
for branch in ['market','actions','fundamentals','macro','intraday']:
 p=R/branch/'README.md'
 if p.exists():selected.add(p)
for p in R.rglob('*.py'):
 if any(x in p.parts for x in ['source-review','probes','raw','normalized','__pycache__','delivery']):continue
 if any(x in p.name for x in ['_v1','_v2','_v3','pre_star']) or p.name.startswith(('probe','review_focused','baostock_two_gap')):
  omissions.append(str(p.relative_to(R)));continue
 selected.add(p)
# No executable automatic entrypoint; each code file must be reviewed before manual use.
readme='''# CODE + INDEX RECOVERY PACKAGE — NOT A RAW-DATA BACKUP

仅代码、交接说明、审计摘要和数据索引；不含任何 raw/normalized 大数据、截图、cookie、凭据或内部工具。没有自动安装、启动、预抓取入口。先读 a-share-data-lake/catalog/HANDOFF.md 和 FINAL_SUMMARY.md。

本批数据原存云端 fin_data/legacy-work/a-share-data-lake，不在用户设备；该路径及运行环境不可移植保证，原始大数据未随此包保存。恢复历史数值必须另有原始文件备份或重新获得来源数据；索引和SHA无法重建已丢失的原始字节。现有脚本为冻结批次，不能直接当长期更新器。

为安全，导出JSON/说明已移除HTTP receipts/headers、原始响应样本以及URL查询/片段。原始审计文件不改。PACKAGE_MANIFEST.json同时记录源文件与导出文件SHA、移除统计和明确排除项。公开下载器代码经过文字凭据扫描，无用户密钥；它仍需要人工核对依赖、截止日期、路径、授权和同host限速，禁止直接运行旧版/实验性预抓取。
'''
manifest={'kind':'CODE_AND_INDEX_ONLY_NOT_RAW_DATA_BACKUP','created_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'members':[],'explicitly_excluded':['raw/**','normalized/**','screenshots','HTTP headers/receipts','signed URLs/query strings in exported metadata','environment binaries','plugin/internal helpers','source-review/probes','archived collector versions'],'excluded_code_files':omissions,'portability':'Absolute paths and frozen batch dates require manual review. No auto-execution or automatic prefetch.'}
with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
 z.writestr('CODE_INDEX_RECOVERY_ONLY/README_FIRST.md',readme)
 for p in sorted(selected):
  raw=p.read_bytes();export=raw
  if p.suffix=='.json':export=(json.dumps(scrub(json.loads(raw)),ensure_ascii=False,indent=2)+'\n').encode()
  elif p.suffix=='.md':export=scrub_string(raw.decode()).encode()
  elif p.suffix=='.py':
   # Reject literal secret assignments, never "sanitize" runnable code silently.
   text=raw.decode()
   if re.search(r'(?im)^\s*(?:[A-Z_]*(?:PASSWORD|API_KEY|ACCESS_TOKEN|SECRET)[A-Z_]*)\s*=\s*[\"\'][^\"\']+[\"\']',text):raise ValueError('Potential credential literal: '+str(p))
   if re.search(r'(?i)https?://[^\s\"\']*(?:X-Amz-Signature|X-Goog-Signature|sig=)',text):raise ValueError('Signed URL in code: '+str(p))
  member='CODE_INDEX_RECOVERY_ONLY/a-share-data-lake/'+str(p.relative_to(R))
  z.writestr(member,export);manifest['members'].append({'path':member,'source_sha256':hashlib.sha256(raw).hexdigest(),'export_sha256':hashlib.sha256(export).hexdigest(),'source_bytes':len(raw),'export_bytes':len(export),'sanitized':raw!=export})
 manifest['sanitization_counts']=counts;z.writestr('CODE_INDEX_RECOVERY_ONLY/PACKAGE_MANIFEST.json',json.dumps(manifest,ensure_ascii=False,indent=2))
assert target.stat().st_size<20*1024**2
with zipfile.ZipFile(target)as z:
 assert z.testzip()is None
 for x in manifest['members']:
  assert hashlib.sha256(z.read(x['path'])).hexdigest()==x['export_sha256']
 names=z.namelist()
 assert not any('/raw/'in x or '/normalized/'in x or x.endswith(('.png','.jpg','.xlsx','.parquet'))for x in names)
report={'file':str(target.resolve()),'bytes':target.stat().st_size,'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'members':len(manifest['members'])+2,'sanitization_counts':counts,'zip_crc_and_member_sha_verified':True,'contains_raw_or_normalized_data':False,'contains_library_or_internal_helpers':False,'type':'CODE+INDEX recovery package, NOT full data backup'}
(R/'catalog/package-build-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps(report,ensure_ascii=False))
