import pandas as pd
import numpy as np


def calculate_squeeze20_40():
    df = pd.read_hdf('daily_pv.h5', key='data')
    df = df.sort_index()

    close = df['$close']

    def per_inst(g):
        c = g['$close']
        sma20 = c.rolling(20, min_periods=20).mean()
        sigma20 = c.rolling(20, min_periods=20).std(ddof=0)
        sigma_bar = sigma20.rolling(40, min_periods=40).mean()
        return sigma20 / sigma_bar

    result = df.groupby(level='instrument', group_keys=False).apply(per_inst)
    result = result.rename('squeeze20_40')
    result = result.replace([np.inf, -np.inf], np.nan)
    out = result.to_frame()
    out.to_hdf('result.h5', key='data', mode='w')
    print(out.info())


if __name__ == '__main__':
    calculate_squeeze20_40()
