import csv,json,pathlib,requests,hashlib,datetime
R=pathlib.Path(__file__).resolve().parents[1];fields=['BUY_AMT','SELL_AMT','NET_DEAL_AMT','FUND_INFLOW','ACCUM_DEAL_AMT','QUOTA_BALANCE','HOLD_MARKET_CAP'];reports=[]
for name in ['northbound_total','shanghai_connect','shenzhen_connect']:
 p=R/'normalized'/f'{name}.csv';rs=list(csv.DictReader(p.open()));stats={}
 for reg in ['before_2024_08_19','on_after_2024_08_19']:
  subset=[x for x in rs if (x['TRADE_DATE'][:10]<'2024-08-19')==(reg.startswith('before'))]
  stats[reg]={'rows':len(subset),'fields':{f:{'nonnull':sum(x.get(f,'')!='' for x in subset),'zero':sum(x.get(f) in ['0','0.0','0.00'] for x in subset)} for f in fields}}
 for row in rs:
  post=row['TRADE_DATE'][:10]>='2024-08-19';row['disclosure_regime']='post_2024_08_19_limited' if post else 'pre_2024_08_19';row['net_flow_available']=not post and row.get('NET_DEAL_AMT','')!=''
  if post:
   for f in fields:row[f]=''
 with (R/'normalized'/f'{name}_disclosure_aware.csv').open('w') as f:w=csv.DictWriter(f,fieldnames=list(rs[0]));w.writeheader();w.writerows(rs)
 reports.append({'name':name,'stats':stats,'warning':'Raw vendor rows retained unchanged; post-regime no daily directional flow/custody value inferred from zero/placeholders. Use disclosure-aware view.'})
u='https://www.hkex.com.hk/-/media/HKEX-Market/Services/Circulars-and-Notices/Participant-and-Members-Circulars/HKSCC/2024/ce_HKSCC_NOM_217_2024.pdf'
r=requests.get(u,timeout=35);r.raise_for_status();p=R/'raw/hkex-disclosure-change-2024.pdf';p.write_bytes(r.content)
(R/'logs/flow-disclosure-audit.json').write_text(json.dumps({'official_source':u,'source_sha256':hashlib.sha256(r.content).hexdigest(),'retrieved_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'records':reports},ensure_ascii=False,indent=2))
