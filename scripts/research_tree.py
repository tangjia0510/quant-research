#!/usr/bin/env python3
"""Host-agent research tree. No model API, automatic selection or final evaluation."""
from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import re
import sys

from filelock import FileLock
from quantlib import workspace as W

ACTIONS = {'draft', 'improve', 'tune', 'ablate', 'debug'}
DECISIONS = {'expand', 'freeze', 'prune'}


def text(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{field} must be nonempty text')
    return value


def positive(value, field):
    if type(value) is not int or value < 1:
        raise ValueError(f'{field} must be a positive integer')
    return value


def runtime_hash():
    return W.identity({str(p.relative_to(W.SKILL)): W.digest(p)
                       for p in sorted((W.SKILL / 'scripts').rglob('*.py'))})


def development(root):
    protocol = W.load(root)
    if any((root / p).exists() for p in (
            'freeze.json', 'archive.json', 'supplementary/final-artifact-manifest.json')):
        raise ValueError('Study is frozen, archived or sealed; development is closed')
    if W.read(root / 'study.json').get('final_exposed'):
        raise ValueError('Final data exposed; do not adapt this tree to final results')
    return protocol


def save(tree, state, event, **details):
    state['updated_at'] = W.now()
    state['events'].append({'at': state['updated_at'], 'event': event, **details})
    W.write(tree / 'state.json', state)


def load(tree, mutate=True):
    state = W.read(tree / 'state.json')
    if state.get('schema_version') != 1:
        raise ValueError('Unsupported tree schema')
    if mutate:
        root = Path(state['workspace'])
        development(root)
        if W.digest(root / 'protocol.json') != state['binding']['protocol']:
            raise ValueError('Tree protocol changed')
        if runtime_hash() != state['binding']['runtime']:
            raise ValueError('Tree runtime changed; use the recorded code version')
        config = state['execution'].get('config')
        if (W.digest(config) if config else None) != state['binding']['config']:
            raise ValueError('Tree library config changed')
        if W.read(root / 'research-tree-owner.json')['tree'] != str(tree):
            raise ValueError('Tree does not own this study')
    return state


def active(state):
    if state['status'] != 'active':
        raise ValueError('Tree is paused; resume it with a reason first')


def unblocked(state, node):
    while node:
        if node['decision'] in {'freeze', 'prune'}:
            raise ValueError(f"Branch blocked by {node['id']}: {node['decision']}")
        node = state['nodes'].get(node['parent'])


def initialize(tree, spec):
    allowed = {'schema_version', 'workspace', 'objective', 'evaluation_rule',
               'max_nodes', 'max_debug_depth', 'execution'}
    if not isinstance(spec, dict) or set(spec) - allowed or spec.get('schema_version') != 1:
        raise ValueError('Unknown tree spec fields or schema_version')
    root = Path(spec['workspace']).resolve(strict=True)
    if (tree.is_relative_to(W.SKILL) or tree.is_relative_to(root)
            or root.is_relative_to(tree)):
        raise ValueError('Tree must be outside and separate from skill and study')
    if (tree / 'state.json').exists():
        raise ValueError('Tree already exists; use status/resume')
    for k in ('objective', 'evaluation_rule'):
        text(spec.get(k), k)
    positive(spec.get('max_nodes'), 'max_nodes')
    depth = spec.get('max_debug_depth', 3)
    positive(depth, 'max_debug_depth')
    execution = copy.deepcopy(spec.get('execution', {}))
    allowed_execution = {'worker_threads', 'max_attempts', 'timeout_seconds',
                         'memory_budget_mb', 'worker_memory_mb', 'prepare_memory_mb', 'config'}
    if not isinstance(execution, dict) or set(execution) - allowed_execution:
        raise ValueError('Unknown execution fields')
    for k, default in {'worker_threads': 1, 'max_attempts': 2, 'timeout_seconds': 3600}.items():
        execution.setdefault(k, default)
    for k, v in execution.items():
        if k != 'config':
            positive(v, k)
    if execution['worker_threads'] > 64:
        raise ValueError('worker_threads must be <= 64')
    if 'config' in execution:
        execution['config'] = str(Path(execution['config']).resolve(strict=True))
    with FileLock(str(root / '.study.lock'), timeout=0):
        protocol = development(root)
        owner = root / 'research-tree-owner.json'
        if owner.exists() and W.read(owner)['tree'] != str(tree):
            raise ValueError('Study already belongs to another tree; do not reset its budget')
        registered = len(list((root / 'candidates').glob('*/candidate.json')))
        if spec['max_nodes'] > protocol['budget']['max_trials'] - registered:
            raise ValueError('Tree budget exceeds remaining native candidate budget')
        state = dict(schema_version=1, workspace=str(root), objective=spec['objective'],
                     evaluation_rule=spec['evaluation_rule'], max_nodes=spec['max_nodes'],
                     max_debug_depth=depth, execution=execution, status='active',
                     nodes={}, events=[], created_at=W.now(), binding={
                         'protocol': W.digest(root / 'protocol.json'), 'runtime': runtime_hash(),
                         'config': W.digest(execution['config']) if execution.get('config') else None})
        W.write(owner, {'tree': str(tree)})
        save(tree, state, 'initialized')
    return state


def computation_key(root, candidate):
    """Exact computation dedup, not mathematical equivalence detection."""
    c = copy.deepcopy(candidate)
    for k in ('id', 'hypothesis'):
        c.pop(k, None)
    c.setdefault('model', W.load(root)['model'])
    for obj, key in ((c, 'factor_file'), (c['model'], 'file'), (c.get('source', {}), 'path')):
        if obj.get(key):
            obj[key] = {'sha256': W.digest(W.inside(root, obj[key]))}
    return W.identity(c)


def propose(tree, state, proposal):
    active(state)
    required = {'id', 'parent', 'action', 'question', 'change', 'expected_evidence',
                'decision_rule', 'candidate'}
    if not isinstance(proposal, dict) or set(proposal) != required:
        raise ValueError('Proposal requires exactly: ' + ', '.join(sorted(required)))
    name = proposal['id']
    if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}', name):
        raise ValueError('Node id must be a safe short name')
    for k in ('question', 'change', 'expected_evidence', 'decision_rule', 'candidate'):
        text(proposal[k], k)
    if name in state['nodes']:
        raise ValueError('Node already exists; use run --resume for unchanged execution')
    if len(state['nodes']) >= state['max_nodes']:
        raise ValueError('Tree node budget exhausted (failed/pruned nodes count)')
    action, parent_id = proposal['action'], proposal['parent']
    if action not in ACTIONS:
        raise ValueError('Unknown action')
    depth = 0
    if action == 'draft':
        if parent_id is not None:
            raise ValueError('draft must have null parent')
    else:
        parent = state['nodes'].get(parent_id)
        if parent is None:
            raise ValueError('Parent does not exist')
        unblocked(state, parent)
        if action == 'debug':
            if parent['execution_status'] != 'failed':
                raise ValueError('debug requires a failed parent; resume interruptions first')
            depth = parent['debug_depth'] + 1
            if depth > state['max_debug_depth']:
                raise ValueError('Debug depth exhausted; preserve the failed branch')
        elif parent['execution_status'] != 'complete' or parent['decision'] != 'expand':
            raise ValueError('Parent must be complete and reviewed for expansion')
    root = Path(state['workspace'])
    with FileLock(str(root / '.study.lock'), timeout=0):
        development(root)
        candidate_path = W.inside(root, proposal['candidate'])
        candidate = W.read(candidate_path)
        if candidate.get('id') != name:
            raise ValueError('Candidate id must equal node id')
        key = computation_key(root, candidate)
        duplicates = [n['id'] for n in state['nodes'].values() if n['computation_key'] == key]
        if duplicates:
            raise ValueError('Duplicate computation; existing nodes: ' + ', '.join(duplicates))
        # Native registration snapshots code and counts the trial before any execution.
        registered = W.register(root, candidate_path, library_config_path=state['execution'].get('config'))
        frozen_input = copy.deepcopy(candidate)
        if candidate.get('factor_file'):
            frozen_input['factor_file'] = registered['factor_file']
        if candidate.get('model', {}).get('file'):
            frozen_input['model']['file'] = registered['model']['file']
        if candidate.get('source', {}).get('path'):
            frozen_input['source']['path'] = registered['source']['path']
        path = root / 'tree-inputs' / (name + '.json')
        if path.exists() and W.read(path) != frozen_input:
            raise ValueError('Frozen tree input already differs')
        W.write(path, frozen_input)
    node = {**proposal, 'candidate': str(path), 'computation_key': key,
            'candidate_hash': registered['candidate_hash'], 'input_hash': W.digest(path),
            'debug_depth': depth, 'execution_status': 'planned', 'decision': 'pending',
            'reviews': [], 'created_at': W.now()}
    state['nodes'][name] = node
    save(tree, state, 'proposed', node=name)
    return node


def verify_input(state, node):
    if W.digest(node['candidate']) != node['input_hash']:
        raise ValueError('Frozen tree input changed')
    candidate = W.verify_candidate(Path(state['workspace']), node['id'])
    if candidate['candidate_hash'] != node['candidate_hash']:
        raise ValueError('Registered candidate changed')


def make_plan(state, node):
    root = Path(state['workspace'])
    tasks = []
    if not (root / 'prepared.json').exists():
        tasks.append({'id': 'prepare', 'command': 'prepare', 'workspace': str(root)})
    tasks += [dict(id='check', command='check', workspace=str(root), candidate=node['candidate'],
                   depends_on=['prepare'] if tasks else []),
              dict(id='evaluate', command='evaluate', workspace=str(root), candidate=node['candidate'],
                   depends_on=['check'])]
    return dict(schema_version=1, global_candidate_budget=1, max_workers=1,
                cpu_budget=state['execution']['worker_threads'],
                tasks=tasks, **state['execution'])


def run_node(tree, state, name, resume=False):
    import batch
    active(state)
    node = state['nodes'][name]
    unblocked(state, node)
    for other in state['nodes'].values():
        if other['id'] != name and other['execution_status'] in {'running', 'interrupted'}:
            raise ValueError(f"Recover node {other['id']} first with run --resume")
    if node['execution_status'] != 'planned' and not resume:
        raise ValueError('Existing execution requires run --resume')
    verify_input(state, node)
    output = tree / 'executions' / name
    plan_path = tree / 'plans' / (name + '.json')
    if not plan_path.exists():
        W.write(plan_path, make_plan(state, node))
    if node.get('plan_hash') and W.digest(plan_path) != node['plan_hash']:
        raise ValueError('Recorded execution plan changed')
    node['plan_hash'] = W.digest(plan_path)
    prior = W.read(output / 'state.json') if (output / 'state.json').exists() else None
    plan = batch.load_plan(plan_path, resolved_defaults=prior['plan'] if prior else None)
    node['execution_status'] = 'running'
    save(tree, state, 'execution_started', node=name, resume=resume)
    try:
        code = batch.run(plan, output, resume=prior is not None)
        node['execution_status'] = 'complete' if code == 0 else ('interrupted' if code == 130 else 'failed')
        node['batch_state'] = str(output / 'state.json')
        if code == 0:
            metrics = Path(state['workspace']) / 'runs' / 'discovery' / name / 'result.json'
            node['metrics'] = str(metrics)
            node['metrics_hash'] = W.digest(metrics)
        save(tree, state, 'execution_finished', node=name, exit_code=code)
        return {'node': node, 'exit_code': code}
    except BaseException as error:
        # Batch owns process cleanup. Keep ambiguous crashes resumable, not expandable.
        node['execution_status'] = 'interrupted'
        save(tree, state, 'execution_interrupted', node=name,
             error={'type': type(error).__name__, 'message': str(error)})
        raise


def decide(tree, state, name, review):
    node = state['nodes'][name]
    if any(n['execution_status'] in {'running', 'interrupted'} for n in state['nodes'].values()):
        raise ValueError('Reconcile interrupted execution with run --resume before review')
    required = {'decision', 'outcome', 'reason', 'evidence', 'next_step'}
    if not isinstance(review, dict) or set(review) != required:
        raise ValueError('Review requires exactly: ' + ', '.join(sorted(required)))
    if review['decision'] not in DECISIONS or review['outcome'] not in {
            'supported', 'refuted', 'inconclusive', 'invalid'}:
        raise ValueError('Invalid decision or outcome')
    for field in ('reason', 'next_step'):
        text(review[field], field)
    if node['execution_status'] in {'running', 'interrupted'}:
        raise ValueError('Reconcile interrupted execution with run --resume before review')
    if review['decision'] == 'expand' and node['execution_status'] != 'complete':
        raise ValueError('Only complete experiments can expand')
    if node['execution_status'] != 'complete' and review['outcome'] != 'invalid':
        raise ValueError('Unexecuted or failed experiments cannot establish scientific outcomes')
    if review['decision'] == 'expand' and review['outcome'] == 'invalid':
        raise ValueError('Invalid evidence cannot authorize expansion')
    evidence = review['evidence']
    if not isinstance(evidence, list) or not evidence:
        raise ValueError('Review requires evidence paths')
    root = Path(state['workspace'])
    receipts = {}
    for path in evidence:
        p = Path(text(path, 'evidence path')).resolve(strict=True)
        batch_root = tree / 'executions' / name
        allowed = [root / 'runs' / 'discovery' / name, root / 'candidates' / name, batch_root]
        if not any(p.is_relative_to(folder) for folder in allowed) or not p.is_file():
            raise ValueError('Evidence must belong to this node discovery/check/batch artifacts')
        receipts[str(p)] = W.digest(p)
    if node['execution_status'] == 'complete':
        # Verify full native discovery receipt under the same execution thread setting.
        import batch
        previous = os.environ.get('QUANT_WORKER_THREADS')
        os.environ['QUANT_WORKER_THREADS'] = str(state['execution']['worker_threads'])
        try:
            verify_input(state, node)
            native = batch.receipt({'workspace': str(root), 'command': 'evaluate', 'candidate': node['candidate']})
            saved = W.read(tree / 'executions' / name / 'state.json')['tasks']['evaluate']['receipt']
            if native != saved or W.digest(node['metrics']) != node['metrics_hash']:
                raise ValueError('Experiment evidence changed')
        finally:
            if previous is None:
                os.environ.pop('QUANT_WORKER_THREADS', None)
            else:
                os.environ['QUANT_WORKER_THREADS'] = previous
    node['reviews'].append({**review, 'evidence_hashes': receipts, 'at': W.now()})
    node['decision'] = review['decision']
    save(tree, state, 'reviewed', node=name, decision=review['decision'])
    return node


def status(tree):
    state = load(tree, mutate=False)
    rows = []
    for n in state['nodes'].values():
        try:
            unblocked(state, n)
            blocked = False
        except ValueError:
            blocked = True
        rows.append({k: n[k] for k in ('id', 'parent', 'action', 'execution_status', 'decision', 'debug_depth')} | {
            'blocked_by_branch': blocked, 'question': n['question'],
            'metrics': n.get('metrics'), 'batch_state': n.get('batch_state')})
    return {'tree': str(tree), 'objective': state['objective'], 'evaluation_rule': state['evaluation_rule'],
            'status': state['status'], 'remaining_nodes': state['max_nodes'] - len(rows), 'nodes': rows,
            'recover_first': [r['id'] for r in rows if r['execution_status'] in {'running', 'interrupted'}],
            'review_next': [r['id'] for r in rows if r['execution_status'] == 'complete' and r['decision'] == 'pending'],
            'notice': 'Host agent chooses the next node. No background model calls or automatic finalization.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tree', required=True, help='Persistent tree directory outside study and repository')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('init').add_argument('--spec', required=True)
    sub.add_parser('status')
    sub.add_parser('show').add_argument('--node', required=True)
    sub.add_parser('propose').add_argument('--proposal', required=True)
    run = sub.add_parser('run')
    run.add_argument('--node', required=True)
    run.add_argument('--resume', action='store_true')
    review = sub.add_parser('decide')
    review.add_argument('--node', required=True)
    review.add_argument('--review', required=True)
    reopen = sub.add_parser('reopen')
    reopen.add_argument('--node', required=True)
    reopen.add_argument('--reason', required=True)
    for action in ('pause', 'resume'):
        sub.add_parser(action).add_argument('--reason', required=True)
    args = parser.parse_args()
    tree = Path(args.tree).resolve()
    try:
        code = 0
        if args.command in {'status', 'show'}:
            result = status(tree) if args.command == 'status' else load(tree, False)['nodes'][args.node]
        else:
            tree.mkdir(parents=True, exist_ok=True)
            with FileLock(str(tree / '.tree.lock'), timeout=0):
                if args.command == 'init':
                    result = initialize(tree, W.read(args.spec))
                else:
                    state = load(tree)
                    if args.command == 'propose':
                        result = propose(tree, state, W.read(args.proposal))
                    elif args.command == 'run':
                        result = run_node(tree, state, args.node, args.resume)
                        code = result['exit_code']
                    elif args.command == 'decide':
                        result = decide(tree, state, args.node, W.read(args.review))
                    elif args.command == 'reopen':
                        text(args.reason, 'reason')
                        node = state['nodes'][args.node]
                        if node['decision'] not in {'freeze', 'prune'}:
                            raise ValueError('Only frozen or pruned branches can reopen')
                        node['decision'] = 'pending'
                        save(tree, state, 'reopened', node=args.node, reason=args.reason)
                        result = node
                    else:
                        text(args.reason, 'reason')
                        state['status'] = 'paused' if args.command == 'pause' else 'active'
                        save(tree, state, args.command, reason=args.reason)
                        result = {'status': state['status']}
        print(json.dumps({'ok': code == 0, 'command': args.command, 'result': result}, ensure_ascii=False))
        return code
    except Exception as error:
        print(json.dumps({'ok': False, 'error': {'type': type(error).__name__, 'message': str(error)}}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
