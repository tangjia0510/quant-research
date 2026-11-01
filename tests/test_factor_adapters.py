"""Portable seed factors preserve their reviewed sources and research caveats."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import shutil
import sys
import types

import numpy as np
import pandas as pd
import pytest

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / 'scripts'))
from quantlib import factors

PACKAGES = SKILL / 'assets' / 'factor-library'
DEFINITIONS = {p.parent.parent.name: json.loads(p.read_text())
               for p in sorted(PACKAGES.glob('*/1.0.0/definition.json'))}
ACCEPTED = [name for name, value in DEFINITIONS.items() if value['status'] == 'accepted']
HISTORICAL = [name for name in ACCEPTED if DEFINITIONS[name]['source']['kind'] == 'historical']


def market_bars(dtype='float64', missing=False):
    """Independent fixtures exercise volume zeros, irregular prices and multiple instruments."""
    rng = np.random.default_rng(710213)
    dates = pd.bdate_range('2022-01-03', periods=200)
    rows = []
    for i, symbol in enumerate(('ALPHA', 'BETA', 'CONSTANT')):
        close = (19.0 + 31 * i) * np.exp(np.cumsum(rng.normal(.0004, .018, len(dates))))
        if symbol == 'CONSTANT':
            close[:65] = 70.
        width = rng.uniform(.1, 1.1, len(dates))
        volume = rng.integers(0, 90000, len(dates)).astype(float)
        volume[40:48] = 0
        for j, date in enumerate(dates):
            rows.append((date, symbol, close[j], close[j] + width[j], close[j] - width[j],
                         close[j], volume[j], 1.0))
    bars = pd.DataFrame(rows, columns=['datetime', 'instrument', 'open', 'high', 'low',
                                       'close', 'volume', 'factor']).set_index(['datetime', 'instrument']).sort_index()
    if missing:
        bars.loc[(dates[81], 'ALPHA'), ['open', 'high', 'low', 'close']] = np.nan
        bars.loc[(dates[115], 'BETA'), 'volume'] = np.nan
    return bars.astype(dtype)


def load_module(path, name):
    # These reviewed sources are snapshotted evidence; do not generate bytecode
    # inside immutable seed packages while exercising their unmodified bodies.
    module = types.ModuleType(name)
    module.__file__ = str(path)
    exec(compile(path.read_text(), str(path), 'exec'), module.__dict__)
    return module


def adapted(name, bars):
    module = load_module(PACKAGES / name / '1.0.0' / 'factor.py', 'adapted_' + name)
    return module.compute(bars.copy(), {})


def historical_output(name, bars, monkeypatch):
    """Execute actual preserved source; replace only HDF I/O, without PyTables or source rewrites."""
    source = PACKAGES / name / '1.0.0' / 'provenance' / 'original.py'
    assert hashlib.sha256(source.read_bytes()).hexdigest() == DEFINITIONS[name]['source']['original_sha256']
    frame = bars.rename(columns=lambda value: '$' + value)
    saved = []

    def read_hdf(path, key=None, **kwargs):
        assert path == 'daily_pv.h5' and key == 'data'
        return frame.copy()

    def to_hdf(output, path, key=None, **kwargs):
        assert path == 'result.h5' and key == 'data'
        saved.append(output.copy())

    with monkeypatch.context() as patch:
        patch.setattr(pd, 'read_hdf', read_hdf)
        patch.setattr(pd.DataFrame, 'to_hdf', to_hdf)
        module = load_module(source, 'historical_' + name)
        entrypoints = [getattr(module, attr) for attr in vars(module) if attr.startswith('calculate_')]
        assert len(entrypoints) == 1
        with contextlib.redirect_stdout(io.StringIO()):
            entrypoints[0]()
    assert len(saved) == 1
    return saved[0].reindex(bars.index)


@pytest.mark.parametrize('name', HISTORICAL)
@pytest.mark.parametrize('dtype,missing', [('float64', False), ('float32', True)])
def test_historical_adapter_matches_actual_preserved_code(name, dtype, missing, monkeypatch):
    bars = market_bars(dtype, missing)
    expected = historical_output(name, bars, monkeypatch)
    observed = adapted(name, bars)
    assert observed.index.equals(bars.index)
    assert list(observed.columns) == list(expected.columns) == DEFINITIONS[name]['output_columns']
    np.testing.assert_array_equal(observed.isna(), expected.isna())
    np.testing.assert_allclose(observed, expected, equal_nan=True, rtol=1e-10, atol=1e-12)


@pytest.mark.parametrize('name', factors.BUILTINS)
def test_registered_builtin_is_equivalent_to_existing_interface(name):
    bars = market_bars(missing=True)
    pd.testing.assert_frame_equal(adapted(name, bars), factors.builtin_features(bars, [name]))


@pytest.mark.parametrize('name', ACCEPTED)
def test_all_seed_factors_pass_real_worker_contract_and_causality(name, tmp_path):
    definition = DEFINITIONS[name]
    source = PACKAGES / name / '1.0.0' / 'factor.py'
    factors.audit_code(source.read_text())
    shutil.copyfile(source, tmp_path / 'factor.py')
    candidate = {'id': name, 'features': [], 'factor_file': 'factor.py',
                 'max_lookback': definition['max_lookback'],
                 'scale_invariant': definition['scale_invariant']}
    values, checks = factors.compute(tmp_path, candidate, market_bars())
    assert list(values.columns) == definition['output_columns']
    assert checks['future_perturbation'] and checks['prefix_invariance']
    assert checks['declared_lookback_verified'] == definition['max_lookback']
    assert checks['scale_invariance_checked'] == definition['scale_invariant']


@pytest.mark.parametrize('name', ACCEPTED)
def test_standalone_factor_preserves_unsorted_input_and_rejects_parameters(name):
    bars = market_bars().sample(frac=1, random_state=17)
    observed = adapted(name, bars)
    pd.testing.assert_frame_equal(observed, adapted(name, bars.sort_index()).reindex(bars.index))
    module = load_module(PACKAGES / name / '1.0.0' / 'factor.py', 'parameters_' + name)
    with pytest.raises(ValueError, match='no parameters'):
        module.compute(bars, {'window': 4})


def test_known_price_scale_sensitivity_is_preserved_and_not_declared_invariant():
    name = 'r2_expand_on_volume'
    bars = market_bars()
    scaled = bars.copy()
    scale = bars.index.get_level_values('instrument').map({'ALPHA': .3, 'BETA': 2., 'CONSTANT': 7.})
    for column in ('open', 'high', 'low', 'close'):
        scaled[column] *= scale
    scaled['volume'] /= scale
    expected = adapted(name, bars).mul(np.asarray(scale), axis=0)
    observed = adapted(name, scaled)
    np.testing.assert_allclose(observed, expected, rtol=1e-7, atol=1e-9, equal_nan=True)
    assert not np.allclose(observed, adapted(name, bars), equal_nan=True)
    assert DEFINITIONS[name]['scale_invariant'] is False
    evidence = json.loads((PACKAGES / name / '1.0.0/provenance/factor-math-checks.json').read_text())
    assert next(row for row in evidence['formula_checks'] if row['factor'] == 'R2_expand_on_volume')['scale_invariant'] is False


def test_rejected_bundle_is_non_executable_and_preserves_actual_failure_reason():
    name = 'trend_r1_trend_range_pos55'
    package = PACKAGES / name / '1.0.0'
    assert DEFINITIONS[name]['status'] == 'rejected'
    assert not (package / 'factor.py').exists()
    diagnostic = json.loads((package / 'provenance/trend-code-diagnostic.json').read_text())
    assert diagnostic['checks'][0]['tail_checks']['60']['matches'] is True
    assert diagnostic['checks'][1]['factor'] == 'TREND_PATH_QUAL55'
    assert diagnostic['checks'][1]['tail_checks']['60']['matches'] is False
    assert diagnostic['checks'][1]['tail_checks']['61']['matches'] is True
    failure = json.loads((package / 'provenance/failure-TREND.json').read_text())
    assert failure['entered_final_evaluation'] is False
    assert 'float32' in DEFINITIONS[name]['rejection']['original_failure']


def test_inventory_and_source_evidence_hashes():
    assert len(DEFINITIONS) == 14 and len(ACCEPTED) == 13 and len(HISTORICAL) == 8
    for name, definition in DEFINITIONS.items():
        package = PACKAGES / name / '1.0.0'
        assert definition['factor_id'] == name and definition['version'] == '1.0.0'
        original = package / definition['source']['original_snapshot']
        assert hashlib.sha256(original.read_bytes()).hexdigest() == definition['source']['original_sha256']
        if definition['status'] == 'accepted':
            assert hashlib.sha256((package / 'factor.py').read_bytes()).hexdigest() == definition['source']['adapter_sha256']
            parity = definition['validation_context']['adapter_validation']
            receipt = package / parity['evidence']
            assert hashlib.sha256(receipt.read_bytes()).hexdigest() == parity['evidence_sha256']
            proof = json.loads(receipt.read_text())
            assert proof['status'] == 'passed' and proof['factor_id'] == name
            assert proof['result']['missing_mask_equal'] and proof['result']['max_absolute_difference'] == 0.
        for record in definition['validation_context']['historical'].get('evidence_files', []):
            assert hashlib.sha256((package / record['path']).read_bytes()).hexdigest() == record['sha256']


def test_same_formula_families_remain_separate_provenance():
    bars = market_bars()
    for family in [('range_position_20', 'r1_range_pos20', 'rev_r1_range_pos20'),
                   ('volume_ratio_5', 'rev_r1_vol_dryup5')]:
        first = adapted(family[0], bars)
        for name in family[1:]:
            np.testing.assert_allclose(adapted(name, bars), first, equal_nan=True)
            assert DEFINITIONS[name]['formula_family'] == DEFINITIONS[family[0]]['formula_family']
            assert DEFINITIONS[name]['source']['original_sha256'] != DEFINITIONS[family[0]]['source']['original_sha256']
