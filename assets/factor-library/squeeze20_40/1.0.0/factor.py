"""Versioned fixed-formula factor. Observations include the current session."""
import numpy as np
import pandas as pd


def compute(frame, params):
    if params:
        raise ValueError('This fixed formula accepts no parameters; create a new version for changes')
    bars = frame.sort_index()
    group = bars.groupby(level='instrument', sort=False)
    std = group.close.transform(lambda s: s.rolling(20, min_periods=20).std(ddof=0))
    mean_std = std.groupby(level='instrument', sort=False).transform(lambda s: s.rolling(40, min_periods=40).mean())
    value = (std / mean_std).replace([np.inf, -np.inf], np.nan)
    return value.rename('squeeze20_40').to_frame().reindex(frame.index)
