"""Isolated execution helper. This is a process boundary, not a security sandbox."""
import contextlib
import importlib.util
import json
import sys
from pathlib import Path

import pandas as pd


def main():
    code, source, output, params = map(Path, sys.argv[1:])
    with contextlib.redirect_stdout(sys.stderr):
        spec = importlib.util.spec_from_file_location('candidate_factor', code)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        frame = pd.read_parquet(source)
        result = module.compute(frame.copy(), json.loads(params.read_text()))
        if isinstance(result, pd.Series):
            result = result.to_frame(name=result.name or 'generated_factor')
        if not isinstance(result, pd.DataFrame):
            raise ValueError('compute(frame, params) must return a pandas Series or DataFrame')
        result.to_parquet(output)


if __name__ == '__main__':
    main()
