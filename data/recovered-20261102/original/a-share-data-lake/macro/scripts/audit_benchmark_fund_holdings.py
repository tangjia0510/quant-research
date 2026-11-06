import pathlib,json,csv,hashlib,datetime,re
R=pathlib.Path(__file__).resolve().parents[1];coverage=json.loads((R/'logs/fund-holdings-coverage.json').read_text());rows=[];issues=[];D=json.JSONDecoder()
for rec in coverage:
 p=R/rec['raw_file'];text=p.read_text();sha=hashlib.sha256(p.read_bytes()).hexdigest();rr=list(csv.DictReader((R/rec['file']).open()));m=re.search(r'\bcontent\s*:\s*',text);html=D.raw_decode(text[m.end():])[0] if m else ''
 if sha!=rec['sha256']:issues.append({'code':rec['code'],'year':rec['year'],'error':'rawsha'})
 if len(rr)!=rec['rows']:issues.append({'code':rec['code'],'year':rec['year'],'error':'rowcount'})
 if rr and not re.search(r'fund\.eastmoney\.com/'+rec['code']+r'\.html',html):issues.append({'code':rec['code'],'year':rec['year'],'error':'fund identity link absent'})
 for x in rr:
  if not x['report_period_end'].startswith(str(rec['year'])):issues.append({'code':rec['code'],'year':rec['year'],'error':'reportyear'})
 rows+=rr
keys=[(x['fund_code'],x['report_period_end'],x['security_code']) for x in rows];groups={}
for x in rows:groups.setdefault((x['fund_code'],x['report_period_end']),[]).append(x)
for k,v in groups.items():
 ranks=[int(x['rank']) for x in v]
 if len(ranks)!=len(set(ranks)):issues.append({'fund_period':k,'error':'rankduplicate'})
obj={'generated_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'state':'completed_selected_fund_first_pass','fund_year_responses':len(coverage),'funds':len({x['code'] for x in coverage}),'rows':len(rows),'fund_report_periods':len(groups),'duplicate_security_keys':len(keys)-len(set(keys)),'rows_per_period_distribution':{str(n):sum(len(v)==n for v in groups.values()) for n in sorted({len(v) for v in groups.values()})},'source_and_row_issues':issues,'min_period_end':min(x['report_period_end'] for x in rows),'max_period_end':max(x['report_period_end'] for x in rows),'scope':'Nine selectedETF; returnedtop10positionsperquarter, not full portfolio; publication dates unknown; displayed10kunit values retain rounding'};(R/'logs/fund-holdings-audit.json').write_text(json.dumps(obj,ensure_ascii=False,indent=2));print(obj)
