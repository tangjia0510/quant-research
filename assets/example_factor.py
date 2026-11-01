"""Synthetic example: five-session return divided by twenty-session volatility."""
import numpy as np
import pandas as pd


def compute(frame, params):
    short = int(params.get('return_window', 5))
    long = int(params.get('volatility_window', 20))
    if short < 1 or long < 2:
        raise ValueError('Windows must be positive; volatility needs at least two sessions.')
    groups = frame['close'].groupby(level='instrument', sort=False)
    returns = groups.pct_change(periods=short, fill_method=None)
    daily = groups.pct_change(fill_method=None)
    volatility = daily.groupby(level='instrument', sort=False).transform(
        lambda s: s.rolling(long, min_periods=long).std(ddof=0))
    values = returns / volatility.replace(0, np.nan)
    return pd.DataFrame({'risk_adjusted_momentum': values}, index=frame.index)
