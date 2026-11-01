"""Versioned fixed-formula factor. Observations include the current session."""
import numpy as np
import pandas as pd


def compute(frame, params):
    if params:
        raise ValueError('This fixed formula accepts no parameters; create a new version for changes')
    bars = frame.sort_index()
    group = bars.groupby(level='instrument', sort=False)
    close = bars.close.astype('float64')
    volume = bars.volume.astype('float64')
    prices = close.groupby(level='instrument', sort=False)
    mean = prices.transform(lambda s: s.rolling(20, min_periods=20).mean())
    std = prices.transform(lambda s: s.rolling(20, min_periods=20).std(ddof=0))
    mean_volume = volume.groupby(level='instrument', sort=False).transform(lambda s: s.rolling(20, min_periods=20).mean())
    value = (((close - mean) / (2.0 * std)) * (volume / mean_volume)).replace([np.inf, -np.inf], np.nan)
    return value.rename('band_volume_trend').to_frame().reindex(frame.index)
