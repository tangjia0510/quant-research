import json
from pathlib import Path
import pytest
from quantlib import workspace as W


@pytest.fixture
def study(tmp_path):
    config = {'mode': 'factor', 'data': {'format': 'csv', 'path': 'bars.csv'},
              'splits': {'train': ['2020-01-01', '2020-03-31'], 'valid': ['2020-04-01', '2020-05-31'],
                         'discovery': ['2020-06-01', '2020-07-31'], 'final': ['2020-08-01', '2020-12-31']}}
    protocol = tmp_path / 'input.json'
    W.write(protocol, config)
    root = tmp_path / 'study'
    W.initialize(root, protocol)
    (root / 'factor.py').write_text('def compute(frame, params):\n    return frame.close\n')
    candidate = root / 'candidate.json'
    W.write(candidate, {'id': 'v1', 'kind': 'factor', 'hypothesis': 'Test momentum', 'factor_file': 'factor.py'})
    return root, candidate


def test_protocol_tamper(study):
    root, _ = study
    config = W.read(root / 'protocol.json')
    config['label']['horizon'] = 1
    W.write(root / 'protocol.json', config)
    with pytest.raises(ValueError, match='protocol changed'):
        W.load(root)


def test_candidate_is_immutable(study):
    root, path = study
    first = W.register(root, path)
    assert W.register(root, path) == first
    (root / 'factor.py').write_text('def compute(frame, params):\n    return frame.open\n')
    with pytest.raises(ValueError, match='immutable'):
        W.register(root, path)


def test_snapshot_code_tamper(study):
    root, path = study
    W.register(root, path)
    (root / 'candidates/v1/factor.py').write_text('altered')
    with pytest.raises(ValueError, match='changed'):
        W.verify_candidate(root, 'v1')


def test_no_path_escape(study):
    root, path = study
    c = W.read(path)
    c['factor_file'] = '../input.json'
    W.write(path, c)
    with pytest.raises(ValueError, match='inside'):
        W.register(root, path)


def test_no_new_candidate_after_freeze(study):
    root, path = study
    W.write(root / 'freeze.json', {})
    with pytest.raises(ValueError, match='frozen'):
        W.register(root, path)


def test_init_preserves_existing_files(study):
    root, path = study
    before = path.read_bytes()
    with pytest.raises(ValueError, match='empty'):
        W.initialize(root, root / 'protocol.json')
    assert path.read_bytes() == before


def test_overlapping_splits_rejected():
    with pytest.raises(ValueError, match='disjoint'):
        W.validate({'mode': 'model', 'data': {'format': 'csv'}, 'splits': {
            'train': ['2020-01-01', '2020-03-01'], 'valid': ['2020-02-01', '2020-04-01']}})


def test_report_keeps_portfolio_days_and_paired_sample_days(study):
    from quant import report
    root, path = study
    W.register(root, path)
    folder = root / 'runs/discovery/v1'
    W.write(folder / 'result.json', {'signal': {'ic_days': 74},
                                    'portfolio': {'days': 79}, 'increment': {'days': 74}})
    W.write(folder / 'run.json', {'status': 'complete',
                                 'artifacts': {'result.json': W.digest(folder / 'result.json')}})
    report(root)
    markdown = (root / 'report.md').read_text()
    rendered = (root / 'report.html').read_text()
    assert '| portfolio | days | 79 |' in markdown
    assert '| increment | days | 74 |' in markdown
    assert '<td>portfolio</td><td>days</td><td>79</td>' in rendered
    assert '<td>increment</td><td>days</td><td>74</td>' in rendered
    assert 'href="runs/discovery/v1/result.json"' in rendered
