"""CPU model adapters. No network or LLM dependency; only registered local code."""
from __future__ import annotations

import importlib.util
import json
import pickle
import random
import sys
from pathlib import Path

import numpy as np

# On macOS the locked Torch and LightGBM wheels load native OpenMP runtimes.
# Loading Torch first can crash inside LightGBM, even with n_jobs=1. Initialize
# LightGBM's runtime before any candidate can import Torch; no unsafe duplicate-
# runtime environment override is used. LightGBM is a required core dependency.
if sys.platform == 'darwin':
    import lightgbm as _lightgbm_runtime


def fit_predict(train_x, train_y, valid_x, valid_y, evaluation_x, spec, output: Path, workspace: Path):
    kind = spec.get('kind', 'ridge')
    params = dict(spec.get('params', {}))
    seed = int(params.pop('seed', 42))
    random.seed(seed)
    np.random.seed(seed)
    output.mkdir(parents=True, exist_ok=True)
    if kind == 'ridge':
        from sklearn.linear_model import Ridge
        model = Ridge(**({'alpha': 1.0} | params))
        model.fit(train_x, train_y)
        prediction = model.predict(evaluation_x)
    elif kind == 'lightgbm':
        import lightgbm as lgb
        patience = int(params.pop('patience', 20))
        model = lgb.LGBMRegressor(**({'n_estimators': 200, 'n_jobs': 1, 'random_state': seed,
                                     'verbosity': -1} | params))
        model.fit(train_x, train_y, eval_set=[(valid_x, valid_y)],
                  callbacks=[lgb.early_stopping(patience, verbose=False)])
        prediction = model.predict(evaluation_x)
    elif kind == 'xgboost':
        import xgboost as xgb
        rounds = int(params.pop('num_boost_round', 200))
        patience = int(params.pop('early_stopping_rounds', 20))
        opts = {'objective': 'reg:squarederror', 'tree_method': 'hist', 'device': 'cpu',
                'max_depth': 4, 'learning_rate': 0.05, 'seed': seed, 'nthread': 1} | params
        train = xgb.DMatrix(train_x, label=train_y)
        valid = xgb.DMatrix(valid_x, label=valid_y)
        model = xgb.train(opts, train, num_boost_round=rounds, evals=[(valid, 'valid')],
                          early_stopping_rounds=patience, verbose_eval=False)
        prediction = model.predict(xgb.DMatrix(evaluation_x), iteration_range=(0, model.best_iteration + 1))
        model.save_model(output / 'model.ubj')
    elif kind == 'custom':
        return _custom(train_x, train_y, valid_x, valid_y, evaluation_x, spec, params, seed, output, workspace)
    else:
        raise ValueError(f'Unknown model kind: {kind}')
    # Only own local artifacts are deserialized, immediately after writing.
    path = output / 'model.pkl'
    path.write_bytes(pickle.dumps(model))
    again = pickle.loads(path.read_bytes())
    if kind == 'xgboost':
        reloaded = again.predict(xgb.DMatrix(evaluation_x), iteration_range=(0, again.best_iteration + 1))
    else:
        reloaded = again.predict(evaluation_x)
    np.testing.assert_allclose(prediction, reloaded, rtol=1e-7, atol=1e-9)
    prediction = np.asarray(prediction).reshape(-1)
    if not np.isfinite(prediction).all():
        raise ValueError('Model produced non-finite predictions')
    return prediction, {'kind': kind, 'seed': seed, 'reload_predictions_match': True,
                        'best_iteration': int(getattr(model, 'best_iteration', getattr(model, 'best_iteration_', 0)))}


def _custom(train_x, train_y, valid_x, valid_y, evaluation_x, spec, params, seed, output, workspace):
    import torch
    path = (workspace / spec['file']).resolve()
    if not path.is_relative_to(workspace.resolve()) or not path.is_file():
        raise ValueError('Custom model must be a registered workspace file')
    module_spec = importlib.util.spec_from_file_location('quant_research_candidate_model', path)
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    torch.manual_seed(seed)
    torch.set_num_threads(1)
    model = module.build_model(train_x.shape[1])
    if not isinstance(model, torch.nn.Module):
        raise ValueError('build_model(num_features) must return torch.nn.Module')
    model = model.cpu()
    epochs = int(params.pop('epochs', 30))
    patience = int(params.pop('patience', 5))
    batch_size = int(params.pop('batch_size', 128))
    lr = float(params.pop('lr', 0.001))
    if params:
        raise ValueError(f'Unsupported custom training parameters: {sorted(params)}')
    if not (1 <= epochs <= 10000 and 1 <= patience and 1 <= batch_size):
        raise ValueError('Invalid custom training budget')
    tx = torch.tensor(np.asarray(train_x), dtype=torch.float32)
    ty = torch.tensor(np.asarray(train_y), dtype=torch.float32)
    vx = torch.tensor(np.asarray(valid_x), dtype=torch.float32)
    vy = torch.tensor(np.asarray(valid_y), dtype=torch.float32)
    ex = torch.tensor(np.asarray(evaluation_x), dtype=torch.float32)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    best_loss, stale, history = float('inf'), 0, []
    best_epoch = 0
    for epoch in range(epochs):
        model.train()
        for indices in torch.randperm(len(tx)).split(batch_size):
            optimizer.zero_grad()
            predicted = model(tx[indices]).reshape(-1)
            if predicted.shape != ty[indices].shape:
                raise ValueError('Custom model must return one score per input row')
            loss = ((predicted - ty[indices]) ** 2).mean()
            if not torch.isfinite(loss):
                raise ValueError('Non-finite custom training loss')
            loss.backward()
            optimizer.step()
        model.eval()
        with torch.no_grad():
            valid_pred = model(vx).reshape(-1)
            if valid_pred.shape != vy.shape:
                raise ValueError('Custom model returned incorrect validation shape')
            valid_loss = float(((valid_pred - vy) ** 2).mean())
        if not np.isfinite(valid_loss):
            raise ValueError('Non-finite validation loss')
        history.append({'epoch': epoch, 'validation_mse': valid_loss})
        if valid_loss < best_loss:
            best_loss, stale, best_epoch = valid_loss, 0, epoch
            torch.save(model.state_dict(), output / 'model.pt')
        else:
            stale += 1
            if stale >= patience:
                break
    model.load_state_dict(torch.load(output / 'model.pt', map_location='cpu', weights_only=True))
    model.eval()
    with torch.no_grad():
        prediction = model(ex).reshape(-1).numpy()
    again = module.build_model(train_x.shape[1]).cpu()
    again.load_state_dict(torch.load(output / 'model.pt', map_location='cpu', weights_only=True))
    again.eval()
    with torch.no_grad():
        reloaded = again(ex).reshape(-1).numpy()
    np.testing.assert_allclose(prediction, reloaded, rtol=1e-6, atol=1e-7)
    if len(prediction) != len(evaluation_x) or not np.isfinite(prediction).all():
        raise ValueError('Custom model returned invalid predictions')
    (output / 'learning.json').write_text(json.dumps(history, indent=2))
    return prediction, {'kind': 'custom', 'seed': seed, 'best_iteration': best_epoch,
                        'validation_mse': best_loss, 'reload_predictions_match': True, 'device': 'cpu'}


def check_model(spec, workspace, num_features):
    """Check the model interface before an expensive training attempt."""
    kind = spec.get('kind', 'ridge')
    if kind not in {'ridge', 'lightgbm', 'xgboost', 'custom'}:
        raise ValueError(f'Unknown model kind: {kind}')
    if kind == 'custom':
        import torch
        path = (Path(workspace) / spec['file']).resolve()
        if not path.is_relative_to(Path(workspace).resolve()) or not path.is_file():
            raise ValueError('Custom model file must be inside workspace')
        module_spec = importlib.util.spec_from_file_location('quant_research_model_probe', path)
        module = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(module)
        model = module.build_model(num_features)
        if not isinstance(model, torch.nn.Module):
            raise ValueError('build_model must return torch.nn.Module')
        model.cpu().eval()
        with torch.no_grad():
            for size in [1, 7]:
                prediction = model(torch.zeros(size, num_features)).reshape(-1)
                if len(prediction) != size or not torch.isfinite(prediction).all():
                    raise ValueError('Custom model must emit a finite score per row')
        return {'kind': kind, 'forward_shape_checked': True, 'device': 'cpu'}
    import importlib.util as util
    dependency = {'ridge': 'sklearn', 'lightgbm': 'lightgbm', 'xgboost': 'xgboost'}[kind]
    if util.find_spec(dependency) is None:
        raise ValueError(f'Model dependency is missing: {dependency}')
    return {'kind': kind, 'dependency_available': True}
