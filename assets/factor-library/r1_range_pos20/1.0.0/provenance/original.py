import pandas as pd
import numpy as np


def calculate_range_pos20():
    """
    range_pos20: 20日高低价通道内相对位置因子
    formula: (close - 20日最低) / (20日最高 - 20日最低)
    与 z20 的均值偏离信息互补；使用滚动窗口,
    按instrument分组、按日期排序; 缺失价格保留为NaN; 结果中inf置为NaN.
    """
    # 读取数据: MultiIndex(datetime, instrument), 列含 $open/$high/$low/$close/$volume/$factor
    df = pd.read_hdf('daily_pv.h5', key='data')

    parts = []
    for inst, g in df.groupby(level='instrument'):
        # 取出该instrument的时序, 按日期排序
        s = g.droplevel('instrument').sort_index()

        high = s['$high'].astype('float64')
        low = s['$low'].astype('float64')
        close = s['$close'].astype('float64')

        # 20日高低通道, min_periods=窗口长度
        H20 = high.rolling(window=20, min_periods=20).max()
        L20 = low.rolling(window=20, min_periods=20).min()

        denom = H20 - L20
        # 通道内相对位置; denom<=0 或缺失时结果自然为NaN/inf
        f = (close - L20) / denom
        # 将 inf 置为 NaN, 保留缺失价格带来的NaN
        f = f.replace([np.inf, -np.inf], np.nan)

        f = f.to_frame('range_pos20')
        f['instrument'] = inst
        f = f.set_index('instrument', append=True)
        parts.append(f)

    result = pd.concat(parts)
    result = result.sort_index()

    # 写出结果: 单列, MultiIndex(datetime, instrument)
    result.to_hdf('result.h5', key='data', mode='w', complevel=0)

    print(result.info())
    print(result.head())
    print(result.tail())
    return result


if __name__ == '__main__':
    calculate_range_pos20()
