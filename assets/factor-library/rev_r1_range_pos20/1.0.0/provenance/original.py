import pandas as pd
import numpy as np


def calculate_RANGE_POS20():
    df = pd.read_hdf('daily_pv.h5', key='data')
    df = df.sort_index()
    close = df['$close']
    low = df['$low']
    high = df['$high']

    min_low = low.groupby(level='instrument').rolling(20, min_periods=20).min().reset_index(level=0, drop=True)
    max_high = high.groupby(level='instrument').rolling(20, min_periods=20).max().reset_index(level=0, drop=True)

    rng = max_high - min_low
    val = (close - min_low) / rng.replace(0.0, np.nan)

    out = pd.DataFrame({'RANGE_POS20': val.astype(np.float64)})
    out.to_hdf('result.h5', key='data', mode='w')
    print(out.info())


if __name__ == '__main__':
    calculate_RANGE_POS20()
