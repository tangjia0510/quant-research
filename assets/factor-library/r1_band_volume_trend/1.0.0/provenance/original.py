import pandas as pd
import numpy as np

def calculate_band_volume_trend():
    # 读取数据
    df = pd.read_hdf('daily_pv.h5', key='data')

    # 按instrument分组、按datetime排序计算
    def _calc(g):
        g = g.sort_index(level='datetime')
        close = g['$close'].astype('float64')
        volume = g['$volume'].astype('float64')

        # 20日布林带：SMA20 与总体标准差 pop std(ddof=0)
        sma20 = close.rolling(20, min_periods=20).mean()
        std20 = close.rolling(20, min_periods=20).std(ddof=0)

        # z20: 带内标准化位置 (close - SMA20) / (2*std20)
        z20 = (close - sma20) / (2.0 * std20)

        # 20日均量比 V_t / mean(V_{t-19..t})，min_periods=20
        vma20 = volume.rolling(20, min_periods=20).mean()
        vol_ratio = volume / vma20

        # 交互因子：z20 * 量比
        factor = z20 * vol_ratio

        # inf 视为 NaN，保留缺失价格
        factor = factor.replace([np.inf, -np.inf], np.nan)
        return factor

    result = df.groupby(level='instrument', group_keys=False).apply(_calc)
    out = result.to_frame('band_volume_trend')
    out = out.sort_index()

    # 不做任何日期过滤，完整保留输入 MultiIndex（含 warmup NaN）

    # 写出结果
    out.to_hdf('result.h5', key='data', mode='w')
    print(out.info())
    return out

if __name__ == '__main__':
    calculate_band_volume_trend()
