import pandas as pd
import numpy as np


def calculate_TREND_RANGE_POS55():
    df = pd.read_hdf('daily_pv.h5', key='data')
    df = df.sort_index()
    idx_names = df.index.names
    full_index = df.index

    out = pd.DataFrame(index=full_index, columns=['TREND_RANGE_POS55'], dtype=float)

    def calc(g):
        g = g.sort_index(level='datetime')
        close = g['$close']
        high = g['$high']
        low = g['$low']
        hh55 = high.rolling(55, min_periods=55).max().shift(5)
        ll55 = low.rolling(55, min_periods=55).min().shift(5)
        rng = hh55 - ll55
        val = (close.shift(5) - ll55) / rng.replace(0, np.nan)
        return val

    grp = df.groupby(level='instrument', group_keys=False)
    vals = grp.apply(calc)
    out['TREND_RANGE_POS55'] = vals

    out.index.names = idx_names
    out.to_hdf('result.h5', key='data', mode='w')


if __name__ == '__main__':
    calculate_TREND_RANGE_POS55()
