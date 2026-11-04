#!/usr/bin/env python3
"""Real Qlib integration of agent-driven branching, review and resume. Synthetic only."""
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def run(output):
    output = Path(output).resolve()
    if output.is_relative_to(ROOT) or (output.exists() and any(output.iterdir())):
        raise ValueError('Use a fresh output outside the repository')
    output.mkdir(parents=True, exist_ok=True)
    logs = output / 'logs'; logs.mkdir()
    counter = 0

    def cli(script, *args, fail=False):
        nonlocal counter
        counter += 1
        result = subprocess.run([sys.executable, str(ROOT / script), *map(str, args)],
                                capture_output=True, text=True, timeout=900)
        (logs / f'{counter:02d}.stdout.json').write_text(result.stdout)
        (logs / f'{counter:02d}.stderr.log').write_text(result.stderr)
        value = json.loads(result.stdout)
        if fail:
            assert result.returncode and not value['ok'], value
        else:
            assert result.returncode == 0 and value['ok'], (value, result.stderr[-2000:])
        return value

    def write(path, value):
        path.write_text(json.dumps(value, indent=2) + '\n')
        return path

    spec = importlib.util.spec_from_file_location('demo', ROOT / 'assets/make_demo.py')
    demo = importlib.util.module_from_spec(spec); spec.loader.exec_module(demo)
    inputs = demo.create_demo(output / 'input', sessions=400, instruments=4)
    protocol_path = Path(inputs['protocol'])
    protocol = json.loads(protocol_path.read_text())
    protocol['robustness'] = {'enabled': False}
    protocol['budget']['max_trials'] = 6
    write(protocol_path, protocol)
    workspace = output / 'study'; tree = output / 'tree'
    cli('scripts/quant.py', 'init', '--workspace', workspace, '--protocol', protocol_path)
    shutil.copy2(ROOT / 'assets/example_factor.py', workspace / 'factor.py')
    spec_path = write(output / 'tree-spec.json', {
        'schema_version': 1, 'workspace': str(workspace), 'max_nodes': 6,
        'objective': 'SYNTHETIC software branching verification, not alpha discovery',
        'evaluation_rule': 'Verify complete artifacts and compare controlled parameters; no investment conclusion',
        'execution': {'worker_threads': 1, 'memory_budget_mb': 2048,
                      'worker_memory_mb': 512, 'timeout_seconds': 600}})

    def tree_cli(*args, **kwargs):
        return cli('scripts/research_tree.py', '--tree', tree, *args, **kwargs)

    tree_cli('init', '--spec', spec_path)
    for name, parent, window in [('root', None, 5), ('short', 'root', 3), ('long', 'root', 10)]:
        candidate = write(workspace / f'{name}.json', {
            'id': name, 'kind': 'factor', 'hypothesis': 'Synthetic parameter-branch integration test',
            'factor_file': 'factor.py', 'factor_params': {'return_window': window, 'volatility_window': 20},
            'features': ['return_5', 'volatility_20'], 'max_lookback': 21})
        proposal = write(output / f'{name}-proposal.json', {
            'id': name, 'parent': parent, 'action': 'draft' if parent is None else 'tune',
            'question': 'Does the controlled parameter variation execute?',
            'change': f'return_window={window}', 'expected_evidence': 'Native discovery artifacts',
            'decision_rule': 'Software execution only, never infer investment value', 'candidate': str(candidate)})
        tree_cli('propose', '--proposal', proposal)
        tree_cli('run', '--node', name)
        review = write(output / f'{name}-review.json', {
            'decision': 'expand' if name == 'root' else 'freeze', 'outcome': 'inconclusive',
            'reason': 'Synthetic execution test; no scientific or investment acceptance claim',
            'evidence': [str(workspace / 'runs/discovery' / name / 'result.json')],
            'next_step': 'Compare a sibling' if name == 'root' else 'Wait for real-data research'})
        tree_cli('decide', '--node', name, '--review', review)
    before = (tree / 'executions/root/state.json').read_text()
    tree_cli('run', '--node', 'root', '--resume')
    after = json.loads((tree / 'executions/root/state.json').read_text())
    assert {k: v['attempts'] for k, v in json.loads(before)['tasks'].items()} == {
        k: v['attempts'] for k, v in after['tasks'].items()}
    # Changing only ID/hypothesis cannot renew an existing computation.
    duplicate = json.loads((workspace / 'short.json').read_text()); duplicate['id'] = 'renamed'
    write(workspace / 'renamed.json', duplicate)
    proposal = json.loads((output / 'short-proposal.json').read_text())
    proposal.update(id='renamed', candidate=str(workspace / 'renamed.json'))
    p = write(output / 'duplicate.json', proposal)
    error = tree_cli('propose', '--proposal', p, fail=True)
    assert 'Duplicate computation' in error['error']['message']
    tree_cli('pause', '--reason', 'Smoke pause')
    tree_cli('run', '--node', 'root', '--resume', fail=True)
    tree_cli('resume', '--reason', 'Smoke resume')
    review = json.loads((output / 'root-review.json').read_text())
    review.update(decision='prune', next_step='Stop synthetic campaign')
    tree_cli('decide', '--node', 'root', '--review', write(output / 'prune.json', review))
    status = tree_cli('status')['result']
    assert len(status['nodes']) == 3 and all(n['blocked_by_branch'] for n in status['nodes'])
    assert all(n['execution_status'] == 'complete' for n in status['nodes'])
    result = {'ok': True, 'synthetic_only': True, 'native_experiments': 3,
              'verified': ['root and sibling execution', 'native evidence review', 'idempotent resume',
                           'renamed duplicate rejection', 'pause/resume', 'ancestor branch pruning'],
              'tree': str(tree), 'logs': str(logs)}
    write(output / 'verification.json', result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    print(json.dumps(run(parser.parse_args().output), indent=2))
