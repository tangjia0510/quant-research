"""Versioned fixed-formula factor. Observations include the current session."""
import numpy as np
import pandas as pd


def compute(frame, params):
    if params:
        raise ValueError('This fixed formula accepts no parameters; create a new version for changes')
    bars = frame.sort_index()
    group = bars.groupby(level='instrument', sort=False)
    value = group.close.transform(lambda s: s.pct_change(5, fill_method=None))
    return value.rename('return_5').to_frame().reindex(frame.index)
