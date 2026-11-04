"""Reproducible training and real Qlib daily simulation from a frozen protocol."""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import numpy as np
import pandas as pd

from . import data, factors, models, statistics
from .defaults import DEFAULT_INITIAL_CASH


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False, default=str))


def labels_for(bars, label):
    """Shift on the global calendar, never on a security's sparse observation rows."""
    calendar = pd.DatetimeIndex(bars.index.get_level_values('datetime').unique()).sort_values()
    price = label.get('price', 'open')
    lag, horizon = int(label.get('entry_lag', 1)), int(label.get('horizon', 5))
    if lag < 1 or horizon < 1 or price not in bars:
        raise ValueError('Label needs known price, entry_lag >= 1 and horizon >= 1')
    wide = bars[price].unstack('instrument').reindex(calendar)
    value = wide.shift(-(lag + horizon)) / wide.shift(-lag) - 1
    target = value.stack(future_stack=True).reindex(bars.index)
    end_dates = pd.Series(calendar, index=calendar).shift(-(lag + horizon))
    ends = pd.Series(bars.index.get_level_values('datetime').map(end_dates), index=bars.index, name='label_end')
    return target.rename('label'), ends, calendar


def _validation_boundary(splits):
    # A fixed split retains identical validation samples in discovery and final.
    # Explicit rolling folds can declare their own train/valid/evaluation dates.
    valid_end = pd.Timestamp(splits['valid'][1])
    return min(pd.Timestamp(splits[name][0]) for name in ('discovery', 'final')
               if name in splits and pd.Timestamp(splits[name][0]) > valid_end)


def split_masks(index, ends, splits, phase):
    dates = index.get_level_values('datetime')
    train, valid, test = [pd.to_datetime(splits[name]) for name in ['train', 'valid', phase]]
    if not (train[0] <= train[1] < valid[0] <= valid[1] < test[0] <= test[1]):
        raise ValueError('Train, validation and evaluation intervals must be ordered and disjoint')
    return {
        'train': (dates >= train[0]) & (dates <= train[1]) & (ends < valid[0]),
        'valid': (dates >= valid[0]) & (dates <= valid[1]) & (ends < _validation_boundary(splits)),
        'test': (dates >= test[0]) & (dates <= test[1]),
        'label_valid': ends <= test[1],
    }


def scale_train_only(features, mask, clip=10.):
    train = features.loc[mask]
    median = train.median()
    # Entirely missing training columns cannot be silently estimated from later data.
    if median.isna().any():
        raise ValueError('Some feature columns have no finite training observations: ' + ','.join(median.index[median.isna()]))
    spread = (train.quantile(.75) - train.quantile(.25)).replace(0, 1).fillna(1)
    if not np.isfinite(clip) or clip <= 0:
        raise ValueError('Preprocessing clip must be positive')
    scaled = ((features - median) / spread).clip(-clip, clip).fillna(0).astype(np.float32)
    return scaled, median, spread


def _fit_fold(workspace, config, candidate, bars, features, phase, splits, output):
    from qlib.data.dataset import DatasetH
    from qlib.data.dataset.handler import DataHandlerLP
    from qlib.data.dataset.loader import StaticDataLoader

    labels, ends, _ = labels_for(bars, config['label'])
    labels, ends = labels.reindex(features.index), ends.reindex(features.index)
    masks = split_masks(features.index, ends, splits, phase)
    eligibility_path = workspace / 'data/eligibility.parquet'
    eligible = pd.read_parquet(eligibility_path)['eligible'].reindex(features.index).fillna(False) if eligibility_path.exists() else pd.Series(True, index=features.index)
    train_mask = masks['train'] & eligible & labels.notna()
    valid_mask = masks['valid'] & eligible & labels.notna()
    test_mask = masks['test'] & eligible
    if min(int(train_mask.sum()), int(valid_mask.sum()), int(test_mask.sum())) < 3:
        raise ValueError('Insufficient train, validation or evaluation rows after boundary purging')
    preprocessing = config.get('preprocessing', {})
    scaled, median, spread = scale_train_only(features, train_mask, float(preprocessing.get('clip', 10.)))
    transform = preprocessing.get('label_transform', 'raw')
    if transform == 'raw':
        learning_labels = labels
    elif transform == 'cross_sectional_rank':
        # Qlib CSRankNorm semantics: percentile rank, centered then scaled by 3.46.
        learning_labels = (labels.where(eligible).groupby(level='datetime').rank(pct=True) - .5) * 3.46
    else:
        raise ValueError('label_transform must be raw or cross_sectional_rank')
    # Actual Qlib dataset contract, with fixed preprocessed features and label eligibility.
    frame = pd.concat({'feature': scaled, 'label': labels.to_frame()}, axis=1)
    handler = DataHandlerLP(data_loader=StaticDataLoader(frame))
    dataset = DatasetH(handler=handler, segments={'train': splits['train'], 'valid': splits['valid'], 'test': splits[phase]})
    checked = dataset.prepare('train', col_set='feature', data_key=DataHandlerLP.DK_I)
    if not set(scaled.columns) == set(checked.columns):
        raise ValueError('Qlib dataset changed feature columns')
    output.mkdir(parents=True, exist_ok=True)
    model_spec = candidate.get('model', config.get('model', {'kind': 'ridge', 'params': {'alpha': 1.0}}))
    models.check_model(model_spec, workspace, features.shape[1])
    prediction, model_check = models.fit_predict(
        scaled.loc[train_mask], learning_labels.loc[train_mask], scaled.loc[valid_mask], learning_labels.loc[valid_mask],
        scaled.loc[test_mask], model_spec, output, workspace)
    result = pd.DataFrame({'prediction': prediction, 'label': labels.loc[test_mask],
                           'label_end': ends.loc[test_mask]}, index=features.loc[test_mask].index)
    result.loc[~masks['label_valid'].loc[test_mask], 'label'] = np.nan
    pd.DataFrame({'median': median, 'iqr': spread}).to_csv(output / 'scaler.csv')
    result.to_parquet(output / 'predictions.parquet')
    details = {'splits': splits, 'rows': {'train': int(train_mask.sum()), 'valid': int(valid_mask.sum()),
                                       'evaluation': int(test_mask.sum())},
               'feature_names': list(features.columns), 'label_transform': transform, 'train_only_preprocessing': True,
               'validation_label_boundary': str(_validation_boundary(splits).date()),
               'label_boundaries_purged': True, 'model': model_check}
    write_json(output / 'checks.json', details)
    return result, details


def _backtest(workspace, config, predictions, calendar, output, cost_multiplier=1., delay=0, equal_weight=False):
    import qlib
    from qlib.backtest import backtest
    from qlib.backtest.decision import TradeDecisionWO
    from qlib.contrib.strategy.signal_strategy import WeightStrategyBase

    manifest = json.loads((workspace / 'data/manifest.json').read_text())
    qlib.init(provider_uri=str(workspace / 'data/provider'), region=config['data'].get('region', 'cn'),
              kernels=1, joblib_backend='threading', expression_cache=None, dataset_cache=None,
              logging_level=logging.ERROR)
    opts = config.get('portfolio', {})
    top_k, rebalance = int(opts.get('top_k', 3)), int(opts.get('rebalance', 5))
    lag = int(config['label'].get('entry_lag', 1))
    if top_k < 1 or rebalance < 1:
        raise ValueError('top_k and rebalance must be positive')
    # Qlib consumes previous session's signal; move whole snapshots for additional lag.
    shift = lag - 1 + int(delay)
    score = predictions.prediction.copy()
    position = calendar.get_indexer(score.index.get_level_values('datetime'))
    keep = (position >= 0) & (position + shift < len(calendar))
    score = score.loc[keep]
    score.index = pd.MultiIndex.from_arrays([calendar[position[keep] + shift], score.index.get_level_values('instrument')], names=['datetime', 'instrument'])
    first_signal = calendar.get_indexer([predictions.index.get_level_values('datetime').min()])[0]
    end = predictions.index.get_level_values('datetime').max()
    if first_signal + lag >= len(calendar) or calendar[first_signal + lag] > end:
        raise ValueError('Evaluation interval too short for the configured execution lag')
    start = calendar[first_signal + lag]

    class PeriodicWeights(WeightStrategyBase):
        def __init__(self, **kwargs):
            self.orders = []
            super().__init__(**kwargs)

        def generate_trade_decision(self, execute_result=None):
            if self.trade_calendar.get_trade_step() % rebalance:
                return TradeDecisionWO([], self)
            result = super().generate_trade_decision(execute_result)
            trade_date, _ = self.trade_calendar.get_step_time()
            snapshot_date, _ = self.trade_calendar.get_step_time(shift=1)
            origin_idx = calendar.get_indexer([snapshot_date.normalize()])[0] - shift
            original_date = calendar[origin_idx] if origin_idx >= 0 else pd.NaT
            for order in result.get_decision():
                if pd.isna(original_date) or original_date >= trade_date:
                    raise ValueError('Signal timing is not strictly earlier than execution')
                self.orders.append({'signal_date': str(original_date.date()), 'trade_date': str(trade_date.date()),
                                    'instrument': order.stock_id, 'direction': int(order.direction),
                                    'requested_amount': float(order.amount)})
            return result

        def generate_target_weight_position(self, score, current, trade_start_time, trade_end_time):
            if isinstance(score, pd.DataFrame):
                score = score.iloc[:, 0]
            available = score.dropna().sort_index().sort_values(ascending=False, kind='stable')
            selected = available if equal_weight else available.head(top_k)
            return {symbol: 1 / len(selected) for symbol in selected.index} if len(selected) else {}

    strategy = PeriodicWeights(signal=score, risk_degree=float(opts.get('position', .95)))
    codes = sorted(predictions.index.get_level_values('instrument').unique())
    # Qlib's OrderGenWOInteract sizes the first orders from the previous close.
    # Load that session into the exchange quote cache without adding a simulated
    # trading day. Otherwise step 0 has no sizing quote and misses a whole cycle.
    exchange = {'freq': 'day', 'codes': codes, 'start_time': calendar[first_signal + lag - 1],
                'deal_price': opts.get('deal_price', 'open'),
                'limit_threshold': opts.get('limit_threshold', .095),
                'open_cost': float(opts.get('buy_cost', .0005)) * cost_multiplier,
                'close_cost': float(opts.get('sell_cost', .0015)) * cost_multiplier,
                'min_cost': float(opts.get('min_cost', 0)) * cost_multiplier,
                'trade_unit': opts.get('trade_unit', 100)}
    portfolios, _ = backtest(start_time=start, end_time=end, strategy=strategy,
                             executor={'class': 'SimulatorExecutor', 'module_path': 'qlib.backtest.executor',
                                       'kwargs': {'time_per_step': 'day', 'generate_portfolio_metrics': True}},
                             benchmark=manifest.get('benchmark', 'QRBENCH'),
                             account=float(opts.get('initial_cash', DEFAULT_INITIAL_CASH)), exchange_kwargs=exchange)
    report, _ = portfolios['1day']
    if not np.isfinite(report[['return', 'cost', 'bench']].to_numpy()).all():
        raise ValueError('Qlib simulator returned non-finite results')
    report.to_csv(output)
    pd.DataFrame(strategy.orders, columns=['signal_date', 'trade_date', 'instrument', 'direction', 'requested_amount']).to_csv(output.with_name(output.stem + '-orders.csv'), index=False)
    return report


def folds_for(config, phase):
    """A fold may refine a phase interval, but cannot relabel another phase's data."""
    lower, upper = pd.to_datetime(config['splits'][phase])
    result = []
    for entry in config.get('folds') or [config['splits']]:
        fold = entry.get('splits', entry)
        if phase not in fold:
            continue
        start, end = pd.to_datetime(fold[phase])
        if not lower <= start <= end <= upper:
            raise ValueError('Fold evaluation interval must stay entirely inside the protocol phase interval')
        result.append(fold)
    if not result:
        raise ValueError('No folds configured for this phase')
    return result


def evaluate(workspace: Path, config: dict, candidate: dict, phase: str, output: Path):
    if phase not in {'discovery', 'final'}:
        raise ValueError('phase must be discovery or final')
    fold_specs = folds_for(config, phase)
    os.environ.setdefault('MLFLOW_DISABLE_AGENT_HINT', '1')
    workspace, output = Path(workspace).resolve(), Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    bars = data.load_bars(workspace)
    # No future prices are presented to candidate functions in discovery.
    ceiling = pd.Timestamp(config['splits'][phase][1])
    bars = bars.loc[bars.index.get_level_values('datetime') <= ceiling]
    features, factor_checks = factors.compute(workspace, candidate, bars, stage=phase)
    features = features.replace([np.inf, -np.inf], np.nan)
    _, _, calendar = labels_for(bars, config['label'])
    all_predictions, fold_checks = [], []
    for number, fold in enumerate(fold_specs):
        fold = fold.get('splits', fold)
        if phase not in fold:
            continue
        if pd.Timestamp(fold[phase][1]) > ceiling:
            raise ValueError('Fold evaluation extends past the protocol phase boundary')
        predicted, checked = _fit_fold(workspace, config, candidate, bars, features, phase, fold, output / f'fold-{number}')
        predicted['fold'] = number
        all_predictions.append(predicted)
        fold_checks.append(checked)
    if not all_predictions:
        raise ValueError('No folds configured for this phase')
    predictions = pd.concat(all_predictions).sort_index()
    if predictions.index.has_duplicates:
        raise ValueError('Evaluation folds overlap; predictions must be unique')
    observed_dates = pd.DatetimeIndex(predictions.index.get_level_values('datetime').unique()).sort_values()
    expected_dates = calendar[(calendar >= observed_dates.min()) & (calendar <= observed_dates.max())]
    if not observed_dates.equals(expected_dates):
        raise ValueError('Evaluation folds must cover a continuous calendar interval; missing whole-day signals cannot be silently carried')
    predictions.to_parquet(output / 'predictions.parquet')
    signal_metadata = {'frequency': 'daily',
                       'label_horizon_sessions': int(config['label'].get('horizon', 5)),
                       'label_entry_lag_sessions': int(config['label'].get('entry_lag', 1))}
    signal, daily = statistics.signal_metrics(predictions, **signal_metadata)
    factor_signal, factor_daily = statistics.factor_signal_metrics(features, predictions, **signal_metadata)
    factor_daily.to_csv(output / 'factor-daily-ic.csv', index=False)
    daily.to_csv(output / 'daily-ic.csv', index=False)
    base = _backtest(workspace, config, predictions, calendar, output / 'portfolio.csv')
    control = _backtest(workspace, config, predictions, calendar, output / 'equal-weight.csv', equal_weight=True)
    net = base['return'] - base.cost
    control_net = control['return'] - control.cost
    metrics = {'phase': phase, 'candidate_id': candidate.get('id'), 'signal': signal,
               'factor_signal': factor_signal,
               'portfolio': statistics.portfolio_metrics(base),
               'equal_weight': statistics.portfolio_metrics(control),
               'equal_weight_excess_annualized': statistics.finite((net - control_net).mean() * 252),
               'folds': fold_checks, 'factor_checks': factor_checks,
               'prediction_rows': len(predictions), 'simulator': 'qlib.SimulatorExecutor',
               'benchmark': 'synthetic equal-weight close index; not an official market index',
               'interpretation': 'historical research; implementation checks are not investment validation'}
    robustness = config.get('robustness', {})
    if robustness.get('enabled', True):
        metrics['robustness'] = {}
        for name, multiplier, delay in [('double_cost', 2., 0), ('delayed_signal', 1., 1)]:
            result = _backtest(workspace, config, predictions, calendar, output / f'{name}.csv', cost_multiplier=multiplier, delay=delay)
            metrics['robustness'][name] = statistics.portfolio_metrics(result)
    # Compare on identical evaluation dates against an explicit fixed baseline.
    baseline_candidate = dict(candidate)
    baseline_candidate['id'] = 'fixed-baseline'
    kind = candidate.get('kind', 'factor')
    if kind != 'model':
        baseline_candidate.pop('factor_file', None)
        baseline_candidate.pop('factor_params', None)
        baseline_candidate.pop('factor_refs', None)
        baseline_candidate.pop('registered_factors', None)
        if not baseline_candidate.get('features', ['return_5', 'volatility_20']):
            baseline_candidate['features'] = config.get('baseline_features', ['return_5', 'volatility_20'])
    if kind in {'model', 'joint'}:
        baseline_candidate['model'] = config.get('model', {'kind': 'ridge', 'params': {'alpha': 1.0}})
    if kind == 'joint':
        baseline_candidate['features'] = config.get('baseline_features', ['return_5', 'volatility_20'])
    baseline_features, _ = factors.compute(workspace, baseline_candidate, bars, stage=phase)
    baseline_features = baseline_features.replace([np.inf, -np.inf], np.nan)
    baseline_parts = []
    for number, fold in enumerate(fold_specs):
        fold = fold.get('splits', fold)
        if phase in fold:
            part, _ = _fit_fold(workspace, config, baseline_candidate, bars, baseline_features,
                                phase, fold, output / 'baseline' / f'fold-{number}')
            baseline_parts.append(part)
    baseline_predictions = pd.concat(baseline_parts).sort_index()
    if not baseline_predictions.index.equals(predictions.index):
        raise ValueError('Candidate and baseline evaluation samples must match')
    baseline_predictions.to_parquet(output / 'baseline/predictions.parquet')
    baseline_signal, baseline_daily = statistics.signal_metrics(baseline_predictions, **signal_metadata)
    baseline_daily.to_csv(output / 'baseline/daily-ic.csv', index=False)
    baseline_report = _backtest(workspace, config, baseline_predictions, calendar, output / 'baseline/portfolio.csv')
    metrics['baseline'] = {'model': baseline_candidate.get('model', config.get('model', {'kind': 'ridge'})),
                           'features': list(baseline_features.columns), 'signal': baseline_signal,
                           'portfolio': statistics.portfolio_metrics(baseline_report)}
    metrics['increment'] = statistics.paired_increment(daily, baseline_daily, lag=max(1, int(config['label']['horizon'])))
    metrics['increment']['annualized_net_return_difference'] = statistics.finite(
        ((base['return'] - base.cost) - (baseline_report['return'] - baseline_report.cost)).mean() * 252)
    write_json(output / 'metrics.json', metrics)
    return metrics
