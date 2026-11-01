"""Versioned fixed-formula factor. Observations include the current session."""
import numpy as np
import pandas as pd


def compute(frame, params):
    if params:
        raise ValueError('This fixed formula accepts no parameters; create a new version for changes')
    bars = frame.sort_index()
    group = bars.groupby(level='instrument', sort=False)
    volume = bars.volume.astype('float64')
    value = volume.groupby(level='instrument', sort=False).transform(lambda s: s / s.rolling(5, min_periods=5).mean()).astype('float64')
    return value.rename('VOL_DRYUP5').to_frame().reindex(frame.index)
