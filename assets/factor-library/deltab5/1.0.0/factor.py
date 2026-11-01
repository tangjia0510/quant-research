"""Versioned fixed-formula factor. Observations include the current session."""
import numpy as np
import pandas as pd


def compute(frame, params):
    if params:
        raise ValueError('This fixed formula accepts no parameters; create a new version for changes')
    bars = frame.sort_index()
    group = bars.groupby(level='instrument', sort=False)
    mean = group.close.transform(lambda s: s.rolling(20, min_periods=20).mean())
    std = group.close.transform(lambda s: s.rolling(20, min_periods=20).std(ddof=0))
    pct_b = ((bars.close - mean) / std) / 4.0 + 0.5
    value = pct_b - pct_b.groupby(level='instrument', sort=False).shift(5)
    return value.rename('deltaB5').to_frame().reindex(frame.index)
