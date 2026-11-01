#!/usr/bin/env python3
"""Agent-neutral CLI. All model reasoning belongs to the calling agent."""
from __future__ import annotations
import argparse
import contextlib
import copy
import html
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import uuid
from quantlib import workspace as W


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--version', action='version', version='quant-research 1.5.1')
    p.add_argument('--config', help='Library configuration file (or QUANT_RESEARCH_CONFIG)')
    sub = p.add_subparsers(dest='command', required=True)
    sub.add_parser('doctor')
    sub.add_parser('defaults', help='Show default research years and portfolio settings')
    b = sub.add_parser('bootstrap')
    b.add_argument('--venv', help='Environment path; defaults to configured runtime_root/py311')
    b.add_argument('--extras', nargs='*', choices=['models', 'reports'], default=[])
    for cmd in ('init', 'prepare', 'check', 'evaluate', 'freeze', 'finalize', 'status', 'report'):
        s = sub.add_parser(cmd)
        s.add_argument('--workspace', required=True)
        if cmd == 'init':
            s.add_argument('--protocol', required=True)
            s.add_argument('--mode', choices=sorted(W.MODES))
        if cmd in ('check', 'evaluate'):
            s.add_argument('--candidate', required=True)
        if cmd == 'freeze':
            s.add_argument('--candidates', nargs='+', required=True)
    r = sub.add_parser('extract-report')
    r.add_argument('--input', required=True)
    r.add_argument('--output', required=True)
    c = sub.add_parser('config').add_subparsers(dest='action', required=True)
    ci = c.add_parser('init')
    for name in ('warehouse-root', 'research-root', 'runtime-root', 'factor-root', 'sources-root'):
        ci.add_argument('--' + name)
    c.add_parser('show')
    d = sub.add_parser('dataset').add_subparsers(dest='action', required=True)
    da = d.add_parser('add')
    for name in ('id', 'version', 'source', 'format'):
        da.add_argument('--' + name, required=True, **({'choices': ['csv', 'parquet', 'qlib']} if name == 'format' else {}))
    for name in ('universe', 'calendar', 'metadata'):
        da.add_argument('--' + name)
    d.add_parser('list')
    sources = sub.add_parser('source', help='Inspect installed market-data adapters').add_subparsers(dest='action', required=True)
    sources.add_parser('list')
    data = sub.add_parser('data', help='Download, validate and register real market-data snapshots').add_subparsers(dest='action', required=True)
    fetch = data.add_parser('fetch')
    fetch.add_argument('--source', default='baostock')
    fetch.add_argument('--id', required=True)
    fetch.add_argument('--version', required=True)
    fetch.add_argument('--start', default='2019-01-01')
    fetch.add_argument('--end', help='Inclusive exchange-local date; omitted means latest available completed session')
    fetch.add_argument('--instruments', nargs='+', help='Explicit source instrument codes; omitted means all supported historical stocks')
    fetch.add_argument('--resume', help='Resume an exact acquisition batch after verifying saved payloads')
    fetch.add_argument('--retries', type=int, default=2)
    fetch.add_argument('--timeout', type=float, default=30)
    fetch.add_argument('--delay', type=float, default=0.2)
    data.add_parser('status').add_argument('--batch', required=True)
    validate = data.add_parser('validate')
    validate.add_argument('--id', required=True)
    validate.add_argument('--version', required=True)
    combine = data.add_parser('combine', help='Combine compatible immutable versions with explicit source priority')
    combine.add_argument('--id', required=True)
    combine.add_argument('--version', required=True)
    combine.add_argument('--inputs', required=True, help='JSON list of {id, version}, highest priority first')
    combine.add_argument('--conflicts', choices=['reject', 'prefer-first'], default='reject')
    factors = sub.add_parser('factor').add_subparsers(dest='action', required=True)
    factors.add_parser('seed').add_argument('--validate', action='store_true')
    factors.add_parser('add').add_argument('--source', required=True)
    factors.add_parser('list')
    for command in ('show', 'validate'):
        action = factors.add_parser(command)
        action.add_argument('--id', required=True)
        action.add_argument('--version', required=True)
    studies = sub.add_parser('study').add_subparsers(dest='action', required=True)
    sn = studies.add_parser('new')
    for name in ('slug', 'dataset', 'version'):
        sn.add_argument('--' + name, required=True)
    sn.add_argument('--protocol', help='Explicit protocol; omit to use default years and 100,000 initial cash')
    sn.add_argument('--title')
    sn.add_argument('--mode', choices=sorted(W.MODES))
    historical = studies.add_parser('import')
    for name in ('source', 'slug', 'title'):
        historical.add_argument('--' + name, required=True)
    historical.add_argument('--mode', choices=sorted(W.MODES | {'unknown'}), default='unknown')
    historical.add_argument('--historical-status', default='unknown')
    for name in ('report', 'datasets', 'exclude', 'notes'):
        historical.add_argument('--' + name)
    studies.add_parser('verify').add_argument('--workspace', required=True)
    ix = sub.add_parser('index').add_subparsers(dest='action', required=True)
    ix.add_parser('refresh')
    ix.add_parser('show')
    return p


def doctor():
    packages = {}
    for name in ('pyqlib', 'numpy', 'pandas', 'pyarrow', 'scipy', 'scikit-learn', 'lightgbm', 'xgboost', 'filelock', 'torch', 'pypdf', 'baostock'):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    return {'python': sys.version.split()[0], 'executable': sys.executable,
            'python_supported': sys.version_info[:2] == (3, 11), 'uv': shutil.which('uv'),
            'packages': packages, 'core_ready': sys.version_info[:2] == (3, 11) and all(
                packages[n] for n in packages if n not in ('torch', 'pypdf', 'baostock')),
            'custom_models_ready': packages['torch'] is not None,
            'pdf_ready': packages['pypdf'] is not None,
            'market_data_ready': packages['baostock'] is not None}


def bootstrap(args):
    uv = shutil.which('uv')
    if not uv:
        raise ValueError('uv is required for locked bootstrap; install uv using its official instructions')
    if args.venv:
        venv = Path(args.venv).expanduser().resolve()
    else:
        from quantlib.library import load_config
        venv = Path(load_config(getattr(args, 'config', None))['runtime_root']) / 'py311'
    if venv.is_relative_to(W.SKILL):
        raise ValueError('Choose a runtime environment outside the skill directory')
    if venv.exists() and not (venv / '.quant-research-runtime').exists():
        raise ValueError('Refusing to alter an existing environment not created by this skill')
    env = os.environ.copy()
    env.pop('PYTHONPATH', None)
    env['UV_PROJECT_ENVIRONMENT'] = str(venv)
    command = [uv, 'sync', '--locked', '--no-dev', '--python', '3.11', '--project', str(W.SKILL)]
    for extra in args.extras:
        command += ['--extra', extra]
    result = subprocess.run(command, env=env, stdout=sys.stderr, stderr=sys.stderr)
    if result.returncode:
        raise RuntimeError('Locked environment installation failed')
    (venv / '.quant-research-runtime').write_text(W.digest(W.SKILL / 'uv.lock'))
    return {'venv': str(venv), 'python': str(venv / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')),
            'extras': args.extras}


def extract(args):
    source = Path(args.input).resolve()
    output = Path(args.output).resolve()
    if output.exists():
        raise ValueError('Report extraction output already exists')
    if source.suffix.lower() == '.pdf':
        from pypdf import PdfReader
        pages = [{'page': i + 1, 'text': page.extract_text() or ''} for i, page in enumerate(PdfReader(source).pages)]
    elif source.suffix.lower() in ('.md', '.txt'):
        pages = [{'page': 1, 'text': source.read_text(encoding='utf-8')}]
    else:
        raise ValueError('Supported report input: PDF, Markdown or plain text')
    if not any(p['text'].strip() for p in pages):
        raise ValueError('No readable text; use host OCR/vision and preserve page attribution')
    result = {'source_name': source.name, 'sha256': W.digest(source), 'pages': pages,
              'limitations': 'Extraction does not validate formulas; the agent must reconcile symbols and page references.'}
    W.write(output, result)
    return {'output': str(output), 'pages': len(pages), 'sha256': result['sha256']}


def prepared(root):
    stamp = W.read(root / 'prepared.json')
    if stamp['files'] != W.snapshot(root):
        raise ValueError('Prepared data changed; create a new study with the revised snapshot')


def valid_result(folder):
    run = W.read(folder / 'run.json')
    if run['status'] == 'complete':
        for path, digest in run['artifacts'].items():
            if W.digest(W.inside(folder, path)) != digest:
                raise ValueError('Saved result artifact changed: ' + path)
    return run


def run_worker(cmd, log_path, timeout):
    env = {k: v for k, v in os.environ.items() if k in ('PATH', 'HOME', 'TMPDIR', 'TEMP', 'SYSTEMROOT', 'LANG')}
    env.update(PYTHONNOUSERSITE='1', OMP_NUM_THREADS='4', OPENBLAS_NUM_THREADS='4',
               MLFLOW_DISABLE_AGENT_HINT='1', MLFLOW_ENABLE_SYSTEM_METRICS_LOGGING='false')
    with Path(log_path).open('w') as log:
        process = subprocess.Popen(cmd, env=env, stdout=log, stderr=log, start_new_session=os.name != 'nt')
        try:
            code = process.wait(timeout=timeout)
        except (subprocess.TimeoutExpired, KeyboardInterrupt):
            if os.name != 'nt':
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
            process.wait()
            raise RuntimeError('Worker timed out or was interrupted; attempt evidence preserved')
    if code:
        raise RuntimeError('Worker failed; see ' + str(log_path) + ': ' + Path(log_path).read_text(errors='replace')[-3500:])


def evaluate(root, config, candidate, phase):
    prepared(root)
    fingerprint = W.fingerprint(root, candidate, phase)
    folder = root / 'runs' / phase / candidate['id']
    previous = W.read(folder / 'run.json') if (folder / 'run.json').exists() else None
    if previous:
        if previous['input_hash'] != fingerprint:
            raise ValueError('Run inputs/runtime changed; cached research cannot be overwritten')
        if previous['status'] == 'complete':
            valid_result(folder)
            return {'cached': True, **W.read(folder / 'result.json')}
    attempt = (previous or {}).get('attempt', 0) + 1
    if attempt > 1 + config['budget']['max_repairs']:
        raise ValueError('Technical retry budget exhausted; prior failures are preserved')
    folder.mkdir(parents=True, exist_ok=True)
    output = folder / f'attempt-{attempt}'
    output.mkdir()
    run = {'status': 'running', 'candidate': candidate['id'], 'phase': phase,
           'attempt': attempt, 'input_hash': fingerprint, 'started_at': W.now()}
    W.write(folder / 'run.json', run)
    W.event(root, 'evaluation_started', **run)
    cmd = [sys.executable, str(W.SKILL / 'scripts' / 'evaluate_worker.py'), str(root), candidate['id'], phase, str(output)]
    try:
        run_worker(cmd, output / 'execution.log', config['budget']['timeout_seconds'])
        prepared(root)
        W.verify_candidate(root, candidate['id'])
        result = W.read(output / 'result.json')
        W.write(folder / 'result.json', result)
        run.update(status='complete', completed_at=W.now(), artifacts={
            str(p.relative_to(folder)): W.digest(p) for p in folder.rglob('*') if p.is_file() and p.name != 'run.json'})
        W.write(folder / 'run.json', run)
        W.event(root, 'evaluation_completed', candidate=candidate['id'], phase=phase, input_hash=fingerprint)
        return {'cached': False, **result}
    except BaseException as error:
        run.update(status='failed', completed_at=W.now(), error=str(error))
        W.write(folder / 'run.json', run)
        W.event(root, 'evaluation_failed', candidate=candidate['id'], phase=phase, error=str(error))
        raise


def status(root):
    W.load(root)
    return {'study': W.read(root / 'study.json'), 'prepared': (root / 'prepared.json').exists(),
            'freeze': W.read(root / 'freeze.json') if (root / 'freeze.json').exists() else None,
            'candidates': [W.verify_candidate(root, p.parent.name) for p in sorted((root / 'candidates').glob('*/candidate.json'))],
            'runs': [valid_result(p.parent) for p in sorted((root / 'runs').glob('*/*/run.json'))]}


def report(root):
    state = status(root)
    protocol = W.load(root)
    lines, rendered = [], []

    def heading(value, level=2):
        lines.extend(['#' * level + ' ' + value, ''])
        rendered.append(f'<h{level}>' + html.escape(value) + f'</h{level}>')

    def paragraph(value):
        value = str(value)
        lines.extend([value, ''])
        rendered.append('<p>' + html.escape(value) + '</p>')

    def table(headers, rows):
        rows = [[str(cell) for cell in row] for row in rows]
        lines.extend(['| ' + ' | '.join(headers) + ' |', '|' + '|'.join(['---'] * len(headers)) + '|'])
        lines.extend('| ' + ' | '.join(cell.replace('|', '/') for cell in row) + ' |' for row in rows)
        lines.append('')
        rendered.append('<table><thead><tr>' + ''.join('<th>' + html.escape(h) + '</th>' for h in headers) + '</tr></thead><tbody>'
                        + ''.join('<tr>' + ''.join('<td>' + html.escape(cell) + '</td>' for cell in row) + '</tr>' for row in rows)
                        + '</tbody></table>')

    def link(label, path):
        lines.extend(['[' + label + '](' + path + ')', ''])
        rendered.append('<p><a href="' + html.escape(path, quote=True) + '">' + html.escape(label) + '</a></p>')

    heading('Quantitative research report', 1)
    paragraph('Historical research; numerical checks do not establish investment validity.')
    if protocol.get('data', {}).get('synthetic'):
        paragraph('SYNTHETIC DATA — engineering execution only, not evidence of strategy performance.')
    paragraph('Mode: ' + state['study']['mode'])
    paragraph('Question: ' + protocol.get('objective', 'See candidate hypotheses.'))
    table(['Segment', 'Start', 'End'], [[key, *value] for key, value in protocol['splits'].items()])
    paragraph('Final results exposed: ' + str(state['study']['final_exposed']))
    for candidate in state['candidates']:
        heading(candidate['id'])
        paragraph(candidate['hypothesis'])
        if candidate.get('source'):
            paragraph('Source: ' + json.dumps(candidate['source'], ensure_ascii=False))
        for snapshot in candidate.get('registered_factors', []):
            heading('Factor: ' + snapshot['id'] + '@' + snapshot['version'], 3)
            paragraph('Pinned manifest SHA-256: ' + snapshot['manifest_hash'])
            paragraph('Library validation at registration: ' + snapshot['library_validation'].get('status', 'unvalidated'))
            for limitation in snapshot['limitations']:
                paragraph(limitation)
            link('Definition and original provenance', str(Path(snapshot['factor_file']).with_name('definition.json')))
            if snapshot.get('validation_receipt'):
                link('Pinned validation receipt', snapshot['validation_receipt'])
        for phase in ('discovery', 'final'):
            folder = root / 'runs' / phase / candidate['id']
            if (folder / 'run.json').exists():
                run = valid_result(folder)
                heading(phase, 3)
                paragraph('Status: ' + run['status'])
                if run['status'] == 'complete':
                    data = W.read(folder / 'result.json')
                    # Keep scopes separate: portfolio days and paired IC sample days differ.
                    scopes = {scope: data.get(scope, {}) for scope in ('signal', 'portfolio', 'equal_weight', 'increment')}
                    scopes.update({'baseline.' + scope: data.get('baseline', {}).get(scope, {}) for scope in ('signal', 'portfolio')})
                    scopes.update({'robustness.' + scope: metrics for scope, metrics in data.get('robustness', {}).items()})
                    table(['Scope', 'Metric', 'Value'], [[scope, key, value] for scope, metrics in scopes.items()
                                                       for key, value in metrics.items()])
                    link('Full numerical evidence: ' + candidate['id'] + '/' + phase,
                         str((folder / 'result.json').relative_to(root)))
                else:
                    paragraph('Failure: ' + run.get('error', 'Interrupted before completion'))
    if (root / 'data' / 'manifest.json').exists():
        manifest = W.read(root / 'data' / 'manifest.json')
        heading('Data provenance')
        paragraph('Snapshot: ' + manifest.get('dataset_id', ''))
        paragraph('Rows: ' + str(manifest.get('rows')) + '; instruments: ' + str(len(manifest.get('instruments', []))))
        for item in manifest.get('limitations', []):
            paragraph(item)
        link('Full data manifest', 'data/manifest.json')
        link('Frozen protocol', 'protocol.json')
    text = '\n'.join(lines)
    (root / 'report.md').write_text(text, encoding='utf-8')
    (root / 'report.html').write_text('<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Quant research</title>'
        '<style>body{max-width:1000px;margin:40px auto;padding:20px;font:16px/1.6 system-ui;overflow-wrap:anywhere}'
        'table{border-collapse:collapse;width:100%;font-size:14px}th,td{padding:8px;text-align:left;border-bottom:1px solid #ddd}'
        'th{background:#f4f5f7}h2{margin-top:40px}td:last-child{max-width:560px}</style>'
        + '\n'.join(rendered), encoding='utf-8')
    return {'markdown': str(root / 'report.md'), 'html': str(root / 'report.html'), 'candidate_count': len(state['candidates'])}


def managed_new(args, configuration):
    from quantlib import library, catalog, defaults
    registered = library.dataset_resolve(configuration, args.dataset, args.version)
    protocol = W.read(args.protocol) if args.protocol else defaults.protocol_for_dataset(registered)
    mode = args.mode or protocol.get('mode')
    spec = dict(protocol.get('data', {}))
    if any(spec.get(key) for key in ('universe', 'calendar')):
        raise ValueError('Register universe/calendar with the dataset; remove external paths from the managed protocol')
    for key in ('path', 'dataset_id', 'dataset_version', 'manifest_hash'):
        spec.pop(key, None)
    if spec.get('format') not in (None, registered['format']):
        raise ValueError('Protocol format differs from registered dataset format')
    for key in ('region', 'price_basis', 'volume_unit', 'synthetic', 'columns',
                'currency', 'frequency', 'adjustment_identity', 'adjustment_policy',
                'volume_basis', 'limitations', 'universe_scope', 'source', 'acquisition'):
        if key in registered['metadata']:
            if key in spec and spec[key] != registered['metadata'][key]:
                raise ValueError('Protocol interpretation conflicts with registered dataset: ' + key)
            spec[key] = registered['metadata'][key]
    spec.update(format=registered['format'], dataset_id=args.dataset, dataset_version=args.version,
                manifest_hash=registered['manifest_hash'])
    W.validate({**copy.deepcopy(protocol), 'mode': mode, 'data': spec})
    root, metadata = catalog.allocate(configuration, args.slug, mode, args.title or protocol.get('objective'))
    args.workspace = str(root)
    if args.protocol:
        result = W.initialize(root, args.protocol, mode, data_override=spec)
    else:
        # Keep the allocated study empty until initialize commits its protocol.
        # Only the materialized dates enter the frozen study; no temporary path does.
        with tempfile.TemporaryDirectory(prefix='quant-default-protocol-') as temporary:
            source = Path(temporary) / 'protocol.json'
            W.write(source, protocol)
            result = W.initialize(root, source, mode, data_override=spec)
    catalog.finish_registration(root, metadata)
    return {**result, 'id': metadata['id'], 'dataset': {'id': args.dataset, 'version': args.version}}


def resolve_data(config, config_path):
    """Resolve registered data only for preparation; never mutate the frozen protocol."""
    if not config['data'].get('dataset_id'):
        return config
    from quantlib import library
    resolved = copy.deepcopy(config)
    spec = resolved['data']
    registered = library.dataset_resolve(library.load_config(config_path), spec['dataset_id'],
                                         spec['dataset_version'], spec['manifest_hash'])
    if spec['format'] != registered['format']:
        raise ValueError('Dataset format differs from the frozen protocol')
    for key in ('path', 'universe', 'calendar'):
        if registered.get(key):
            spec[key] = registered[key]
    return resolved


def library_dispatch(args):
    from quantlib import library, catalog
    path = getattr(args, 'config', None)
    if args.command == 'study' and args.action == 'verify':
        from quantlib.history import verify_history
        return verify_history(args.workspace)
    if args.command == 'config':
        if args.action == 'init':
            return library.config_init(path, args.warehouse_root, args.research_root, args.runtime_root, args.factor_root, args.sources_root)
        return library.load_config(path)
    configuration = library.load_config(path)
    if args.command == 'data':
        from quantlib import ingestion
        if args.action == 'fetch':
            return ingestion.ingest(configuration, source=args.source, dataset_id=args.id, version=args.version,
                                    start=args.start, end=args.end, instruments=args.instruments, resume=args.resume,
                                    options={'retries': args.retries, 'timeout': args.timeout, 'delay': args.delay})
        if args.action == 'status':
            given = Path(args.batch).expanduser()
            relative = (given.resolve().relative_to(Path(configuration['sources_root']).resolve())
                        if given.is_absolute() and given.resolve().is_relative_to(Path(configuration['sources_root']).resolve())
                        else given)
            if relative.parts and relative.parts[0] == 'combined':
                from quantlib.composition import batch_status
                return batch_status(configuration, args.batch)
            return ingestion.batch_status(configuration, args.batch)
        if args.action == 'combine':
            from quantlib.composition import combine
            return combine(configuration, args.id, args.version, W.read(args.inputs), conflicts=args.conflicts)
        import pandas as pd
        registered = library.dataset_resolve(configuration, args.id, args.version)
        if registered['format'] not in ('csv', 'parquet') or not all(registered.get(k) for k in ('calendar', 'universe')):
            raise ValueError('Data validation requires CSV/Parquet with registered calendar and universe')
        frame = (pd.read_parquet(registered['path']) if registered['format'] == 'parquet'
                 else pd.read_csv(registered['path'], dtype={'instrument': str}))
        from quantlib.data import normalize
        frame = normalize(frame, registered['metadata'].get('columns'))
        quality = ingestion.validate_input(frame, Path(registered['calendar']).read_text().splitlines(),
                                           pd.read_csv(registered['universe'], dtype={'instrument': str}), registered['metadata'])
        return {'dataset_id': args.id, 'version': args.version, 'manifest_hash': registered['manifest_hash'], 'quality': quality}
    if args.command == 'factor':
        from quantlib import factor_registry as F
        if args.action == 'add':
            return F.add(configuration, args.source)
        if args.action == 'seed':
            result = F.seed(configuration)
            if args.validate:
                validations = []
                for definition_path in sorted((W.SKILL / 'assets/factor-library').glob('*/*/definition.json')):
                    entry = W.read(definition_path)
                    if entry['status'] == 'rejected':
                        continue
                    validations.append(F.validate(configuration, entry['factor_id'], entry['version']))
                return {'seed': result, 'validations': validations,
                        'validation_passed': all(v['status'] in ('passed', 'passed_with_limitations') for v in validations),
                        'index': F.refresh(configuration)}
            return result
        if args.action == 'list':
            return {'factors': F.list_factors(configuration), 'index': F.refresh(configuration)}
        if args.action == 'show':
            return F.resolve(configuration, args.id, args.version, require_runnable=False)
        return F.validate(configuration, args.id, args.version)
    if args.command == 'dataset':
        if args.action == 'add':
            metadata = W.read(args.metadata) if args.metadata else None
            return library.dataset_add(configuration, args.id, args.version, args.source, args.format,
                                       args.universe, args.calendar, metadata)
        return {'datasets': library.dataset_list(configuration)}
    if args.command == 'study':
        if args.action == 'import':
            from quantlib.history import import_history
            result = import_history(configuration, args.source, args.slug, args.title, args.mode,
                                    args.historical_status, args.report,
                                    W.read(args.datasets) if args.datasets else None,
                                    W.read(args.exclude) if args.exclude else None,
                                    W.read(args.notes) if args.notes else None)
            args.workspace = result['workspace']
            return result
        return managed_new(args, configuration)
    # Both forms rebuild so an index request cannot silently present a stale catalog.
    from quantlib import factor_registry as F
    return {**catalog.refresh(configuration), 'factor_library': F.refresh(configuration)}


def _dispatch(args):
    if args.command == 'defaults':
        from quantlib.defaults import policy
        return policy()
    if args.command == 'source':
        from quantlib.sources import list_sources
        return {'sources': list_sources()}
    if args.command in ('config', 'dataset', 'study', 'index', 'factor', 'data'):
        return library_dispatch(args)
    if args.command == 'doctor':
        return doctor()
    if args.command == 'bootstrap':
        return bootstrap(args)
    if args.command == 'extract-report':
        return extract(args)
    root = Path(args.workspace).expanduser().resolve()
    if root.is_relative_to(W.SKILL):
        raise ValueError('Research workspace must be outside the skill directory')
    if (root / 'archive.json').exists():
        from quantlib.history import read_archive
        historical = read_archive(root)
        if args.command == 'status':
            return {'workspace': str(root), 'id': historical['id'], 'status': 'archived',
                    'historical_status': historical['historical_status'], 'mode': historical['mode'],
                    'datasets': historical['datasets'], 'artifact_integrity': 'not_checked',
                    'verify_command': 'study verify --workspace ' + str(root)}
        if args.command == 'report':
            if not historical.get('report'):
                raise ValueError('No historical report was recorded; inspect original artifacts')
            report_path = W.inside(root, historical['report'])
            key = 'html' if report_path.suffix.lower() in ('.html', '.htm') else 'markdown'
            return {'status': 'archived', key: str(report_path), 'original_preserved': True}
        raise ValueError('Historical archives are read-only evidence; use study new for new research')
    if args.command == 'init':
        return W.initialize(root, args.protocol, args.mode)
    config = W.load(root)
    from filelock import FileLock
    with FileLock(str(root / '.study.lock'), timeout=0):
        if args.command == 'prepare':
            if (root / 'prepared.json').exists():
                prepared(root)
                return {'cached': True, **W.read(root / 'data' / 'manifest.json')}
            from quantlib.data import prepare
            result = prepare(root, resolve_data(config, getattr(args, 'config', None)))
            W.write(root / 'prepared.json', {'files': W.snapshot(root), 'prepared_at': W.now()})
            W.event(root, 'data_prepared')
            return result
        if args.command in ('check', 'evaluate'):
            prepared(root)
            candidate = W.register(root, args.candidate, library_config_path=getattr(args, 'config', None))
            if args.command == 'evaluate':
                return evaluate(root, config, candidate, 'discovery')
            out = root / 'candidates' / candidate['id'] / ('check-' + uuid.uuid4().hex[:8])
            out.mkdir()
            run_worker([sys.executable, str(W.SKILL / 'scripts/check_worker.py'), str(root), candidate['id'], str(out)],
                       out / 'execution.log', config['budget']['timeout_seconds'])
            result = W.read(out / 'result.json')
            W.write(root / 'candidates' / candidate['id'] / 'checks.json', result)
            return result
        if args.command == 'freeze':
            prepared(root)
            ids = sorted(set(args.candidates))
            fingerprints = {}
            for name in ids:
                candidate = W.verify_candidate(root, name)
                run = valid_result(root / 'runs' / 'discovery' / name)
                if run['status'] != 'complete':
                    raise ValueError('Only completed discovery candidates can be frozen')
                if run['input_hash'] != W.fingerprint(root, candidate, 'discovery'):
                    raise ValueError('Discovery inputs/runtime changed since evaluation')
                fingerprints[name] = candidate['candidate_hash']
            freeze = {'candidates': fingerprints, 'data': W.snapshot(root), 'protocol_hash': W.digest(root / 'protocol.json'),
                      'discovery_inputs': {name: W.fingerprint(root, W.verify_candidate(root, name), 'discovery') for name in ids}}
            if (root / 'freeze.json').exists():
                previous = W.read(root / 'freeze.json')
                if any(previous[k] != v for k, v in freeze.items()):
                    raise ValueError('Frozen selection cannot change')
                return previous
            freeze['frozen_at'] = W.now()
            W.write(root / 'freeze.json', freeze)
            study = W.read(root / 'study.json')
            study['freeze_hash'] = W.digest(root / 'freeze.json')
            W.write(root / 'study.json', study)
            W.event(root, 'candidates_frozen', candidates=ids)
            return freeze
        if args.command == 'finalize':
            prepared(root)
            freeze = W.read(root / 'freeze.json')
            study = W.read(root / 'study.json')
            if study.get('freeze_hash') != W.digest(root / 'freeze.json'):
                raise ValueError('Frozen selection manifest changed')
            if freeze['data'] != W.snapshot(root):
                raise ValueError('Frozen data changed')
            for name, expected in freeze['discovery_inputs'].items():
                if expected != W.fingerprint(root, W.verify_candidate(root, name), 'discovery'):
                    raise ValueError('Research implementation changed since freezing')
            study.update(final_exposed=True, final_exposed_at=study.get('final_exposed_at', W.now()))
            W.write(root / 'study.json', study)
            results = {}
            for name, digest in freeze['candidates'].items():
                candidate = W.verify_candidate(root, name)
                if candidate['candidate_hash'] != digest:
                    raise ValueError('Frozen candidate changed')
                results[name] = evaluate(root, config, candidate, 'final')
            return results
        if args.command == 'status':
            return status(root)
        if args.command == 'report':
            return report(root)
    raise ValueError('Unknown command')


def dispatch(args):
    try:
        return _dispatch(args)
    finally:
        # Index failure must not conceal a completed experiment or replace its error.
        if getattr(args, 'workspace', None):
            try:
                from quantlib import library, catalog
                path = library.config_path(getattr(args, 'config', None))
                if path.exists():
                    config = library.load_config(path)
                    if Path(args.workspace).expanduser().resolve().parent == Path(config['research_root']):
                        updated = catalog.refresh(config)
                        args.library_index = {key: updated[key] for key in ('index_json', 'index_markdown', 'count', 'errors')}
            except Exception as error:
                args.library_index = {'error': str(error), 'repair': 'Run index refresh with the correct --config'}
                print('Library index refresh failed: ' + str(error), file=sys.stderr)


def main():
    args = parser().parse_args()
    try:
        with contextlib.redirect_stdout(sys.stderr):
            result = dispatch(args)
        print(json.dumps({'ok': True, 'command': args.command, 'result': result,
                          **({'library_index': args.library_index} if hasattr(args, 'library_index') else {})},
                         ensure_ascii=False, allow_nan=False, default=str))
    except Exception as error:
        details = {'type': type(error).__name__, 'message': str(error)}
        for key in ('acquisition_batch', 'acquisition_batch_path'):
            if hasattr(error, key):
                details[key] = getattr(error, key)
        print(json.dumps({'ok': False, 'command': args.command, 'error': details,
                          **({'library_index': args.library_index} if hasattr(args, 'library_index') else {})}, ensure_ascii=False))
        sys.exit(1)


if __name__ == '__main__':
    main()
