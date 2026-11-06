import requests,time,json,hashlib,csv,datetime,pathlib,shutil,re
ROOT=pathlib.Path(__file__).resolve().parents[1];BASE='https://data.stats.gov.cn/dg/website/publicrelease/web/external/';S=requests.Session();S.headers.update({'Referer':'https://data.stats.gov.cn/dg/website/page.html','User-Agent':'Mozilla/5.0','Accept':'application/json'})
OUT=ROOT/'raw/nbs';OUT.mkdir(exist_ok=True); recs=json.loads((ROOT/'logs/nbs-receipts.json').read_text()) if (ROOT/'logs/nbs-receipts.json').exists() else [];fails=[];catalog=[];count=0
F=(ROOT/'normalized/nbs_national.tmp.csv').open('w');W=csv.DictWriter(F,fieldnames=['frequency','catalog_path','period','indicator_id','indicator_name','unit','value','source_file','publication_date','vintage']);W.writeheader()
def fetch(endpoint,params=None,payload=None):
 global count
 key=hashlib.sha256(json.dumps([endpoint,params,payload],sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:20];p=OUT/(key+'.json');url=BASE+endpoint
 if p.exists():return json.loads(p.read_text()),str(p.relative_to(ROOT))
 if shutil.disk_usage(ROOT).free<15*1024**3:raise RuntimeError('global_free_disk_floor')
 for attempt in range(3):
  time.sleep(1.1)
  try:
   r=S.post(url,json=payload,timeout=45) if payload else S.get(url,params=params,timeout=45)
   if r.status_code in [401,403,429]:raise PermissionError(f'Access/rate restriction HTTP{r.status_code}')
   r.raise_for_status();d=r.json()
   if d.get('success') is False:raise ValueError(str(d)[:300])
   p.write_bytes(r.content);count+=1;recs.append({'file':str(p.relative_to(ROOT)),'url':r.url,'request_json':payload,'sha256':hashlib.sha256(r.content).hexdigest(),'retrieved_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'bytes':len(r.content)})
   (ROOT/'logs/nbs-receipts.json').write_text(json.dumps(recs,ensure_ascii=False,indent=2));return d,str(p.relative_to(ROOT))
  except PermissionError:raise
  except Exception as e:
   if attempt==2:fails.append({'url':url,'params':params,'payload':payload,'error':str(e)});return {},''
   time.sleep(3*(attempt+1))
try:
 for code,freq,dts in [(2,'quarterly','201901SS-202603SS'),(1,'monthly','201901MM-202610MM'),(3,'annual','2019YY-2025YY')]:
  d,_=fetch('new/queryIndexTreeAsync',{'pid':'','code':code});roots=d.get('data',[])
  if not roots:continue
  root=roots[0]['_id'];queue=[(root,roots[0].get('name',freq),0)];seen=set()
  while queue:
   cid,path,depth=queue.pop(0)
   if cid in seen:continue
   seen.add(cid)
   # Annual covers macro/finance/economy, avoiding thousands of demographic and local subseries in this pass.
   d,_=fetch('new/queryIndexTreeAsync',{'pid':cid,'code':code});children=d.get('data',[])
   if children:
    for child in children:
     name=child.get('name',child.get('_name',''))
     historic=re.search(r'[(（](?:19|20)\d{2}\s*[-—至]\s*((?:19|20)\d{2})[)）]',name)
     if historic and int(historic.group(1))<2019:continue
     if code==3 and depth==0 and not any(k in name for k in ['国民经济','价格','金融','财政','工业','投资','贸易','对外','能源','房地产','综合']):continue
     queue.append((child['_id'],path+' > '+name,depth+1))
    continue
   d,_=fetch('new/queryIndicatorsByCid',{'cid':cid,'dt':'','name':''});inds=d.get('data',{}).get('list',[])
   if not inds:continue
   ids=[x['_id'] for x in inds];lookup={x['_id']:x for x in inds}
   payload={'cid':cid,'indicatorIds':ids,'daCatalogId':'','das':[{'text':'全国','value':'000000000000'}],'showType':'1','rootId':root,'dts':[dts]}
   d,src=fetch('stream/esData',payload=payload);data=d.get('data',[]);n=0
   for period in data:
    for val in period.get('values',[]):
     id_=val.get('_id') or val.get('id') or val.get('indicatorId','');meta=lookup.get(id_,{})
     W.writerow({'frequency':freq,'catalog_path':path,'period':period.get('name',''),'indicator_id':id_,'indicator_name':val.get('i_showname') or val.get('ek_dp_name') or val.get('_name',''),'unit':val.get('du_name') or val.get('unit') or val.get('unit_name') or meta.get('unit',''),'value':val.get('value',''),'source_file':src,'publication_date':'','vintage':'latest_revised_as_retrieved_not_point_in_time'});n+=1
   F.flush();catalog.append({'cid':cid,'path':path,'frequency':freq,'indicators':len(ids),'periods':len(data),'rows':n,'source_file':src});(ROOT/'logs/nbs-coverage.json').write_text(json.dumps(catalog,ensure_ascii=False,indent=2));print(freq,path,n,flush=True)
except Exception as e:fails.append({'terminal':True,'error':repr(e)});print('STOP',repr(e),flush=True)
finally:
 F.close();(ROOT/'normalized/nbs_national.tmp.csv').replace(ROOT/'normalized/nbs_national.csv');(ROOT/'logs/nbs-failures.json').write_text(json.dumps(fails,ensure_ascii=False,indent=2));print('DONE',count,len(catalog),len(fails),flush=True)
