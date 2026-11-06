"""Local-only re-normalization after audited STAR source-unit correction; archive old artifacts."""
import gzip,hashlib,json,shutil
from pathlib import Path
import acquire_tencent_daily as m
archive=m.ROOT/'normalizer_revisions/pre-v4-star-units';archive.mkdir(parents=True,exist_ok=True)
oldget=m.Collector.get

def local_get(self,code,start,end):
 assert (m.ROOT/'raw'/code/(start[:4]+'.json.gz')).exists(), 'No network allowed in unit correction'
 return oldget(self,code,start,end)
m.Collector.get=local_get
collector=m.Collector();calendar=(m.CACHE/'calendar.txt').read_text().splitlines();revisions=[]
for p in sorted((m.ROOT/'status').glob('sh68*.json')):
 old=json.loads(p.read_text());code=old['instrument']
 if not code.startswith(('sh688','sh689')) or old.get('normalizer_version')=='v4-star-volume-units':continue
 for rel in ['status/'+p.name,old['normalized_file']]:
  a=archive/rel;a.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(m.ROOT/rel,a)
 new=collector.stock(old['source_list_record'],calendar)
 revisions.append({'instrument':code,'old_state':old['state'],'new_state':new['state'],'old_csv_sha256':old['normalized_csv_sha256'],'new_csv_sha256':new['normalized_csv_sha256'],'old_issue_count':len(old['validation_issues']),'new_issue_count':len(new['validation_issues'])})
assert collector.network_requests==0
m.atomic(m.ROOT/'star-normalization-correction.json',{'normalizer_version':'v4-star-volume-units','scope':'STAR 688/689 raw volume in shares, normalized lots=raw/100; other stocks raw lots unchanged','evidence':'star-volume-unit-audit.json + public source project changelog v3.10.1','primary_implementation_url':'https://raw.githubusercontent.com/simonlin1212/a-stock-data/main/CHANGELOG.md','old_artifacts_archive':str(archive.relative_to(m.ROOT)),'network_requests':0,'revisions':revisions});print(len(revisions),'corrected; newstates',set(x['new_state'] for x in revisions))
