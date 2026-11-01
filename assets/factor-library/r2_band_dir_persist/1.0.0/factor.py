"""Versioned fixed-formula factor. Observations include the current session."""
import numpy as np
import pandas as pd


def compute(frame, params):
    if params:
        raise ValueError('This fixed formula accepts no parameters; create a new version for changes')
    bars = frame.sort_index()
    group = bars.groupby(level='instrument', sort=False)
    close = bars.close.astype('float64')
    mean = close.groupby(level='instrument', sort=False).transform(lambda s: s.rolling(20, min_periods=20).mean())
    signs = np.sign(close - mean)
    value = signs.groupby(level='instrument', sort=False).transform(lambda s: s.rolling(10, min_periods=10).mean())
    value = value.replace([np.inf, -np.inf], np.nan).astype('float64')
    return value.rename('band_dir_persist').to_frame().reindex(frame.index)
