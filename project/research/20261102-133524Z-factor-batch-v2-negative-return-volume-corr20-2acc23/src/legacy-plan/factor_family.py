import numpy as np
import pandas as pd


def compute(frame, params):
    name = params['candidate_id']
    group = frame.groupby(level='instrument', sort=False)
    close = frame['close']
    volume = frame['volume'].where(frame['volume'] > 0)
    previous_close = group['close'].shift(1)
    returns = close / previous_close - 1
    if name == 'low-downside-risk20':
        squared = returns.clip(upper=0).pow(2)
        value = -np.sqrt(squared.groupby(level='instrument', sort=False).transform(
            lambda s: s.rolling(20, min_periods=20).mean()))
    elif name == 'negative-return-volume-corr20':
        log_change = np.log(volume).groupby(level='instrument', sort=False).diff()
        pairs = pd.DataFrame({'r': returns, 'v': log_change}, index=frame.index)
        def correlation(g):
            r = g['r'].rolling(20, min_periods=20)
            v = g['v'].rolling(20, min_periods=20)
            result = -r.corr(g['v'])
            return result.where((r.std(ddof=0) > 0) & (v.std(ddof=0) > 0))
        value = pd.concat([correlation(g) for _, g in pairs.groupby(level='instrument', sort=False)]).reindex(frame.index)
        value = value.replace([np.inf, -np.inf], np.nan)
    elif name == 'volume-weighted-close-location20':
        span = (frame['high'] - frame['low']).where(frame['high'] > frame['low'])
        location = (2 * close - frame['high'] - frame['low']) / span
        weighted = location * volume
        numerator = weighted.groupby(level='instrument', sort=False).transform(
            lambda s: s.rolling(20, min_periods=20).sum())
        denominator = volume.groupby(level='instrument', sort=False).transform(
            lambda s: s.rolling(20, min_periods=20).sum())
        value = numerator / denominator.where(denominator > 0)
    else:
        raise ValueError('Unknown frozen candidate')
    return value.rename('x_' + name.replace('-', '_')).to_frame()
