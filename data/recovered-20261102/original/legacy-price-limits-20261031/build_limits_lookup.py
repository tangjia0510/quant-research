from pathlib import Path
import sqlite3,pyarrow.parquet as pq
B=Path(__file__).parent;p=B/'daily_limits.sqlite'
if p.exists():raise RuntimeError('Refusing to overwrite existing snapshot')
c=sqlite3.connect(p);c.execute('CREATE TABLE daily_limits(instrument TEXT NOT NULL,date TEXT NOT NULL,upper_limit REAL,lower_limit REAL,quality TEXT NOT NULL,PRIMARY KEY(instrument,date)) WITHOUT ROWID')
t=pq.read_table(B/'daily_limits_deduplicated.parquet',columns=['instrument','date','upper_limit','lower_limit','quality']);
for batch in t.to_batches(max_chunksize=10000):c.executemany('INSERT INTO daily_limits VALUES (?,?,?,?,?)',zip(*[col.to_pylist() for col in batch.columns]))
c.commit();print(c.execute('select count(*) from daily_limits').fetchone());c.close()
