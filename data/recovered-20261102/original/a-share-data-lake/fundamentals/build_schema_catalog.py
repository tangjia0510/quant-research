"""Snapshot observed fields/types; no inferred units or unverified publication semantics."""
import pathlib,json,datetime,collections
import pyarrow.parquet as pq
ROOT=pathlib.Path(__file__).resolve().parent
SOURCES=[ROOT,ROOT/'supplemental',ROOT/'full_statements',ROOT/'special_financials',ROOT/'forward_forecasts',ROOT/'pagination_repairs/forecast-stable-v1']+sorted((ROOT/'financial_refreshes').glob('*/*'))
entries=[]
for base in SOURCES:
 groups=collections.defaultdict(list)
 for p in (base/'catalog').glob('*/*.json'):
  j=json.loads(p.read_text())
  if j.get('status')=='success' and j.get('parquet_path'):groups[j['report']].append(j)
 for report,parts in groups.items():
  fields=collections.defaultdict(lambda:{'types':set(),'partitions_present':0})
  for part in parts:
   for f in pq.read_schema(base/part['parquet_path']):
    fields[f.name]['types'].add(str(f.type));fields[f.name]['partitions_present']+=1
  entries.append({'collection':str(base.relative_to(ROOT)),'report':report,'partitions_observed':len(parts),'field_count':len(fields),'fields':{name:{'types':sorted(v['types']),'partitions_present':v['partitions_present'],'unit':'source-native; not independently verified'}for name,v in sorted(fields.items())}})
result={'generated_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'entries':entries,'semantics':{'REPORT_DATE/REPORTDATE':'Fiscal period end, not publication date','NOTICE_DATE':'Vendor formal notice date, not proof of numeric revision first availability','UPDATE_DATE/EITIME':'Vendor update fields retained; not verified historical revision vintages','CURRENCY/ORG_TYPE':'Preserve per-row currency and industry/accounting subtype; do not assume all tables share monetary units','_pit_ready':'False throughout: snapshots lack historical numeric revision vintages'},'limitation':'Observed schema catalog only. All raw vendor values are preserved without scaling; fields/types can differ by period and financial-sector subtype. Field availability is not unit certification.'}
(ROOT/'catalog/observed-schemas.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(len(entries),'schemas')
