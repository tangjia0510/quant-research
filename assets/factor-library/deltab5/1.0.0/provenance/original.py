import pandas as pd
import numpy as np


def calculate_deltaB5():
    df = pd.read_hdf('daily_pv.h5', key='data')
    df = df.sort_index()

    close = df['$close']

    # per-instrument rolling computations
    grp = close.groupby(level='instrument', group_keys=False)

    sma20 = grp.apply(lambda s: s.rolling(window=20, min_periods=20).mean())
    std20 = grp.apply(lambda s: s.rolling(window=20, min_periods=20).std(ddof=0))

    z20 = (close - sma20) / std20
    pctB = z20 / 4.0 + 0.5  # intermediate only

    # 5-session change in %B, per instrument
    pctB_grp = pctB.groupby(level='instrument', group_keys=False)
    pctB_lag5 = pctB_grp.apply(lambda s: s.shift(5))

    deltaB5 = pctB - pctB_lag5

    out = deltaB5.rename('deltaB5').to_frame()
    out.to_hdf('result.h5', key='data', mode='w')
    print(out.info())


if __name__ == '__main__':
    calculate_deltaB5()
