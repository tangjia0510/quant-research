"""Versioned fixed-formula factor. Observations include the current session."""
import numpy as np
import pandas as pd


def compute(frame, params):
    if params:
        raise ValueError('This fixed formula accepts no parameters; create a new version for changes')
    bars = frame.sort_index()
    group = bars.groupby(level='instrument', sort=False)
    value = bars.volume / group.volume.transform(lambda s: s.rolling(5, min_periods=5).mean()).replace(0., np.nan)
    return value.rename('volume_ratio_5').to_frame().reindex(frame.index)
