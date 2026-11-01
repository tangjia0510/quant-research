import pandas as pd
import numpy as np

def calculate_expand_on_volume():
    input_df = pd.read_hdf('daily_pv.h5', key='data')
    df = input_df.sort_index()
    assert len(df) == len(input_df)
    input_index = df.index

    # width20 = 4*std20(ddof=0)
    g_close = df.groupby(level='instrument')['$close']
    sma20 = g_close.transform(lambda s: s.rolling(20, min_periods=20).mean())
    std20 = g_close.transform(lambda s: s.rolling(20, min_periods=20).std(ddof=0))
    width20 = 4.0 * std20

    # 带宽5日变化：width20 - width20.shift(5)
    width_shift = width20.groupby(level='instrument').shift(5)
    dwidth = width20 - width_shift

    # 20日均量比
    g_vol = df.groupby(level='instrument')['$volume']
    vol_mean20 = g_vol.transform(lambda s: s.rolling(20, min_periods=20).mean())
    vol_ratio20 = df['$volume'] / vol_mean20

    # 5日平滑量比
    vr5 = vol_ratio20.groupby(level='instrument').transform(
        lambda s: s.rolling(5, min_periods=5).mean())

    factor = dwidth * vr5
    factor = factor.replace([np.inf, -np.inf], np.nan)

    out = pd.DataFrame({'expand_on_volume': factor.astype('float64')})
    # 保证与输入 MultiIndex 完全一致，包括 warmup NaN 行
    out = out.reindex(input_index)

    print('input rows:', len(input_df), 'output rows:', len(out))
    assert len(out) == len(input_df)
    print(out.head())
    print(out.info())

    out.to_hdf('result.h5', key='data', mode='w', complevel=4)

if __name__ == '__main__':
    calculate_expand_on_volume()
