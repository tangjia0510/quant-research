"""Deterministic factor calculations and observable causality checks."""
from __future__ import annotations

import ast
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

BUILTINS = ('return_5', 'volatility_20', 'momentum_20', 'range_position_20', 'volume_ratio_5')


def builtin_features(bars, names):
    output = pd.DataFrame(index=bars.index)
    group = bars.groupby(level='instrument', sort=False)
    for name in names:
        if name == 'return_5':
            value = group.close.transform(lambda s: s.pct_change(5, fill_method=None))
        elif name == 'momentum_20':
            value = group.close.transform(lambda s: s.pct_change(20, fill_method=None))
        elif name == 'volatility_20':
            value = group.close.transform(lambda s: s.pct_change(fill_method=None).rolling(20, min_periods=20).std(ddof=0))
        elif name == 'range_position_20':
            lo = group.low.transform(lambda s: s.rolling(20, min_periods=20).min())
            hi = group.high.transform(lambda s: s.rolling(20, min_periods=20).max())
            value = (bars.close - lo) / (hi - lo).replace(0., np.nan)
        elif name == 'volume_ratio_5':
            value = bars.volume / group.volume.transform(lambda s: s.rolling(5, min_periods=5).mean()).replace(0., np.nan)
        else:
            raise ValueError(f'Unknown builtin feature {name}; available: {BUILTINS}')
        output[name] = value
    return output


def audit_code(code):
    """Catch common mistakes. AST restrictions do not constitute a sandbox."""
    tree = ast.parse(code)
    banned = {'open', 'eval', 'exec', 'compile', '__import__', 'getattr', 'setattr',
              'globals', 'locals', 'input', 'breakpoint', 'read_csv', 'read_parquet',
              'read_pickle', 'read_hdf', 'read_sql', 'read_excel', 'load', 'save',
              'to_pickle', 'to_csv', 'to_parquet', 'to_hdf', 'to_sql', 'loadtxt',
              'savetxt', 'fromfile', 'tofile', 'system', 'popen', 'bfill'}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            modules = [x.name.split('.')[0] for x in node.names] if isinstance(node, ast.Import) else [(node.module or '').split('.')[0]]
            if not set(modules).issubset({'numpy', 'pandas'}):
                raise ValueError('Factor imports are limited to numpy and pandas')
        if isinstance(node, ast.Attribute) and node.attr.startswith('__'):
            raise ValueError('Dunder access is not part of the factor contract')
        if isinstance(node, ast.Call):
            name = node.func.id if isinstance(node.func, ast.Name) else node.func.attr if isinstance(node.func, ast.Attribute) else ''
            if name in banned:
                raise ValueError(f'Forbidden factor operation: {name}')
            for keyword in node.keywords:
                if keyword.arg == 'center' and (not isinstance(keyword.value, ast.Constant) or keyword.value.value):
                    raise ValueError('Centered windows use future observations')
    if not any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == 'compute' for n in tree.body):
        raise ValueError('Factor must define compute(frame, params)')


def _output(result, expected):
    if not isinstance(result.index, pd.MultiIndex) or list(result.index.names) != ['datetime', 'instrument']:
        raise ValueError('Factor output index must be datetime,instrument')
    if not result.index.is_unique or not result.index.equals(expected):
        raise ValueError('Factor output must preserve every input row in the same order')
    if result.shape[1] == 0 or result.shape[1] > 32 or not result.columns.is_unique:
        raise ValueError('Factor output needs 1 to 32 uniquely named columns')
    if not all(isinstance(c, str) and c and not c.startswith('__') for c in result):
        raise ValueError('Factor column names must be nonempty strings')
    if not all(pd.api.types.is_numeric_dtype(t) for t in result.dtypes):
        raise ValueError('Factor values must be numeric')
    result = result.astype('float64')
    if np.isinf(result.to_numpy()).any():
        raise ValueError('Factor produced infinity')
    if result.notna().sum().eq(0).any():
        raise ValueError('Factor produced an entirely missing column')
    return result


def _run(code_path, bars, params, timeout, scratch):
    scratch.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='factor-', dir=scratch) as directory:
        directory = Path(directory)
        bars.to_parquet(directory / 'input.parquet')
        (directory / 'params.json').write_text(json.dumps(params, allow_nan=False))
        env = {'PATH': str(Path(sys.executable).parent), 'HOME': str(directory),
               'PYTHONNOUSERSITE': '1', 'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1',
               'MKL_NUM_THREADS': '1', 'PYTHONHASHSEED': '0', 'LANG': 'C.UTF-8'}
        command = [sys.executable, '-I', '-B', str(Path(__file__).with_name('factor_worker.py')),
                   str(code_path), str(directory / 'input.parquet'), str(directory / 'output.parquet'),
                   str(directory / 'params.json')]
        try:
            result = subprocess.run(command, cwd=directory, env=env, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            raise ValueError(f'Factor exceeded timeout ({timeout}s)') from exc
        if result.returncode:
            raise ValueError('Factor execution failed: ' + result.stderr[-2000:])
        if not (directory / 'output.parquet').exists():
            raise ValueError('Factor did not produce output')
        return _output(pd.read_parquet(directory / 'output.parquet'), bars.index)


def _compare(left, right, reason):
    if list(left.columns) != list(right.columns):
        raise ValueError(f'{reason}: columns changed')
    try:
        np.testing.assert_allclose(left.to_numpy(), right.to_numpy(), rtol=1e-7, atol=1e-10, equal_nan=True)
    except AssertionError as exc:
        raise ValueError(reason) from exc


def compute(workspace, candidate, bars, stage='discovery'):
    workspace = Path(workspace).resolve()
    config_path = workspace / 'protocol.json'
    if config_path.exists():
        config = json.loads(config_path.read_text())
        split = config['splits'].get('discovery' if stage == 'discovery' else 'final')
        if split:
            bars = bars.loc[bars.index.get_level_values('datetime') <= pd.Timestamp(split[1])].copy()
    bars = bars.sort_index()
    if not len(bars):
        raise ValueError('No factor input observations')
    if not bars.index.is_unique or list(bars.index.names) != ['datetime', 'instrument']:
        raise ValueError('Factor input requires unique datetime,instrument index')
    # Pass only market observables, even if a caller accidentally includes labels.
    bars = bars[[c for c in ('open', 'high', 'low', 'close', 'volume', 'factor') if c in bars]]
    names = candidate.get('features', ['return_5', 'volatility_20'])
    features = builtin_features(bars, names)
    checks = {'stage': stage, 'rows': len(bars), 'builtin_features': names,
              'input_end': str(bars.index.get_level_values('datetime').max().date()),
              'generated_factor': False, 'execution_is_security_sandbox': False}
    if candidate.get('factor_file'):
        relative = Path(candidate['factor_file'])
        if relative.is_absolute():
            raise ValueError('factor_file must be workspace-relative')
        code_path = (workspace / relative).resolve()
        if not code_path.is_relative_to(workspace):
            raise ValueError('factor_file escapes the study workspace')
        code = code_path.read_text()
        audit_code(code)
        params = candidate.get('factor_params', {})
        timeout = float(candidate.get('factor_timeout', 120))
        if not 0 < timeout <= 3600:
            raise ValueError('factor_timeout must be positive and <= 3600 seconds')
        lookback = candidate.get('max_lookback')
        if not isinstance(lookback, int) or not 1 <= lookback <= 10000:
            raise ValueError('Generated factor requires max_lookback (positive observation count)')
        scratch = workspace / '.factor-work'
        generated = _run(code_path, bars, params, timeout, scratch)
        duplicates = set(features) & set(generated)
        if duplicates:
            raise ValueError(f'Generated feature names overlap baseline: {sorted(duplicates)}')
        # Causality checks operate on real data and preserve complete cross sections.
        calendar = pd.DatetimeIndex(bars.index.get_level_values('datetime').unique()).sort_values()
        if len(calendar) < lookback + 3:
            raise ValueError('Insufficient history to independently check declared factor lookback')
        sample_dates = calendar[:min(len(calendar), max(80, lookback * 3 + 3))]
        sample = bars.loc[bars.index.get_level_values('datetime').isin(sample_dates)]
        original = _run(code_path, sample, params, timeout, scratch)
        cutoff = sample_dates[max(lookback, len(sample_dates) * 2 // 3) - 1]
        future = sample.copy()
        mask = future.index.get_level_values('datetime') > cutoff
        for i, column in enumerate(future):
            future.loc[mask, column] *= 1.3 + .17 * i
        altered = _run(code_path, future, params, timeout, scratch)
        before = original.loc[original.index.get_level_values('datetime') <= cutoff]
        _compare(before, altered.reindex(before.index), 'Future perturbation changed historical factor values')
        prefix = sample.loc[sample.index.get_level_values('datetime') <= cutoff]
        prefix_output = _run(code_path, prefix, params, timeout, scratch)
        _compare(before, prefix_output, 'Factor depends on data beyond the observation date')
        # Keep complete cross sections in the last lookback calendar sessions.
        # Comparing each security's own last row would distort rank factors when
        # securities enter or leave the universe at different times.
        window = sample.loc[sample.index.get_level_values('datetime') >= sample_dates[-lookback]]
        window_output = _run(code_path, window, params, timeout, scratch)
        last = window.loc[window.index.get_level_values('datetime') == sample_dates[-1]].index
        _compare(original.reindex(last), window_output.reindex(last), 'Declared max_lookback is insufficient')
        if candidate.get('scale_invariant', False):
            scaled = sample.copy()
            ids = sorted(sample.index.get_level_values('instrument').unique())
            scales = pd.Series(np.geomspace(.3, 3., len(ids)), index=ids)
            scale = sample.index.get_level_values('instrument').map(scales).to_numpy()
            for column in ('open', 'high', 'low', 'close'):
                scaled[column] *= scale
            scaled['volume'] /= scale
            scaled_output = _run(code_path, scaled, params, timeout, scratch)
            _compare(original, scaled_output, 'Declared scale invariance does not hold')
        features = features.join(generated)
        checks.update({'generated_factor': True, 'factor_sha256': hashlib.sha256(code.encode()).hexdigest(),
                       'future_perturbation': True, 'prefix_invariance': True,
                       'declared_lookback_verified': lookback,
                       'scale_invariance_checked': bool(candidate.get('scale_invariant', False))})
    registered = candidate.get('registered_factors', [])
    if candidate.get('factor_refs') and not registered:
        raise ValueError('Resolve factor_refs through candidate registration before computing')
    registered_checks = []
    for snapshot in registered:
        registered_candidate = {'features': [], 'factor_file': snapshot['factor_file'],
                                'factor_params': snapshot['params'],
                                'factor_timeout': candidate.get('factor_timeout', 120),
                                'max_lookback': snapshot['max_lookback'],
                                'scale_invariant': snapshot['scale_invariant']}
        output, result = compute(workspace, registered_candidate, bars, stage)
        if list(output.columns) != snapshot['output_columns']:
            raise ValueError('Registered factor output differs from versioned output_columns')
        duplicates = set(features) & set(output)
        if duplicates:
            raise ValueError(f'Registered factor columns overlap other features: {sorted(duplicates)}')
        features = features.join(output)
        registered_checks.append({'id': snapshot['id'], 'version': snapshot['version'],
                                  'manifest_hash': snapshot['manifest_hash'],
                                  'limitations': snapshot['limitations'], 'checks': result,
                                  'library_validation': snapshot['library_validation']})
    if registered_checks:
        checks.update(generated_factor=True, registered_factors=registered_checks)
    if features.empty or not len(features.columns):
        raise ValueError('Candidate has no features')
    if np.isinf(features.to_numpy()).any():
        raise ValueError('Features contain infinity')
    checks['coverage'] = {column: float(features[column].notna().mean()) for column in features}
    return features, checks
