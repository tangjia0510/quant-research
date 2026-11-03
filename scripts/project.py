#!/usr/bin/env python3
"""Portable research metadata and code. Does not execute or rewrite legacy studies."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile
import zipfile

SCHEMA = 1
ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$')
TOP = {'skill', 'research', 'registry', 'literature', 'data-catalog', 'environment'}
SKIP = {'work', 'runtime', '.git', '__pycache__', '.venv', 'node_modules', '.pytest_cache', '.mypy_cache', '.ruff_cache', '.tox'}
EXT = {'.py', '.md', '.json', '.jsonl', '.yaml', '.yml', '.toml', '.lock', '.txt', '.pdf', '.csv'}
MAX_FILE = 16 * 1024 * 1024
MAX_TOTAL = 64 * 1024 * 1024
SKILL_TOP = {'scripts', 'references', 'assets', 'agents', 'tests'}
SKILL_ROOT_FILES = {'SKILL.md', 'README.md', 'pyproject.toml', 'uv.lock'}

def skill_root(root):
    root = Path(root).resolve()
    ref = read(root / 'project.json').get('skill_source')
    if ref is None:
        return root / 'skill'
    if ref != '..' or root.name != 'project':
        raise ValueError('Only repository project/ may reference its parent Skill')
    parent = root.parent
    if not (parent / 'SKILL.md').is_file() or not (parent / 'scripts/project.py').is_file():
        raise ValueError('Repository Skill missing')
    return parent

def skill_files(source):
    source = Path(source)
    return sorted(p for p in source.rglob('*') if p.is_file() and not p.is_symlink() and not any(x in SKIP for x in p.relative_to(source).parts) and (p.relative_to(source).parts[0] in SKILL_TOP or p.relative_to(source).as_posix() in SKILL_ROOT_FILES) and p.suffix in EXT)



def read(p):
    return json.loads(Path(p).read_text(encoding='utf-8'))


def write(p, value):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    os.replace(tmp, p)


def digest(p):
    h = hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()


def relative(value):
    if not isinstance(value, str) or not value or '\\' in value:
        raise ValueError('Expected nonempty POSIX relative path')
    p = PurePosixPath(value)
    if p.is_absolute() or any(x in ('..', '.', '') for x in value.split('/')) or ':' in value:
        raise ValueError('Unsafe relative path: ' + value)
    return p


def inside(root, rel):
    p = Path(root) / str(relative(rel))
    root = Path(root).resolve()
    if not p.resolve().is_relative_to(root):
        raise ValueError('Path escapes root: ' + str(rel))
    return p


def check_id(value):
    if not isinstance(value, str) or not ID.fullmatch(value) or value.endswith('.'):
        raise ValueError('Invalid id: ' + str(value))
    return value


def check_hash(value):
    if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value):
        raise ValueError('Expected SHA256')


def init(root):
    root = Path(root)
    config = root / 'project.json'
    if config.exists():
        if read(config).get('schema_version') != SCHEMA:
            raise ValueError('Unsupported project schema')
        return {'existing': True, 'project': str(root)}
    root.mkdir(parents=True, exist_ok=True)
    for p in TOP | {'work'}:
        (root / p).mkdir(exist_ok=True)
    for p in ('factors', 'strategies'):
        (root / 'registry' / p).mkdir(exist_ok=True)
    write(config, {'schema_version': SCHEMA, 'layout': 'portable-research-v1',
                   'runtime_root': 'work', 'external_root_config': 'local-paths.json',
                   'research_format': 'JSON encoded YAML', 'raw_data_in_bundle': False})
    return {'existing': False, 'project': str(root)}


def portable_files(root):
    root = Path(root)
    files = []
    for p in root.rglob('*'):
        rel = p.relative_to(root)
        if any(x in SKIP for x in rel.parts):
            continue
        if rel.parts[0] not in TOP and rel.as_posix() not in ('project.json', 'README.md'):
            continue
        if p.is_symlink():
            raise ValueError('Portable content cannot contain symlinks: ' + str(rel))
        if not p.is_file():
            continue
        if p.suffix not in EXT or p.name in ('.env', 'local-paths.json'):
            raise ValueError('Nonportable file in asset tree: ' + str(rel))
        if p.stat().st_size > MAX_FILE:
            raise ValueError('Asset exceeds 16MiB; externalize it: ' + str(rel))
        # CSV is allowed only as small evidence, never a bulk dataset/ledger.
        if p.suffix == '.csv' and p.stat().st_size > 256 * 1024:
            raise ValueError('CSV exceeds evidence budget; externalize: ' + str(rel))
        files.append(p)
    if sum(p.stat().st_size for p in files) > MAX_TOTAL:
        raise ValueError('Portable project exceeds 64MiB budget')
    return sorted(files)


def catalog(root):
    result = {}
    for p in sorted((Path(root) / 'data-catalog').glob('*.json')):
        d = read(p)
        check_id(d['id'])
        if d.get('schema_version') != SCHEMA or d['id'] in result:
            raise ValueError('Duplicate or unsupported data reference: ' + d['id'])
        if not d.get('version'):
            raise ValueError('Data reference requires a fixed version')
        loc = d['locator']
        check_id(loc['root'])
        relative(loc['path'])
        if d.get('kind') not in ('file', 'directory'):
            raise ValueError('Data kind must be file or directory')
        if d.get('sha256') is not None:
            check_hash(d['sha256'])
            if d['kind'] != 'file':
                raise ValueError('Directory identity must use manifest, not file SHA')
        if d.get('manifest'):
            relative(d['manifest']['path'])
            check_hash(d['manifest']['sha256'])
        if not d.get('sha256') and not d.get('manifest') and not d.get('limitations'):
            raise ValueError('Unhashed reference needs explicit limitations')
        result[d['id']] = d
    return result


def validate(root):
    root = Path(root)
    if read(root / 'project.json').get('schema_version') != SCHEMA:
        raise ValueError('Unsupported project schema')
    refs = catalog(root)
    studies = []
    for folder in ((root / 'research').iterdir() if (root / 'research').exists() else []):
        if folder.name in SKIP:
            continue
        if folder.is_dir() and not (folder / 'research.yaml').is_file():
            raise ValueError('Research folder lacks research.yaml: ' + folder.name)
    for p in sorted((root / 'research').glob('*/research.yaml')):
        d = read(p)
        check_id(d['id'])
        if d['id'] != p.parent.name or d.get('schema_version') != SCHEMA:
            raise ValueError('Research id/schema mismatch: ' + str(p))
        if d.get('type') not in ('factor', 'strategy', 'diagnostic', 'mixed'):
            raise ValueError('Invalid research type')
        if d.get('status') not in ('draft', 'running', 'completed', 'rejected', 'inconclusive', 'archived'):
            raise ValueError('Invalid research status')
        if not d.get('title') or not isinstance(d.get('data_refs'), list):
            raise ValueError('Research title/data_refs required')
        if any(x not in refs for x in d['data_refs']):
            raise ValueError('Unresolved catalog reference in ' + d['id'])
        if d.get('entrypoint'):
            ep = inside(p.parent, d['entrypoint'])
            if not str(relative(d['entrypoint'])).startswith('src/') or not ep.is_file():
                raise ValueError('Entrypoint must be an existing src/ file')
        if d.get('legacy_ref'):
            check_id(d['legacy_ref']['root'])
            relative(d['legacy_ref']['path'])
        if not (p.parent / 'conclusion.md').is_file():
            raise ValueError('Missing conclusion.md: ' + d['id'])
        studies.append(d)
    for group in ('factors', 'strategies'):
        for p in (root / 'registry' / group).glob('*/asset.json'):
            d = read(p)
            if d.get('status') not in ('admitted', 'retired') or not d.get('version'):
                raise ValueError('Registry is only versioned admitted/retired evidence')
            if not d.get('research_ids') or any(x not in {s['id'] for s in studies} for x in d['research_ids']):
                raise ValueError('Registry research evidence missing')
            if not d.get('admission') or not d.get('limitations'):
                raise ValueError('Registry requires explicit admission and limitations')
    sm = root / 'environment' / 'skill-snapshot.json'
    if sm.exists():
        rows = read(sm)['files']
        expected = {row['path'] for row in rows}
        source = skill_root(root)
        actual = {p.relative_to(source).as_posix() for p in (skill_files(source) if read(root / 'project.json').get('skill_source') else source.rglob('*')) if p.is_file() and not any(x in SKIP for x in p.relative_to(source).parts)}
        if expected != actual or len(expected) != len(rows):
            raise ValueError('Skill snapshot file membership drift')
        for row in rows:
            p = inside(source, row['path'])
            if not p.is_file() or digest(p) != row['sha256']:
                raise ValueError('Skill snapshot drift: ' + row['path'])
    files = portable_files(root)
    return {'valid': True, 'research_count': len(studies), 'data_reference_count': len(refs),
            'portable_files': len(files), 'portable_bytes': sum(p.stat().st_size for p in files),
            'external_inputs_verified': False, 'studies': studies}


def resolve(root, ref_id):
    root = Path(root)
    d = catalog(root)[ref_id]
    bindings = read(root / 'local-paths.json') if (root / 'local-paths.json').exists() else {}
    name = d['locator']['root']
    if name not in bindings:
        raise ValueError('Unbound external root: ' + name + '; configure local-paths.json, never edit frozen identities')
    base = Path(bindings[name])
    if not base.is_absolute():
        base = root / base
    target = inside(base, d['locator']['path'])
    if not target.exists():
        raise ValueError('Missing external input: ' + str(target))
    if (d['kind'] == 'file') != target.is_file():
        raise ValueError('External input kind mismatch')
    if d.get('sha256') and digest(target) != d['sha256']:
        raise ValueError('External input SHA mismatch')
    if d.get('manifest'):
        p = inside(target, d['manifest']['path'])
        if digest(p) != d['manifest']['sha256']:
            raise ValueError('External manifest SHA mismatch')
    return {'id': ref_id, 'path': str(target.resolve()), 'identity_verified': bool(d.get('sha256') or d.get('manifest')),
            'directory_payload_verified': False}


def snapshot(root, skill):
    root, skill = Path(root), Path(skill)
    if skill.resolve() == (root / 'skill').resolve() or (root / 'skill').resolve().is_relative_to(skill.resolve()):
        raise ValueError('Snapshot source must be independent of destination')
    source = []
    for p in skill.rglob('*'):
        rel = p.relative_to(skill)
        if any(x in SKIP for x in rel.parts) or p.is_symlink() or not p.is_file():
            continue
        if p.suffix in EXT and p.stat().st_size <= MAX_FILE:
            source.append(p)
    rows = [{'path': p.relative_to(skill).as_posix(), 'sha256': digest(p)} for p in sorted(source)]
    dst = root / 'skill'
    existing = {p.relative_to(dst).as_posix() for p in dst.rglob('*') if p.is_file() and not any(x in SKIP for x in p.relative_to(dst).parts)}
    wanted = {x['path'] for x in rows}
    if existing - wanted:
        raise ValueError('Snapshot contains extra files; review explicitly, do not silently delete')
    for p in source:
        target = dst / p.relative_to(skill)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(p, target)
    # Included as portable environment identity, not excluded local absolute source path.
    write(root / 'environment' / 'skill-snapshot.json', {'schema_version': SCHEMA, 'mode': 'controlled-copy', 'files': rows})
    return {'snapshot_files': len(rows)}


def export(root, output, dry_run=False):
    info = validate(root)
    root = Path(root)
    if read(root / 'project.json').get('skill_source') is not None:
        with tempfile.TemporaryDirectory() as td:
            staged = Path(td) / 'portable'
            staged.mkdir()
            for original in portable_files(root):
                target = staged / original.relative_to(root)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(original, target)
            config = read(staged / 'project.json')
            config.pop('skill_source', None)
            write(staged / 'project.json', config)
            for original in skill_files(skill_root(root)):
                target = staged / 'skill' / original.relative_to(skill_root(root))
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(original, target)
            return export(staged, output, dry_run)
    files = portable_files(root)
    manifest = {'schema_version': SCHEMA, 'files': [{'path': p.relative_to(root).as_posix(), 'size': p.stat().st_size, 'sha256': digest(p)} for p in files]}
    if dry_run:
        return {'dry_run': True, **{k: v for k, v in info.items() if k != 'studies'}, 'manifest': manifest}
    out = Path(output)
    if out.exists():
        raise ValueError('Refusing to overwrite bundle')
    if out.resolve().is_relative_to(root.resolve()):
        raise ValueError('Bundle output must be outside project')
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, 'x', zipfile.ZIP_DEFLATED) as z:
        for p in files:
            z.write(p, p.relative_to(root).as_posix())
        z.writestr('PORTABLE_MANIFEST.json', json.dumps(manifest, ensure_ascii=False, indent=2))
    return {'bundle': str(out), 'sha256': digest(out), 'files': len(files), 'bytes': out.stat().st_size}


def import_bundle(source, dest):
    dest = Path(dest)
    if dest.exists():
        raise ValueError('Destination exists; import never overwrites research')
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=dest.parent) as td:
        temp = Path(td) / 'project'
        temp.mkdir()
        with zipfile.ZipFile(source) as z:
            members = z.infolist()
            names = [m.filename for m in members]
            if len(names) != len(set(names)) or sum(m.file_size for m in members) > MAX_TOTAL + MAX_FILE:
                raise ValueError('Duplicate members or oversized archive')
            for m in members:
                relative(m.filename)
                mode = (m.external_attr >> 16) & 0o170000
                if m.is_dir() or mode not in (0, 0o100000) or m.file_size > MAX_FILE:
                    raise ValueError('Oversized or symlink archive member')
            manifest = json.loads(z.read('PORTABLE_MANIFEST.json'))
            expected = {r['path']: r for r in manifest['files']}
            if len(expected) != len(manifest['files']) or set(names) != set(expected) | {'PORTABLE_MANIFEST.json'}:
                raise ValueError('Archive manifest membership mismatch')
            for name, row in expected.items():
                data = z.read(name)
                if len(data) != row['size'] or hashlib.sha256(data).hexdigest() != row['sha256']:
                    raise ValueError('Archive SHA/size mismatch')
                target = inside(temp, name)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
        allowed = {p.relative_to(temp).as_posix() for p in portable_files(temp)}
        if allowed != set(expected):
            raise ValueError('Archive contains local/nonportable files')
        validate(temp)
        shutil.move(str(temp), str(dest))
    return {'imported': str(dest), 'external_inputs_verified': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True)
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('init', 'validate', 'index'):
        sub.add_parser(name)
    p = sub.add_parser('resolve'); p.add_argument('--id', required=True)
    p = sub.add_parser('snapshot-skill'); p.add_argument('--source', required=True)
    p = sub.add_parser('export'); p.add_argument('--output', required=True); p.add_argument('--dry-run', action='store_true')
    p = sub.add_parser('import'); p.add_argument('--source', required=True)
    p = sub.add_parser('new'); p.add_argument('--id', required=True); p.add_argument('--title', required=True); p.add_argument('--type', required=True, choices=['factor','strategy','diagnostic','mixed'])
    args = parser.parse_args()
    root = Path(args.project)
    try:
        if args.command == 'init': result = init(root)
        elif args.command == 'validate': result = validate(root)
        elif args.command == 'resolve': result = resolve(root, args.id)
        elif args.command == 'snapshot-skill': result = snapshot(root, args.source)
        elif args.command == 'export': result = export(root, args.output, args.dry_run)
        elif args.command == 'import': result = import_bundle(args.source, root)
        elif args.command == 'index':
            result = validate(root)
            write(root / 'work' / 'index.json', result)
        elif args.command == 'new':
            check_id(args.id)
            target = root / 'research' / args.id
            if target.exists(): raise ValueError('Research exists; preserve it')
            (target / 'src').mkdir(parents=True)
            result = {'schema_version':1,'id':args.id,'title':args.title,'type':args.type,'status':'draft','data_refs':[],'entrypoint':None}
            write(target / 'research.yaml', result)
            (target / 'conclusion.md').write_text('# Pending research\nNo measured conclusion yet.\n')
    except (ValueError, KeyError, OSError, zipfile.BadZipFile) as exc:
        parser.exit(2, 'ERROR: ' + str(exc) + '\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__': main()
