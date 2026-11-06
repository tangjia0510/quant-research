import pathlib,json,csv,datetime,collections
R=pathlib.Path(__file__).resolve().parents[1];recs={}
for l in (R/'logs/fund-receipts.jsonl').read_text().splitlines():
 x=json.loads(l);recs[x['code']]=x
stats=[]
for code,r in recs.items():
 if r.get('data_kind')!='money_fund_income':continue
 p=R/'normalized/funds'/(code+'-money-income.csv');rows=list(csv.DictReader(p.open())) if p.exists() else [];dates=[x['date'] for x in rows];dupes=len(dates)-len(set(dates));bad=[]
 for x in rows:
  for f in ['income_per_10000_units_as_published','seven_day_annualized_yield_percent']:
   if x.get(f) not in [None,'']:
    try:float(x[f])
    except ValueError:bad.append([x['date'],f,x[f]])
 stats.append({'code':code,'rows':len(rows),'expected_rows':r.get('money_income_rows'),'duplicates':dupes,'bad_numeric_values':bad,'min_date':min(dates,default=None),'max_date':max(dates,default=None)})
obj={'generated_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'money_funds':len(stats),'income_rows':sum(x['rows'] for x in stats),'issues':[x for x in stats if x['rows']!=x['expected_rows'] or x['duplicates'] or x['bad_numeric_values']],'series':stats,'note':'Income per10000units and seven-day annualized yield percent, not NAV or daily realized returns; empty fields remain empty.'};(R/'logs/money-fund-audit.json').write_text(json.dumps(obj,indent=2));print(obj['money_funds'],obj['income_rows'],len(obj['issues']))
