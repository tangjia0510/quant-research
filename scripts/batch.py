#!/usr/bin/env python3
"""Bounded discovery-only scheduler; isolated workspaces, normal locked quant CLI."""
from __future__ import annotations
import argparse
import json
import importlib.metadata
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time

from filelock import FileLock
import quant
from quantlib import workspace as W

COMMANDS = {'prepare', 'check', 'evaluate'}


def positive(value, name):
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f'{name} must be a positive integer')
    return value


def memory_limit_mb():
    physical = os.sysconf('SC_PAGE_SIZE') * os.sysconf('SC_PHYS_PAGES')
    limits = [physical]
    try:
        available = next(int(line.split()[1]) * 1024 for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemAvailable:'))
        limits.append(available)
    except (OSError, StopIteration, ValueError):
        pass
    for name, used in (('/sys/fs/cgroup/memory.max', '/sys/fs/cgroup/memory.current'),
                       ('/sys/fs/cgroup/memory/memory.limit_in_bytes', '/sys/fs/cgroup/memory/memory.usage_in_bytes')):
        try:
            limits.append(max(0, int(Path(name).read_text().strip()) - int(Path(used).read_text().strip())))
        except (OSError, ValueError):
            pass
    return max(1, int(min(limits) / 1024 ** 2 * .8))


def load_plan(path, resolved_defaults=None):
    plan = W.read(path)
    allowed = {'schema_version', 'tasks', 'max_workers', 'worker_threads', 'global_candidate_budget',
               'max_attempts', 'timeout_seconds', 'cpu_budget', 'memory_budget_mb',
               'worker_memory_mb', 'prepare_memory_mb', 'config'}
    if set(plan) - allowed or plan.get('schema_version') != 1:
        raise ValueError('Unknown plan fields or schema_version (expected 1)')
    defaults = dict(max_workers=2, worker_threads=1, max_attempts=2, timeout_seconds=3600,
                    cpu_budget=len(os.sched_getaffinity(0)) if hasattr(os, 'sched_getaffinity') else os.cpu_count() or 1,
                    memory_budget_mb=memory_limit_mb(), worker_memory_mb=2048)
    if resolved_defaults is not None:
        defaults.update({name: resolved_defaults[name] for name in defaults})
    for name, value in defaults.items():
        plan.setdefault(name, value)
    plan.setdefault('prepare_memory_mb', resolved_defaults['prepare_memory_mb'] if resolved_defaults else plan['memory_budget_mb'])
    for name in (*defaults, 'prepare_memory_mb', 'global_candidate_budget'):
        positive(plan.get(name), name)
    available_cpus = len(os.sched_getaffinity(0)) if hasattr(os, 'sched_getaffinity') else os.cpu_count() or 1
    if plan['cpu_budget'] > available_cpus or plan['memory_budget_mb'] > memory_limit_mb():
        raise ValueError('Declared CPU/memory budget exceeds observed available resources')
    if plan['worker_threads'] > 64 or plan['max_workers'] * plan['worker_threads'] > plan['cpu_budget']:
        raise ValueError('Outer workers times inner threads exceeds CPU budget (threads max 64)')
    if max(plan['worker_memory_mb'], plan['prepare_memory_mb']) > plan['memory_budget_mb']:
        raise ValueError('A single job exceeds the declared memory budget')
    if 'config' in plan:
        plan['config'] = str(Path(plan['config']).resolve(strict=True))
    tasks = plan.get('tasks')
    if not isinstance(tasks, list) or not tasks:
        raise ValueError('tasks must be a nonempty list')
    by_id, keys = {}, set()
    for t in tasks:
        if not isinstance(t, dict) or set(t) - {'id', 'command', 'workspace', 'candidate', 'depends_on'}:
            raise ValueError('Unknown task fields')
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}', str(t.get('id', ''))) or t['id'] in by_id:
            raise ValueError('Task IDs must be unique safe names')
        if t.get('command') not in COMMANDS:
            raise ValueError('Only prepare/check/evaluate are allowed')
        t['workspace'] = str(Path(t['workspace']).resolve(strict=True))
        root = Path(t['workspace'])
        if not (root / 'study.json').is_file() or (root / 'freeze.json').exists() or (root / 'archive.json').exists() or (root / 'supplementary/final-artifact-manifest.json').exists():
            raise ValueError('Workspace must be initialized, nonarchived and unfrozen')
        if t['command'] == 'prepare':
            if 'candidate' in t:
                raise ValueError('prepare does not accept candidate')
        else:
            t['candidate'] = str(W.inside(root, t['candidate']).resolve(strict=True))
        t.setdefault('depends_on', [])
        if not isinstance(t['depends_on'], list) or not all(isinstance(x, str) for x in t['depends_on']):
            raise ValueError('depends_on must be a list of task IDs')
        key = (t['workspace'], t['command'], W.read(t['candidate']).get('id') if t.get('candidate') else None)
        if key in keys:
            raise ValueError('Duplicate task or multiple prepare tasks for one workspace')
        keys.add(key); by_id[t['id']] = t
    def ancestors(name, visiting=None):
        visiting = set() if visiting is None else visiting
        if name in visiting:
            raise ValueError('Dependency cycle')
        if name not in by_id:
            raise ValueError('Unknown dependency')
        result = set()
        for dep in by_id[name]['depends_on']:
            result.add(dep)
            result.update(ancestors(dep, visiting | {name}))
        return result
    for t in tasks:
        upstream = [by_id[x] for x in ancestors(t['id'])]
        if t['command'] == 'evaluate' and not any(
                x['command'] == 'check' and x['workspace'] == t['workspace'] and x.get('candidate') == t['candidate']
                for x in upstream):
            raise ValueError('evaluate requires a same-candidate check dependency')
        if t['command'] != 'prepare' and not (Path(t['workspace']) / 'prepared.json').is_file() and not any(
                x['command'] == 'prepare' and x['workspace'] == t['workspace'] for x in upstream):
            raise ValueError('Unprepared workspace requires a prepare dependency')
    candidates = {(t['workspace'], W.read(t['candidate']).get('id')) for t in tasks if t['command'] != 'prepare'}
    if len(candidates) > plan['global_candidate_budget']:
        raise ValueError('Global candidate budget exceeded (includes all planned candidates, not successes)')
    return plan


def hash_path(path):
    path = Path(path)
    if path.is_file():
        return W.digest(path)
    if not path.is_dir():
        raise ValueError(f'Missing source input: {path}')
    return W.identity({str(p.relative_to(path)): W.digest(p) for p in sorted(path.rglob('*')) if p.is_file()})


def bind_inputs(plan):
    """Coordinator-only registration under original study locks, before any launch."""
    roots = sorted({t['workspace'] for t in plan['tasks']})
    inputs, comparison = {}, None
    for name in roots:
        root = Path(name)
        with FileLock(str(root / '.study.lock'), timeout=0):
            config = W.load(root)
            if any((root / p).exists() for p in ('freeze.json', 'archive.json', 'supplementary/final-artifact-manifest.json')):
                raise ValueError('Cannot schedule a frozen or sealed study')
            for spec in [config.get('model', {})] + [W.read(t['candidate']).get('model', {}) for t in plan['tasks'] if t['workspace'] == name and t.get('candidate')]:
                for key in ('n_jobs', 'nthread', 'num_threads', 'num_thread', 'nthreads'):
                    value = spec.get('params', {}).get(key)
                    if value is not None and (not isinstance(value, int) or value < 1 or value > plan['worker_threads']):
                        raise ValueError('Model thread parameters must fit worker_threads')
            resolved = quant.resolve_data(config, plan.get('config'))
            source = {key: hash_path(resolved['data'][key]) for key in ('path', 'calendar', 'universe') if resolved['data'].get(key)}
            comparable = json.loads(json.dumps(config))
            for key in ('path', 'calendar', 'universe'):
                comparable['data'].pop(key, None)
            current = W.identity({'protocol': comparable, 'source': source})
            if comparison is not None and current != comparison:
                raise ValueError('Batch workspaces must have matched protocol/data/sample assumptions')
            comparison = current
            if (root / 'prepared.json').exists():
                quant.prepared(root)
            candidates = {}
            for t in plan['tasks']:
                if t['workspace'] == name and t['command'] != 'prepare':
                    candidate = W.register(root, t['candidate'], library_config_path=plan.get('config'))
                    candidates[t['candidate']] = {'source_hash': W.digest(t['candidate']), 'candidate_hash': candidate['candidate_hash'], 'id': candidate['id']}
            inputs[name] = {'protocol': W.digest(root / 'protocol.json'), 'source': source, 'candidates': candidates}
    return {'inputs': inputs, 'runtime': {str(p.relative_to(W.SKILL)): W.digest(p) for p in sorted((W.SKILL / 'scripts').rglob('*.py'))},
            'python': sys.version, 'executable': sys.executable,
            'versions': {name: importlib.metadata.version(name) for name in ('numpy', 'pandas', 'pyqlib', 'scikit-learn', 'filelock')},
            'config': W.digest(plan['config']) if plan.get('config') else None}


def receipt(task):
    root = Path(task['workspace'])
    quant.prepared(root)
    if task['command'] == 'prepare':
        return {'prepared': W.digest(root / 'prepared.json')}
    candidate = W.verify_candidate(root, W.read(task['candidate'])['id'])
    if task['command'] == 'check':
        path = root / 'candidates' / candidate['id'] / 'checks.json'
        value = W.read(path)
        if value.get('candidate') != candidate['id'] or 'factor_checks' not in value or 'model_checks' not in value:
            raise ValueError('Invalid native check receipt')
        return {'checks': W.digest(path), 'candidate': candidate['candidate_hash']}
    folder = root / 'runs' / 'discovery' / candidate['id']
    run = quant.valid_result(folder)
    if run['status'] != 'complete' or run['input_hash'] != W.fingerprint(root, candidate, 'discovery'):
        raise ValueError('Native cached result does not match current inputs')
    return {'run': W.digest(folder / 'run.json'), 'input_hash': run['input_hash']}


def command_for(plan, task):
    cmd = [sys.executable, str(W.SKILL / 'scripts/quant.py'), '--worker-threads', str(plan['worker_threads'])]
    if plan.get('config'):
        cmd += ['--config', plan['config']]
    cmd += [task['command'], '--workspace', task['workspace']]
    if task.get('candidate'):
        cmd += ['--candidate', task['candidate']]
    return cmd


def group_rss_mb(pgid):
    """Linux observational sum (shared pages can be counted more than once)."""
    total = 0
    try:
        for path in Path('/proc').iterdir():
            if not path.name.isdigit(): continue
            try:
                fields = (path / 'stat').read_text().rsplit(')', 1)[1].split()
                if int(fields[2]) == pgid and fields[0] != 'Z':
                    total += int(fields[21]) * os.sysconf('SC_PAGE_SIZE')
            except (OSError, ValueError, IndexError):
                continue
    except OSError:
        return None
    return total / 1024 ** 2


def stop_process(process):
    # A CLI leader can exit while descendants remain in its dedicated group.
    if os.name == 'posix':
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    elif process.poll() is None:
        process.terminate()
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        if os.name == 'posix':
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        else:
            process.kill()
        process.wait()
    if os.name == 'posix':
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def run(plan, output, resume=False):
    if os.name != 'posix':
        raise ValueError('Batch process-group cancellation currently requires a POSIX host')
    output = Path(output).resolve()
    if output.is_relative_to(W.SKILL) or any(output == Path(t['workspace']) or output.is_relative_to(Path(t['workspace'])) or Path(t['workspace']).is_relative_to(output) for t in plan['tasks']):
        raise ValueError('Batch output must be outside skill and study directories')
    output.mkdir(parents=True, exist_ok=True)
    with FileLock(str(output / '.batch.lock'), timeout=0):
        state_path = output / 'state.json'
        if state_path.exists() != resume:
            raise ValueError('Existing output requires --resume; --resume requires state.json')
        prior = W.read(state_path) if resume else None
        if prior is not None and prior['plan'] != plan:
            raise ValueError('Batch plan changed; use a new batch')
        if prior is not None:
            runtime = {str(p.relative_to(W.SKILL)): W.digest(p) for p in sorted((W.SKILL / 'scripts').rglob('*.py'))}
            if prior['binding']['runtime'] != runtime:
                raise ValueError('Batch runtime changed; use a new batch')
            for t in plan['tasks']:
                if t.get('candidate'):
                    root = Path(t['workspace'])
                    if not (root / 'candidates' / W.read(t['candidate'])['id'] / 'candidate.json').is_file():
                        raise ValueError('Registered candidate missing on resume')
        binding = bind_inputs(plan)
        identity = W.identity({'plan': plan, 'binding': binding})
        state = W.read(state_path) if resume else {'schema_version': 1, 'identity': identity, 'plan': plan, 'binding': binding,
                 'tasks': {t['id']: {'status': 'pending', 'attempts': []} for t in plan['tasks']}}
        if state['identity'] != identity:
            raise ValueError('Batch plan, inputs, candidate code or runtime changed; use a new batch')
        # Also bind native fingerprints to the actual requested worker settings.
        previous_threads = os.environ.get('QUANT_WORKER_THREADS')
        os.environ['QUANT_WORKER_THREADS'] = str(plan['worker_threads'])
        active = {}
        opened_streams = []
        cancelled = False
        previous_handlers = {}
        def cancel(signum, frame):
            nonlocal cancelled
            cancelled = True
        for sig in (signal.SIGINT, signal.SIGTERM):
            previous_handlers[sig] = signal.signal(sig, cancel)
        def save():
            state['updated_at'] = W.now()
            W.write(state_path, state)
        try:
            for t in plan['tasks']:
                entry = state['tasks'][t['id']]
                if entry['status'] == 'success':
                    if receipt(t) != entry['receipt']:
                        raise ValueError('Successful task artifact changed; refusing reuse')
                elif entry['status'] == 'running':
                    # A hard crash may leave descendants: do not assume they died.
                    old = entry['attempts'][-1]
                    try:
                        os.killpg(old['pid'], 0) if os.name == 'posix' else os.kill(old['pid'], 0)
                    except ProcessLookupError:
                        pass
                    else:
                        raise ValueError('Prior task PID is still present; establish termination before resuming')
                    old.update(status='interrupted', ended_at=W.now())
                    entry['status'] = 'pending'
                elif entry['status'] == 'launching':
                    # The start gate cannot open before a running PID is persisted.
                    entry['attempts'][-1].update(status='interrupted', ended_at=W.now())
                    entry['status'] = 'pending'
                elif entry['status'] in ('failed', 'cancelled', 'blocked', 'interrupted'):
                    entry['status'] = 'pending'
            save()
            while True:
                if cancelled:
                    for key, item in list(active.items()):
                        stop_process(item['process'])
                        entry = state['tasks'][key]
                        entry['status'] = 'cancelled'
                        entry['attempts'][-1].update(status='cancelled', ended_at=W.now(), returncode=item['process'].returncode)
                        item['stdout'].close(); item['stderr'].close()
                    active.clear()
                    for entry in state['tasks'].values():
                        if entry['status'] == 'pending': entry['status'] = 'cancelled'
                    state['status'] = 'cancelled'; save(); return 130
                for key, item in list(active.items()):
                    process = item['process']
                    observed_rss = group_rss_mb(process.pid)
                    if observed_rss is not None:
                        attempt = state['tasks'][key]['attempts'][-1]
                        attempt['peak_process_group_rss_mb'] = max(attempt.get('peak_process_group_rss_mb', 0), observed_rss)
                    timed_out = time.monotonic() - item['started'] > plan['timeout_seconds']
                    if timed_out:
                        stop_process(process)
                    code = process.poll()
                    if code is None:
                        continue
                    stop_process(process)  # also reap descendants after an exited CLI leader
                    item['stdout'].close(); item['stderr'].close()
                    entry = state['tasks'][key]; attempt = entry['attempts'][-1]
                    attempt.update(ended_at=W.now(), returncode=code)
                    try:
                        payload = W.read(item['stdout_path'])
                        if timed_out or code != 0 or not payload.get('ok'):
                            raise ValueError('Task timed out' if timed_out else 'CLI failed; inspect attempt logs')
                        current_runtime = {str(p.relative_to(W.SKILL)): W.digest(p) for p in sorted((W.SKILL / 'scripts').rglob('*.py'))}
                        if current_runtime != binding['runtime']:
                            raise ValueError('Runtime changed during task execution')
                        entry['receipt'] = receipt(item['task'])
                        entry['status'] = attempt['status'] = 'success'
                    except Exception as error:
                        entry['status'] = attempt['status'] = 'failed'
                        attempt['error'] = str(error)
                    del active[key]; save()
                busy = {item['task']['workspace'] for item in active.values()}
                memory = sum(item['memory'] for item in active.values())
                for t in plan['tasks']:
                    entry = state['tasks'][t['id']]
                    if entry['status'] != 'pending': continue
                    dependencies = [state['tasks'][x]['status'] for x in t['depends_on']]
                    if any(x in ('failed', 'blocked', 'cancelled') for x in dependencies):
                        entry['status'] = 'blocked'; save(); continue
                    if any(x != 'success' for x in dependencies): continue
                    if len(entry['attempts']) >= plan['max_attempts']:
                        entry['status'] = 'failed'; entry['error'] = 'Batch attempt budget exhausted'; save(); continue
                    needed = plan['prepare_memory_mb'] if t['command'] == 'prepare' else plan['worker_memory_mb']
                    if len(active) >= plan['max_workers'] or t['workspace'] in busy or memory + needed > plan['memory_budget_mb']: continue
                    observed_available = memory_limit_mb()
                    if needed > observed_available:
                        if not active:
                            entry['status'] = 'failed'; entry['error'] = 'Insufficient observed memory headroom before launch'; save()
                        continue
                    if (t['command'] == 'prepare' and active) or any(x['task']['command'] == 'prepare' for x in active.values()): continue
                    current_runtime = {str(p.relative_to(W.SKILL)): W.digest(p) for p in sorted((W.SKILL / 'scripts').rglob('*.py'))}
                    if current_runtime != binding['runtime']:
                        raise ValueError('Runtime changed during batch execution')
                    root = Path(t['workspace'])
                    if any((root / p).exists() for p in ('freeze.json', 'archive.json', 'supplementary/final-artifact-manifest.json')):
                        raise ValueError('Workspace was sealed during batch execution')
                    cmd = command_for(plan, t)
                    attempt_dir = output / t['id'] / f"attempt-{len(entry['attempts']) + 1}"
                    attempt_dir.mkdir(parents=True, exist_ok=False)
                    stdout_path = attempt_dir / 'stdout.json'; stderr_path = attempt_dir / 'stderr.log'
                    stdout = stdout_path.open('w'); stderr = stderr_path.open('w')
                    opened_streams.extend((stdout, stderr))
                    env = os.environ.copy()
                    env.update(QUANT_BATCH_PROCESS_GROUP='1', QUANT_BATCH_START_GATE='1',
                               OMP_NUM_THREADS=str(plan['worker_threads']), OPENBLAS_NUM_THREADS=str(plan['worker_threads']),
                               MKL_NUM_THREADS=str(plan['worker_threads']), NUMEXPR_NUM_THREADS=str(plan['worker_threads']))
                    attempt = {'status': 'launching', 'started_at': W.now(), 'command': cmd,
                               'available_memory_budget_mb_at_launch': observed_available, 'reserved_memory_mb': needed,
                               'stdout': str(stdout_path), 'stderr': str(stderr_path)}
                    entry['attempts'].append(attempt)
                    entry['status'] = 'launching'; save()
                    try:
                        process = subprocess.Popen(cmd, stdout=stdout, stderr=stderr, stdin=subprocess.PIPE,
                                                   env=env, start_new_session=os.name == 'posix')
                    except OSError as error:
                        stdout.close(); stderr.close()
                        entry['status'] = attempt['status'] = 'failed'
                        attempt.update(error=str(error), ended_at=W.now())
                        save(); continue
                    entry['status'] = attempt['status'] = 'running'
                    attempt['pid'] = process.pid
                    active[t['id']] = dict(process=process, task=t, stdout=stdout, stderr=stderr, stdout_path=stdout_path,
                                          started=time.monotonic(), memory=needed)
                    busy.add(t['workspace']); memory += needed; save()
                    process.stdin.write(b'GO\n'); process.stdin.flush(); process.stdin.close()
                if not active and all(x['status'] != 'pending' for x in state['tasks'].values()):
                    if cancelled:
                        state['status'] = 'cancelled'; save(); return 130
                    if bind_inputs(plan) != binding:
                        state['audit_error'] = 'Inputs changed during execution'; save()
                        raise ValueError(state['audit_error'])
                    if cancelled:
                        state['status'] = 'cancelled'; save(); return 130
                    success = all(x['status'] == 'success' for x in state['tasks'].values())
                    state['status'] = 'success' if success else 'failed'; save()
                    return 0 if success else 1
                time.sleep(.1)
        except BaseException as error:
            state['status'] = 'failed'
            state['error'] = {'type': type(error).__name__, 'message': str(error)}
            raise
        finally:
            interrupted = False
            for key, item in active.items():
                stop_process(item['process']); item['stdout'].close(); item['stderr'].close()
                entry = state['tasks'][key]
                entry['status'] = 'interrupted'
                entry['attempts'][-1].update(status='interrupted', ended_at=W.now(), returncode=item['process'].returncode)
                interrupted = True
            if interrupted or state.get('status') == 'failed':
                save()
            for stream in opened_streams:
                stream.close()
            for sig, handler in previous_handlers.items(): signal.signal(sig, handler)
            if previous_threads is None: os.environ.pop('QUANT_WORKER_THREADS', None)
            else: os.environ['QUANT_WORKER_THREADS'] = previous_threads


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args()
    try:
        previous = W.read(Path(args.output) / 'state.json')['plan'] if args.resume else None
        code = run(load_plan(args.plan, resolved_defaults=previous), args.output, args.resume)
        print(json.dumps({'ok': code == 0, 'state': str(Path(args.output).resolve() / 'state.json'), 'exit_code': code}))
        return code
    except Exception as error:
        print(json.dumps({'ok': False, 'error': {'type': type(error).__name__, 'message': str(error)}}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
