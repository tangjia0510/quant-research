import json,csv,hashlib,datetime,collections
from pathlib import Path
R=Path(__file__).resolve().parents[1];B=R/'actions';blob=(B/'catalog/factor-status.json').read_bytes();d=json.loads(blob);bad=[];sentinel=0;events=0;unavailable=[];states=collections.Counter()
for code,item in d['items'].items():
 states[item['status']]+=1;sym=code.replace('.','');raw=B/'raw/sina_factors'/f'{sym}.js';norm=B/'normalized/factors'/f'{sym}.csv'
 if item['status']!='complete':
  if not raw.exists() or hashlib.sha256(raw.read_bytes()).hexdigest()!=item.get('raw_sha256'):bad.append([code,'unavailable_raw_sha'])
  if norm.exists():bad.append([code,'unavailable_has_normalized_output'])
  unavailable.append({'instrument':code,'source_state':item,'raw_exists':raw.exists(),'raw_text':raw.read_text() if raw.exists() else None,'normalized_exists':norm.exists()});continue
 try:
  rb=raw.read_bytes();nb=norm.read_bytes();text=rb.decode();obj,_=json.JSONDecoder().raw_decode(text[text.index('{'):]);expected=sorted((r['d'],str(r['f'])) for r in obj['data']);rows=list(csv.DictReader(nb.decode().splitlines()));actual=sorted((r['effective_date'],r['factor']) for r in rows)
  if hashlib.sha256(rb).hexdigest()!=item['raw_sha256']:bad.append([code,'raw_sha'])
  if hashlib.sha256(nb).hexdigest()!=item['normalized_sha256']:bad.append([code,'norm_sha'])
  if expected!=actual:bad.append([code,'raw_vs_normalized_values'])
  if len(actual)!=item['events'] or len(actual)!=obj['total']:bad.append([code,'counts'])
  sentinel+=sum(day<'1990-01-01' for day,f in expected);events+=len(actual)
 except Exception as e:bad.append([code,str(e)])
out={'audited_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'checkpoint_sha256':hashlib.sha256(blob).hexdigest(),'target_count':d['target_count'],'attempted':len(d['items']),'states':dict(states),'events_including_basis_sentinels':events,'basis_sentinels_present_in_raw_source':sentinel,'non_sentinel_rows':events-sentinel,'issues':bad,'unavailable':unavailable,'sentinel_provenance':'Matched each normalized date/factor against JSON parsed directly from saved raw Sina JS without execution. Pre1990 rows were in provider response, not added default.','scope':'Local artifact integrity/source availability only; does not certify corporate-event completeness, market truth, or PIT vintages.'}
(R/'catalog/factors-final-independent-audit.json').write_text(json.dumps(out,ensure_ascii=False,indent=2));print({k:v for k,v in out.items() if k not in ['unavailable']})
