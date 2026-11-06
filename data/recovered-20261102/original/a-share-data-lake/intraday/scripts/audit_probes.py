import json,pathlib,csv,gzip,hashlib,datetime
R=pathlib.Path(__file__).resolve().parents[1];result=[]
for p in R.joinpath('probes').glob('*-1m.jsonp'):
 s=p.read_text();a=json.loads(s[s.index('=(')+2:s.rindex(');')]);sym=p.name.split('-')[0]
 pos=[x for x in a if float(x['volume'])>0]
 shares=sum(float(x['low'])-.02<=float(x['amount'])/float(x['volume'])<=float(x['high'])+.02 for x in pos)
 lots=sum(float(x['low'])-.02<=float(x['amount'])/(float(x['volume'])*100)<=float(x['high'])+.02 for x in pos)
 dp=R.parent/'market/normalized'/f'{sym}.csv.gz'
 with gzip.open(dp,'rt') as f: day=next(x for x in csv.DictReader(f) if x['date']=='2026-10-30')
 v=[x for x in a if x['day'].startswith('2026-10-30')]
 result.append({'instrument':sym,'rows':len(a),'raw_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'positive_volume_rows':len(pos),'vwap_within_ohlc_as_shares':shares,'vwap_within_ohlc_as_lots100':lots,'target_day_rows':len(v),'intraday_sum_volume_shares':sum(float(x['volume']) for x in v),'independent_daily_volume_shares':float(day['volume_shares']),'intraday_sum_amount_cny':sum(float(x['amount']) for x in v),'independent_daily_amount_cny':float(day['amount_cny']),'daily_source_sha256':hashlib.sha256(dp.read_bytes()).hexdigest(),'ohlc_intraday':[float(v[0]['open']),max(float(x['high']) for x in v),min(float(x['low']) for x in v),float(v[-1]['close'])],'ohlc_independent_daily':[float(day[k]) for k in ['open','high','low','close']]})
(R/'catalog/probe-unit-audit.json').write_text(json.dumps({'generated_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'basis':'Sina minute volume shares supported by amount/VWAP and Tencent independently normalized daily units; vendor SDK does not explicitly certify units. Not applicable to daily APIs. BJ has residual warnings.','adjustment':'Sina empty-adjust documented unadjusted; observed prices match independent daily unadjusted on these probes','timezone':'Asia/Shanghai inferred documentedChinaexchange session; source strings no offset','results':result},ensure_ascii=False,indent=2))
