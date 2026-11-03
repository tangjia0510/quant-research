from pathlib import Path
import json,hashlib,zipfile,datetime,shutil
P=Path(__file__).resolve().parents[1];W=P.parents[2];O=P/'outputs';R=Path(json.loads((O/'native-study.json').read_text())['workspace']);D=W/'deliverables/momentum-optimization-20261102';D.mkdir(exist_ok=True,parents=True);files={}
def add(f,name):
 if f.is_file():files[name]=f
report=R/'supplementary/report'
assert (report/'report.html').exists(),'Report HTML must exist and pass QA first'
for f in report.rglob('*'):
 if f.suffix.lower() in ['.html','.png','.docx','.pdf'] and not any(x in str(f.relative_to(report)).lower() for x in ['qa/','render/','preview/','contact']):add(f,'report/'+str(f.relative_to(report)))
for name in ['protocol.json','study.json','registry.json','events.jsonl']:add(R/name,'native/'+name)
add(R/'report.html','native/generated-report.html');add(R/'report.md','native/generated-report.md')
for f in (R/'candidates').rglob('*'):
 if f.suffix in ['.json','.py'] and '__pycache__' not in str(f):add(f,'native/'+str(f.relative_to(R)))
for f in (R/'runs').rglob('*'):
 if f.suffix in ['.json','.csv'] and f.name!='run.json':add(f,'native/'+str(f.relative_to(R)))
S=R/'supplementary'
for f in S.rglob('*'):
 rel=f.relative_to(S)
 if rel.parts[0] in ['report','observations','execution'] or '__pycache__' in str(rel):continue
 if f.suffix in ['.json','.csv','.py','.jsonl','.log']:add(f,'evidence/'+str(rel))
for name in ['native-command-ledger.jsonl','timing-ledger.json','native-data-factor-regression.log']:add(O/name,'evidence/execution/'+name)
identity={'study':R.name,'root':str(R),'source_dataset':'cn-shsz-audited-quality/2026-11-02-v1','original_plan_sha256':hashlib.sha256((P/'research-plan.json').read_bytes()).hexdigest(),'native_freeze_sha256':hashlib.sha256((R/'freeze.json').read_bytes()).hexdigest(),'prepared_manifest_sha256':hashlib.sha256((R/'data/manifest.json').read_bytes()).hexdigest(),'full_artifact_manifest_sha256':hashlib.sha256((R/'supplementary/final-artifact-manifest.json').read_bytes()).hexdigest(),'raw_or_full_parquet_data_included':False,'native_prediction_rows_included':False,'reason':'Lightweight results packet; full immutable data/provider/predictions remain in workspace study'}
(D/'source-identities.json').write_text(json.dumps(identity,ensure_ascii=False,indent=2));add(D/'source-identities.json','source-identities.json')
readme='量价动量与反转研究｜2026-11-02\n\n先打开 report/report.html。结论：本轮未验证出可准入的有效正向动量因子。\n20日反转存在开发期排序关联，但只是符号翻转；原生Ridge增量准入失败。2026是已暴露回顾性诊断，不是未见测试。\n\n本压缩包包含报告、图表、全部6候选直接IC与分组数据、原生两模型指标/成本曲线、协议/代码/审计与轻量校验。\n不包含原始行情、完整Parquet观测、provider或预测大表；完整研究保存在 source-identities.json 标明的工作区。\n分组5日收益重叠，不能当日收益复利；图中的净值来自另行原生模拟，不代表可成交实盘。\n'
(D/'README.txt').write_text(readme);add(D/'README.txt','README.txt')
manifest={'created_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'files':[{'path':n,'bytes':f.stat().st_size,'sha256':hashlib.sha256(f.read_bytes()).hexdigest()} for n,f in sorted(files.items())]};(D/'delivery-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2));add(D/'delivery-manifest.json','delivery-manifest.json')
z=D/'动量与反转因子优化研究-20261102.zip'
with zipfile.ZipFile(z,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
 for n,f in sorted(files.items()):archive.write(f,n)
with zipfile.ZipFile(z) as archive:
 assert archive.testzip() is None
 for row in manifest['files']:assert hashlib.sha256(archive.read(row['path'])).hexdigest()==row['sha256']
print(json.dumps({'zip':str(z),'bytes':z.stat().st_size,'files':len(files),'sha256':hashlib.sha256(z.read_bytes()).hexdigest()},ensure_ascii=False))
