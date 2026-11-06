"""Read-only integrity and cached daily reconciliation. Writes only intraday/catalog."""
import collections,csv,gzip,hashlib,io,json,pathlib,sys,datetime
from collect import ROOT,LAKE,parse,norm,sha,js,now,TARGET

def main():
 universe=list(csv.DictReader((ROOT/'catalog/universe.csv').open()))
 statuses=[];errors=[];comparisons=[];dist=collections.Counter();counts=collections.Counter();warnings=collections.Counter();boards={};raw_bytes=normalized_bytes=0
 for u in universe:
  sym=u['instrument'].replace('.','');sp=ROOT/'catalog/status'/f'{sym}.json'
  if not sp.exists():continue
  s=json.loads(sp.read_text());statuses.append(s);counts[s['status']]+=1
  board=boards.setdefault(u['board'],{'instruments':0,'rows':0,'latest_days':{},'status_counts':{}});board['instruments']+=1;board['rows']+=s.get('rows',0);board['status_counts'][s['status']]=board['status_counts'].get(s['status'],0)+1
  latest=s.get('latest_day','no_normalized_data');dist[latest]+=1;board['latest_days'][latest]=board['latest_days'].get(latest,0)+1
  warnings.update(s.get('warnings',{}))
  try:
   r=s.get('receipt')
   if r:
    z=(ROOT/r['raw_file']).read_bytes();raw_bytes+=len(z);b=gzip.decompress(z)
    assert sha(z)==r['stored_sha256'],'raw_stored_hash';assert sha(b)==r['raw_sha256'],'raw_payload_hash'
   if not s.get('normalized_file'):continue
   z=(ROOT/s['normalized_file']).read_bytes();normalized_bytes+=len(z);assert sha(z)==s['normalized_sha256'],'normalized_hash'
   rows=list(csv.DictReader(io.StringIO(gzip.decompress(z).decode())));assert len(rows)==s['rows'],'rowcount'
   raw_rows=parse(b);expected,ww=norm(raw_rows,sym);assert len(expected)==len(rows),'raw_norm_rowcount'
   assert ww==s['warnings'],'warnings_changed'
   for e,n in zip(expected,rows):
    for k,v in e.items():assert (float(n[k])==v if isinstance(v,(float,int)) else n[k]==v),f'raw_norm_value:{k}'
   assert rows[0]['timestamp_local']==s['first_timestamp'] and rows[-1]['timestamp_local']==s['last_timestamp'],'timestamp_bounds'
   byday=collections.defaultdict(list)
   for x in rows:byday[x['timestamp_local'][:10]].append(x)
   daily=LAKE/'market/normalized'/f'{sym}.csv.gz'
   if not daily.exists():continue
   with gzip.open(daily,'rt') as f:dailyrows={x['date']:x for x in csv.DictReader(f) if x['date'] in byday}
   for day,rr in byday.items():
    # Exclude first observed day even if it happens to start at open: bounded window may truncate it.
    if day==rows[0]['timestamp_local'][:10] or day not in dailyrows:continue
    d=dailyrows[day]
    # Full-session-shaped windows only; this never implies all trades or 240 bars.
    if rr[0]['timestamp_local'][11:16]>'09:35' or rr[-1]['timestamp_local'][11:16]<'14:55':continue
    agg={'open':float(rr[0]['open']),'high':max(float(x['high']) for x in rr),'low':min(float(x['low']) for x in rr),'close':float(rr[-1]['close']),'volume_shares':sum(float(x['volume_shares']) for x in rr),'amount_cny':sum(float(x['amount_cny']) for x in rr)}
    item={'instrument':sym,'board':u['board'],'date':day,'observed_minute_bars':len(rr),'ohlc_match_within_cent':all(abs(agg[k]-float(d[k]))<=.01000001 for k in ['open','high','low','close'])}
    for k in ['volume_shares','amount_cny']:
     item['minute_'+k]=agg[k];item['daily_'+k]=float(d[k]);item[k+'_relative_difference']=(agg[k]-float(d[k]))/float(d[k]) if float(d[k]) else None
    comparisons.append(item)
  except Exception as e:errors.append({'instrument':sym,'error':str(e)})
 path=ROOT/'catalog/daily-reconciliation.csv.gz'
 if comparisons:
  stream=io.StringIO();w=csv.DictWriter(stream,fieldnames=list(comparisons[0]));w.writeheader();w.writerows(comparisons);path.write_bytes(gzip.compress(stream.getvalue().encode(),mtime=0))
 summary={'generated_at_utc':now(),'scope':'recent source-bounded 1-minute bars only; no full-history or tick coverage','expected_instruments':len(universe),'terminal_instruments':len(statuses),'pending':len(universe)-len(statuses),'source_http_200_instruments':sum(s.get('receipt',{}).get('http_status')==200 for s in statuses),'statuses':dict(counts),'normalized_instruments':sum(bool(s.get('normalized_file')) for s in statuses),'normalized_rows':sum(s.get('rows',0) for s in statuses),'latest_day_distribution':dict(sorted(dist.items())),'boards':boards,'warnings_by_row':dict(warnings),'integrity_errors':errors,'raw_stored_bytes':raw_bytes,'normalized_stored_bytes':normalized_bytes,'reconciliation':{'comparisons':len(comparisons),'ohlc_within_cent':sum(x['ohlc_match_within_cent'] for x in comparisons),'volume_within_1pct':sum(x['volume_shares_relative_difference'] is not None and abs(x['volume_shares_relative_difference'])<=.01 for x in comparisons),'caveat':'Existing Tencent daily vs Sina minute observations. First observed day excluded; only windows spanning 09:35 or earlier through 14:55 or later considered. Sparse/no-trade/auction omissions and source differences remain; this is not complete transaction coverage.','file':str(path.relative_to(ROOT)) if comparisons else None}}
 js(ROOT/'catalog/audit.json',summary)
 manifest=[]
 for base in ['raw','normalized','probes']:
  for p in sorted((ROOT/base).glob('*')):
   if p.is_file():manifest.append({'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'sha256':sha(p.read_bytes())})
 js(ROOT/'catalog/file-manifest.json',{'generated_at_utc':now(),'files':manifest})
 print(json.dumps({k:v for k,v in summary.items() if k not in ['boards','latest_day_distribution']},ensure_ascii=False))
if __name__=='__main__':main()
