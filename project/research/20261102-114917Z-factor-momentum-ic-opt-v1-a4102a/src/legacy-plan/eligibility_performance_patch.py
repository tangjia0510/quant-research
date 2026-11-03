"""Equivalent membership interval assignment; performance-only proposed repair."""
import numpy as np
import pandas as pd

def eligibility_grouped(frame, path):
    result = pd.DataFrame({'eligible': True}, index=frame.index)
    if path is None:
        return result
    intervals = path.copy() if isinstance(path, pd.DataFrame) else pd.read_csv(path, dtype={'instrument': str})
    if not {'instrument', 'start', 'end'}.issubset(intervals):
        raise ValueError('Universe needs instrument,start,end columns')
    intervals['start'] = pd.to_datetime(intervals.start)
    intervals['end'] = pd.to_datetime(intervals.end)
    if intervals[['start', 'end']].isna().any().any() or (intervals.start > intervals.end).any():
        raise ValueError('Invalid membership interval')
    selected = np.zeros(len(frame), dtype=bool)
    dates = frame.index.get_level_values('datetime')
    # One instrument grouping instead of an all-market string scan per interval.
    groups = frame.groupby(level='instrument', sort=False).indices
    for row in intervals.itertuples():
        positions = groups.get(row.instrument)
        if positions is None:
            continue
        subset_dates = dates.take(positions)
        selected[positions[(subset_dates >= row.start) & (subset_dates <= row.end)]] = True
    result['eligible'] = selected
    if not result.eligible.any():
        raise ValueError('No observations overlap the declared universe')
    return result
