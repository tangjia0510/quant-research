"""Small, explicit research statistics; all JSON output is finite or null."""
from __future__ import annotations

import numpy as np
import pandas as pd


def finite(value):
    return float(value) if value is not None and np.isfinite(value) else None


def signal_metrics(predictions: pd.DataFrame):
    rows = []
    for date, group in predictions.dropna(subset=['prediction', 'label']).groupby(level='datetime'):
        if len(group) < 3 or group.prediction.nunique() < 2 or group.label.nunique() < 2:
            continue
        rows.append({'date': str(date.date()), 'n': len(group),
                     'ic': finite(group.prediction.corr(group.label)),
                     'rank_ic': finite(group.prediction.corr(group.label, method='spearman'))})
    daily = pd.DataFrame(rows, columns=['date', 'n', 'ic', 'rank_ic'])
    return {'ic': finite(daily.ic.mean()), 'rank_ic': finite(daily.rank_ic.mean()),
            'ic_days': len(daily), 'rank_ic_positive_fraction': finite((daily.rank_ic > 0).mean())}, daily


def portfolio_metrics(report: pd.DataFrame):
    net = report['return'] - report['cost']
    wealth = (1 + net).cumprod()
    if len(wealth) == 0:
        raise ValueError('Backtest produced no observations')
    # Include initial capital as a peak so an immediate loss counts as drawdown.
    peaks = np.maximum.accumulate(np.r_[1., wealth.to_numpy()])[1:]
    excess = net - report['bench']
    std = excess.std(ddof=1)
    return {'days': len(report), 'total_net_return': finite(wealth.iloc[-1] - 1),
            'net_cagr': finite(wealth.iloc[-1] ** (252 / len(report)) - 1) if wealth.iloc[-1] > 0 else None,
            'max_drawdown': finite((wealth.to_numpy() / peaks - 1).min()),
            'annualized_arithmetic_excess': finite(excess.mean() * 252),
            'information_ratio': finite(excess.mean() / std * np.sqrt(252)) if std > 0 else None,
            'mean_daily_cost': finite(report['cost'].mean()),
            'mean_daily_turnover': finite(report['turnover'].mean()) if 'turnover' in report else None}


def paired_increment(candidate_daily, baseline_daily, lag=5):
    """Same-day RankIC difference with a small Newey-West mean uncertainty estimate."""
    pair = candidate_daily.set_index('date')[['rank_ic']].join(
        baseline_daily.set_index('date')[['rank_ic']], lsuffix='_candidate', rsuffix='_baseline', how='inner').dropna()
    values = (pair.rank_ic_candidate - pair.rank_ic_baseline).to_numpy()
    n = len(values)
    if n < 2:
        return {'days': n, 'mean_rank_ic_increment': None, 'hac_ci95': None, 'interpretation': 'insufficient paired dates'}
    mean = values.mean()
    residual = values - mean
    lag = min(int(lag), n - 1)
    long_variance = np.dot(residual, residual) / n
    for shift in range(1, lag + 1):
        long_variance += 2 * (1 - shift / (lag + 1)) * np.dot(residual[shift:], residual[:-shift]) / n
    se = np.sqrt(max(0., long_variance) / n)
    return {'days': n, 'mean_rank_ic_increment': finite(mean), 'hac_lag': lag,
            'hac_ci95': [finite(mean - 1.96 * se), finite(mean + 1.96 * se)],
            'interpretation': 'exploratory paired estimate; not corrected for adaptive search or multiple trials'}
