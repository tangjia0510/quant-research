"""Reference existing independent HF valuation history for API no-data codes; never stitch vendors."""
import pathlib,csv,json,datetime,collections
import pyarrow.dataset as ds
ROOT=pathlib.Path(__file__).resolve().parent;MARKET=ROOT.parent/'market';j=json.loads((ROOT/'valuations/catalog/progress.json').read_text());unavailable={x['code']:x for x in j['tasks']if x['status']=='unavailable'}
rows=[];coverage={x['code'].split('.')[0]:x for x in csv.DictReader((MARKET/'hf_bulk/coverage.csv').open())};matches={code:coverage[code]for code in unavailable if code in coverage}
fields=['pe','pe_ttm','pb','ps','ps_ttm','dv_ratio','dv_ttm','total_share','float_share','free_share','total_mv','circ_mv']
if matches:
 dataset=ds.dataset(MARKET/'hf_bulk/raw',format='parquet');table=dataset.to_table(columns=['code','date']+fields,filter=ds.field('code').isin([v['code']for v in matches.values()]));groups=collections.defaultdict(list)
 for x in table.to_pylist():groups[x['code']].append(x)
 for code,meta in matches.items():
  data=groups[meta['code']];rows.append({'instrument':unavailable[code]['instrument'],'eastmoney_status':'unavailable','independent_source':'market/hf_bulk','source_code':meta['code'],'rows':len(data),'first_date':meta['min_date'],'last_date':meta['max_date'],'duplicate_code_dates':int(meta['duplicate_dates']),'field_nonnull_counts':{f:sum(x[f]is not None for x in data)for f in fields},'canonical_stitch_allowed':False,'pit_ready':False,'source_metadata':'market/hf_bulk/metadata','source_coverage':'market/hf_bulk/coverage.csv','note':'Historical alternative exists; does not supply latest daily data or prove matching financial definitions. Read original raw source columns; no imputation.'})
quarantined={x['code'].split('.')[0]:x for x in csv.DictReader((MARKET/'hf_features/coverage.csv').open())}
result={'generated_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'eastmoney_attempted':len(j['tasks']),'eastmoney_unavailable':len(unavailable),'independent_nonquarantined_history_matches':len(rows),'entries':rows,'quarantined_feature_matches_not_accepted':sorted(set(unavailable)&set(quarantined)),'unavailable_without_nonquarantined_local_history':sorted(set(unavailable)-set(matches)),'limitations':['Alternate coverage index only. API no-data statuses remain unchanged; source definitions and units must be retained independently.','HF feature dataset is quarantined and is not counted as a resolved valuation gap.','No disclosure-time or historical-restatement guarantee; no cross-vendor value stitching.']}
(ROOT/'catalog/alternate-valuation-coverage.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(len(unavailable),len(rows))
