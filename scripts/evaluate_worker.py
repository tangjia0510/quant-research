"""Run one deterministic numerical attempt in a bounded child process."""
import sys
from pathlib import Path
from quantlib import workspace as W
from quantlib.engine import evaluate

if __name__ == '__main__':
    root, name, phase, output = sys.argv[1:]
    root, output = Path(root), Path(output)
    candidate = W.verify_candidate(root, name)
    result = evaluate(root, W.load(root), candidate, phase, output)
    W.write(output / 'result.json', result)
