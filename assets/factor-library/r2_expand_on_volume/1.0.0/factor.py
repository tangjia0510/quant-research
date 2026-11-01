"""Versioned fixed-formula factor. Observations include the current session."""
import numpy as np
import pandas as pd


def compute(frame, params):
    if params:
        raise ValueError('This fixed formula accepts no parameters; create a new version for changes')
    bars = frame.sort_index()
    group = bars.groupby(level='instrument', sort=False)
    std = group.close.transform(lambda s: s.rolling(20, min_periods=20).std(ddof=0))
    width = 4.0 * std
    width_change = width - width.groupby(level='instrument', sort=False).shift(5)
    mean_volume = group.volume.transform(lambda s: s.rolling(20, min_periods=20).mean())
    ratio = bars.volume / mean_volume
    smooth_ratio = ratio.groupby(level='instrument', sort=False).transform(lambda s: s.rolling(5, min_periods=5).mean())
    value = (width_change * smooth_ratio).replace([np.inf, -np.inf], np.nan).astype('float64')
    return value.rename('expand_on_volume').to_frame().reindex(frame.index)
