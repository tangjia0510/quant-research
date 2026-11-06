"""Current fiscal-year guidance, separately from realized statement quarters."""
from pathlib import Path
import acquire_supplemental as a
a.ROOT=Path(__file__).resolve().parent/'forward_forecasts'
a.ROOT.mkdir(exist_ok=True)
a.REPORTS={'forecast':'RPT_PUBLIC_OP_NEWPREDICT'}
a.PERIODS=['2026-12-31']
if __name__=='__main__':a.main()
