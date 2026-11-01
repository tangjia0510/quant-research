"""Versioned fixed-formula factor. Observations include the current session."""
import numpy as np
import pandas as pd


def compute(frame, params):
    if params:
        raise ValueError('This fixed formula accepts no parameters; create a new version for changes')
    bars = frame.sort_index()
    group = bars.groupby(level='instrument', sort=False)
    lo = bars.low.astype('float64').groupby(level='instrument', sort=False).transform(lambda s: s.rolling(20, min_periods=20).min())
    hi = bars.high.astype('float64').groupby(level='instrument', sort=False).transform(lambda s: s.rolling(20, min_periods=20).max())
    value = ((bars.close.astype('float64') - lo) / (hi - lo)).replace([np.inf, -np.inf], np.nan)
    return value.rename('range_pos20').to_frame().reindex(frame.index)
