"""Versioned fixed-formula factor. Observations include the current session."""
import numpy as np
import pandas as pd


def compute(frame, params):
    if params:
        raise ValueError('This fixed formula accepts no parameters; create a new version for changes')
    bars = frame.sort_index()
    group = bars.groupby(level='instrument', sort=False)
    lo = group.low.transform(lambda s: s.rolling(20, min_periods=20).min())
    hi = group.high.transform(lambda s: s.rolling(20, min_periods=20).max())
    value = ((bars.close - lo) / (hi - lo).replace(0., np.nan)).astype('float64')
    return value.rename('RANGE_POS20').to_frame().reindex(frame.index)
