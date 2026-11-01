import pandas as pd
import numpy as np

def calculate_VOL_DRYUP5():
    df = pd.read_hdf('daily_pv.h5', key='data')
    df = df.sort_index()
    full_index = df.index
    vol = df['$volume'].astype('float64')

    ratio = vol.groupby(level='instrument').transform(
        lambda s: s / s.rolling(window=5, min_periods=5).mean()
    )

    out = pd.DataFrame({'VOL_DRYUP5': ratio})
    out = out.reindex(full_index)
    out['VOL_DRYUP5'] = out['VOL_DRYUP5'].astype('float64')
    out.to_hdf('result.h5', key='data', mode='w')
    return out

if __name__ == '__main__':
    res = calculate_VOL_DRYUP5()
    print(res.info())
