"""Bound factor/model checks with the same process budget as evaluation."""
import sys
from pathlib import Path
from quantlib import workspace as W
from quantlib.data import load_bars
from quantlib.factors import compute
from quantlib.models import check_model

if __name__ == '__main__':
    root, name, output = sys.argv[1:]
    root, output = Path(root), Path(output)
    config, candidate = W.load(root), W.verify_candidate(root, name)
    bars = load_bars(root)
    bars = bars.loc[bars.index.get_level_values('datetime') <= config['splits']['discovery'][1]]
    features, checks = compute(root, candidate, bars, stage='discovery')
    model = check_model(candidate.get('model', config['model']), root, len(features.columns))
    W.write(output / 'result.json', {'candidate': name, 'factor_checks': checks, 'model_checks': model})
