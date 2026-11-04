"""Small, explicit research statistics; all JSON output is finite or null."""
from __future__ import annotations

import numpy as np
import pandas as pd


def finite(value):
    return float(value) if value is not None and np.isfinite(value) else None


def signal_metrics(predictions: pd.DataFrame, *, frequency='unspecified',
                   label_horizon_sessions=None, label_entry_lag_sessions=None):
    """Equal-weighted cross-sectional correlations over dates, not pooled stock-days.

    ICIR and RankICIR are signed, non-annualized mean/sample-SD ratios.
    Metadata describes the caller's design; it does not infer independence.
    """
    if predictions.index.has_duplicates:
        raise ValueError('Signal rows must have a unique (datetime, instrument) index')
    clean = predictions[['prediction', 'label']].replace([np.inf, -np.inf], np.nan)
    rows = []
    input_dates = clean.index.get_level_values('datetime').nunique()
    for date, group in clean.dropna().groupby(level='datetime'):
        if len(group) < 3 or group.prediction.nunique() < 2 or group.label.nunique() < 2:
            continue
        rows.append({'date': str(date.date()), 'n': len(group),
                     'ic': finite(group.prediction.corr(group.label)),
                     'rank_ic': finite(group.prediction.corr(group.label, method='spearman'))})
    daily = pd.DataFrame(rows, columns=['date', 'n', 'ic', 'rank_ic'])
    metrics = {'ic_days': len(daily), 'ic_input_dates': int(input_dates),
               'ic_frequency': frequency, 'ic_std_ddof': 1, 'icir_annualized': False,
               'label_horizon_sessions': label_horizon_sessions,
               'label_entry_lag_sessions': label_entry_lag_sessions,
               'ic_min_cross_section': 3,
               'ic_missing_policy': 'pairwise finite observations; no imputation',
               'ic_inference': 'descriptive ratios, not significance tests; serial dependence and overlapping labels may apply'}
    for column, ratio in [('ic', 'icir'), ('rank_ic', 'rank_icir')]:
        series = pd.to_numeric(daily[column], errors='coerce').dropna()
        n = len(series)
        mean = finite(series.mean())
        std = finite(series.std(ddof=1)) if n >= 2 else None
        # Identical floating observations can have tiny numerical nonzero SD.
        if n >= 2 and series.nunique() == 1:
            std = 0.0
        reason = 'insufficient_dates' if n < 2 else ('zero_variance' if std == 0 else None)
        if n >= 2 and std is None:
            reason = 'nonfinite_dispersion'
        metrics.update({column: mean, column + '_std': std,
                        column + '_n': n, column + '_excluded_dates': int(input_dates - n),
                        ratio: finite(mean / std) if reason is None else None,
                        ratio + '_undefined_reason': reason})
    rank = pd.to_numeric(daily.rank_ic, errors='coerce').dropna()
    metrics['rank_ic_positive_fraction'] = finite((rank > 0).mean()) if len(rank) else None
    return metrics, daily


def factor_signal_metrics(features, predictions, **metadata):
    """Raw standalone feature diagnostics on the model's eligible evaluation rows.

    Reuse the model's purged raw labels, but never its imputed feature values.
    Each column is a separate estimand, not a combined model score.
    """
    summaries, series = {}, []
    for name in features.columns:
        frame = pd.DataFrame({'prediction': features[name].reindex(predictions.index),
                              'label': predictions['label']})
        summary, daily = signal_metrics(frame, **metadata)
        summaries[str(name)] = summary
        if not daily.empty:
            series.append(daily.assign(factor=str(name)))
    daily = pd.concat(series, ignore_index=True) if series else pd.DataFrame(
        columns=['date', 'n', 'ic', 'rank_ic', 'factor'])
    return summaries, daily


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
