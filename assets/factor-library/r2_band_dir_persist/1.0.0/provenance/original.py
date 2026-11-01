import pandas as pd
import numpy as np

def calculate_band_dir_persist():
    df = pd.read_hdf('daily_pv.h5', key='data')
    full_index = df.index
    df = df.reset_index()
    df = df.sort_values(['instrument', 'datetime'])

    out = []
    for inst, g in df.groupby('instrument', sort=False):
        close = g['$close'].astype(float)
        sma20 = close.rolling(20, min_periods=20).mean()
        sign = np.sign(close - sma20)
        val = sign.rolling(10, min_periods=10).mean()
        s = pd.Series(val.values,
                      index=pd.MultiIndex.from_arrays([g['datetime'].values,
                                                       [inst] * len(g)],
                                                      names=['datetime', 'instrument']))
        out.append(s)

    res = pd.concat(out).sort_index()
    res = res.replace([np.inf, -np.inf], np.nan).astype(float)
    res = res.reindex(full_index)
    res = res.to_frame('band_dir_persist')
    res.to_hdf('result.h5', key='data', mode='w')

if __name__ == '__main__':
    calculate_band_dir_persist()
