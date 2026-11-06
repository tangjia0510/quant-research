"""New immutable latest-period snapshots after historical acquisition; no original rewrite."""
import pathlib,datetime
import acquire_full_statements as full
import acquire_special_financials as special
import acquire_supplemental as supp
ROOT=pathlib.Path(__file__).resolve().parent/'financial_refreshes'/datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
for name,module,periods in [('full',full,['2026-09-30']),('industry',special,['2026-09-30']),('forward_forecasts',supp,['2026-12-31'])]:
 module.ROOT=ROOT/name;module.ROOT.mkdir(parents=True,exist_ok=True);module.PERIODS=periods
 if name=='forward_forecasts':module.REPORTS={'forecast':'RPT_PUBLIC_OP_NEWPREDICT'}
 result=module.main()
 if result:raise RuntimeError(f'{name} returned {result}')
