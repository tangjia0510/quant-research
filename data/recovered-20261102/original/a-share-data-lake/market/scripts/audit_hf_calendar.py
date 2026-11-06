#!/usr/bin/env python3
# PUBLIC SANITIZED COPY (2026-11-06): machine paths generalized; see provenance/publication_transformations.json.
import collections,datetime as dt,json
from pathlib import Path
import pyarrow.parquet as pq
M=Path(__file__).resolve().parents[1];H=M/'hf_bulk';C=M.parents[1]/'fin_data/legacy-inputs/mixed-source/calendar.txt'
calendar=[s for s in C.read_text().splitlines() if s<='2026-03-03'];counts=collections.Counter();dates={}
for f in sorted((H/'normalized_prices').glob('*.parquet')):
 for b in pq.ParquetFile(f).iter_batches(batch_size=100000,columns=['instrument','date']):
  d=b.to_pandas();d['date']=d.date.astype(str);d=d[d.date>='2019-01-01']
  counts.update(d.date)
  for code,g in d.groupby('instrument'):dates.setdefault(code,set()).update(g.date)
bydate=collections.Counter();stock_gaps=[]
for code,observed in dates.items():
 lo=min(observed);hi=max(observed);gaps=[d for d in calendar if lo<=d<=hi and d not in observed];bydate.update(gaps)
 stock_gaps.append({'instrument':code,'first_observed':lo,'last_observed':hi,'missing_within_observed_span':len(gaps),'missing_dates':gaps})
zero=[d for d in calendar if not counts[d]]
result={'generated_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'codes':len(dates),'expected_calendar_sessions':len(calendar),'global_zero_observation_dates':zero,'daily_observed_code_counts':dict(sorted(counts.items())),'missing_within_observed_span_by_date':dict(sorted(bydate.items())),'total_code_date_gaps_within_observed_span':sum(bydate.values()),'per_stock':stock_gaps,'limits':['Expected calendar derived from SSEComposite public vendor observations, not exchange certified','Within observed span only, excludes unknown boundary coverage','Per-stock gaps may include suspensions or omissions; global zero days require source supplementation','No missing prices fabricated']}
(H/'calendar-audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k not in ['per_stock','daily_observed_code_counts','missing_within_observed_span_by_date']},ensure_ascii=False))
