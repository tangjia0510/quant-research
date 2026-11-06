"""Conservative source-reported price-limit lookup. Not a tradeability oracle."""
from pathlib import Path
import sqlite3
class LimitStore:
 def __init__(self,path=None):
  self.path=Path(path or Path(__file__).with_name('daily_limits.sqlite')).resolve()
  self.connection=sqlite3.connect(f'file:{self.path}?mode=ro',uri=True)
 def get(self,instrument,date):
  row=self.connection.execute('SELECT upper_limit,lower_limit,quality FROM daily_limits WHERE instrument=? AND date=?',(instrument,date)).fetchone()
  base={'instrument':instrument,'date':date,'source':'https://huggingface.co/datasets/ellendan/a-share-prices','evidence':'source_reported_not_exchange_certified','tradable':None}
  if row is None:return {**base,'status':'unknown','reason':'no_source_row','upper_limit':None,'lower_limit':None}
  hi,lo,q=row
  if q!='source_reported_numeric':return {**base,'status':'unknown','reason':q,'upper_limit':None,'lower_limit':None}
  return {**base,'status':'reported','reason':None,'upper_limit':hi,'lower_limit':lo}
 def close(self):self.connection.close()
