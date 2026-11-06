"""Immutable refresh of current publication window across local-day rollover."""
import datetime,pathlib
import acquire_disclosures as a
stamp=datetime.datetime.now(datetime.timezone.utc)
local=stamp.astimezone(datetime.timezone(datetime.timedelta(hours=8))).date()
a.ROOT=pathlib.Path(__file__).resolve().parent/'disclosure_refreshes'/stamp.strftime('%Y%m%dT%H%M%SZ')
a.ROOT.mkdir(parents=True)
a.PERIODS=[('2026-11-01',local.isoformat())]
if __name__=='__main__':a.main()
