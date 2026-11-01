"""Workspace invariants tested without model or market-data assumptions."""
import json
import argparse
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from quantlib import workspace as W
from quant import extract


class WorkspaceContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / 'study'
        self.protocol = self.base / 'protocol.json'
        self.config = {'schema_version': 1, 'mode': 'factor', 'data': {'path': 'input.csv', 'format': 'csv'},
                       'splits': {'train': ['2020-01-01', '2020-03-31'], 'valid': ['2020-04-01', '2020-04-30'],
                                  'discovery': ['2020-05-01', '2020-05-31'], 'final': ['2020-06-01', '2020-06-30']}}
        self.protocol.write_text(json.dumps(self.config))
        W.initialize(self.root, self.protocol)
        (self.root / 'factor.py').write_text('def compute(frame, params):\n    return frame[["close"]]\n')

    def candidate(self, **updates):
        value = {'id': 'candidate1', 'kind': 'factor', 'hypothesis': 'A declared test', 'factor_file': 'factor.py'}
        value.update(updates)
        path = self.root / 'input.json'
        path.write_text(json.dumps(value))
        return path

    def test_reinit_preserves_existing_research(self):
        with self.assertRaises(ValueError):
            W.initialize(self.root, self.protocol)
        self.assertTrue((self.root / 'study.json').exists())

    def test_protocol_mutation_is_rejected(self):
        p = self.root / 'protocol.json'
        value = W.read(p)
        value['label']['horizon'] = 20
        W.write(p, value)
        with self.assertRaises(ValueError):
            W.load(self.root)

    def test_candidate_snapshot_survives_source_change_but_reregistration_rejects(self):
        candidate_path = self.candidate()
        original = W.register(self.root, candidate_path)
        (self.root / 'factor.py').write_text('def compute(frame, params):\n    return frame[["volume"]]\n')
        self.assertEqual(W.verify_candidate(self.root, 'candidate1')['candidate_hash'], original['candidate_hash'])
        with self.assertRaises(ValueError):
            W.register(self.root, candidate_path)

    def test_candidate_snapshot_mutation_is_rejected(self):
        original = W.register(self.root, self.candidate())
        (self.root / original['factor_file']).write_text('changed')
        with self.assertRaises(ValueError):
            W.verify_candidate(self.root, 'candidate1')

    def test_factor_path_cannot_escape_workspace(self):
        (self.base / 'outside.py').write_text('x=1')
        with self.assertRaises(ValueError):
            W.register(self.root, self.candidate(factor_file='../outside.py'))

    def test_report_source_required(self):
        report_root = self.base / 'report'
        W.initialize(report_root, self.protocol, mode='report')
        (report_root / 'factor.py').write_text('x=1')
        path = report_root / 'candidate.json'
        path.write_text(json.dumps({'id': 'report1', 'kind': 'report', 'hypothesis': 'Reproduce formula', 'factor_file': 'factor.py'}))
        with self.assertRaises(ValueError):
            W.register(report_root, path)
        self.assertFalse((report_root / 'candidates/report1').exists())

    def test_candidate_budget_counts_registered_attempts(self):
        config = dict(self.config)
        config['budget'] = {'max_trials': 1}
        self.protocol.write_text(json.dumps(config))
        limited = self.base / 'limited'
        W.initialize(limited, self.protocol)
        (limited / 'factor.py').write_text('x=1')
        p = limited / 'candidate.json'
        for name in ('one', 'two'):
            p.write_text(json.dumps({'id': name, 'kind': 'factor', 'hypothesis': 'Budget test', 'factor_file': 'factor.py'}))
            if name == 'one':
                W.register(limited, p)
            else:
                with self.assertRaises(ValueError):
                    W.register(limited, p)

    def test_report_extraction_preserves_source_hash_and_does_not_overwrite(self):
        source = self.base / 'report.md'
        source.write_text('Formula: close[t] / close[t-5] - 1.\n')
        output = self.base / 'extracted.json'
        args = argparse.Namespace(input=str(source), output=str(output))
        result = extract(args)
        self.assertEqual(result['sha256'], W.digest(source))
        self.assertEqual(W.read(output)['pages'][0]['text'], source.read_text())
        with self.assertRaises(ValueError):
            extract(args)

    def test_empty_pdf_is_not_successful_formula_extraction(self):
        try:
            from pypdf import PdfWriter
        except ImportError:
            self.skipTest('reports extra not installed')
        source = self.base / 'blank.pdf'
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        with source.open('wb') as stream:
            writer.write(stream)
        output = self.base / 'blank-extracted.json'
        with self.assertRaises(ValueError):
            extract(argparse.Namespace(input=str(source), output=str(output)))
        self.assertFalse(output.exists())

    def test_pdf_extraction_retains_page_locator_and_formula(self):
        try:
            from pypdf import PdfWriter
            from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
        except ImportError:
            self.skipTest('reports extra not installed')
        source = self.base / 'formula.pdf'
        writer = PdfWriter()
        page = writer.add_blank_page(width=612, height=792)
        font = DictionaryObject({NameObject('/Type'): NameObject('/Font'),
                                 NameObject('/Subtype'): NameObject('/Type1'),
                                 NameObject('/BaseFont'): NameObject('/Helvetica')})
        page[NameObject('/Resources')] = DictionaryObject({
            NameObject('/Font'): DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
        stream = DecodedStreamObject()
        stream.set_data(b'BT /F1 12 Tf 72 720 Td (Factor = close[t] / close[t-5] - 1) Tj ET')
        page[NameObject('/Contents')] = writer._add_object(stream)
        with source.open('wb') as output:
            writer.write(output)
        target = self.base / 'formula-extracted.json'
        result = extract(argparse.Namespace(input=str(source), output=str(target)))
        self.assertEqual(result['pages'], 1)
        self.assertEqual(result['sha256'], W.digest(source))
        extracted = W.read(target)
        self.assertEqual(extracted['pages'][0]['page'], 1)
        self.assertIn('Factor = close[t] / close[t-5] - 1', extracted['pages'][0]['text'])

    def test_overlapping_protocol_splits_rejected(self):
        config = json.loads(json.dumps(self.config))
        config['splits']['valid'][0] = config['splits']['train'][1]
        with self.assertRaises(ValueError):
            W.validate(config)


if __name__ == '__main__':
    unittest.main()
