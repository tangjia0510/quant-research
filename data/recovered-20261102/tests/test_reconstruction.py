"""Offline checks only. All inserted observations below are synthetic fixtures."""
import ast
import hashlib
import json
from pathlib import Path
import sqlite3
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ReconstructionTests(unittest.TestCase):
    def database(self, filename):
        db = sqlite3.connect(':memory:')
        self.addCleanup(db.close)
        db.executescript((ROOT / 'schema' / filename).read_text())
        return db

    def test_public_copies_match_current_sha256(self):
        manifest = json.loads((ROOT / 'provenance/source_inventory.json').read_text())
        self.assertFalse(manifest['original_20261105_recovered'])
        for entry in manifest['files']:
            p = ROOT / entry['path']
            with self.subTest(path=entry['path']):
                self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(), entry['sha256'])
                self.assertEqual(p.stat().st_size, entry['bytes'])

    def test_all_preserved_python_parses_without_execution(self):
        paths = sorted((ROOT / 'original').rglob('*.py'))
        self.assertEqual(len(paths), 129)
        for path in paths:
            with self.subTest(path=str(path.relative_to(ROOT))):
                ast.parse(path.read_text(), filename=str(path))

    def test_original_sql_matches_code_constant(self):
        tree = ast.parse((ROOT / 'original/legacy-price-limits-20261031/build_limits_lookup.py').read_text())
        sql = next(n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value.startswith('CREATE TABLE daily_limits'))
        ddl = (ROOT / 'schema/001_daily_limits_original_20261031.sql').read_text()
        statements = '\n'.join(line for line in ddl.splitlines() if not line.startswith('--')).strip()
        self.assertEqual(statements, sql + ';')

    def test_original_primary_key_and_null_contract(self):
        db = self.database('001_daily_limits_original_20261031.sql')
        db.execute('INSERT INTO daily_limits VALUES (?,?,?,?,?)', ('SYNTHETIC', '2000-01-03', 11.0, 9.0, 'source_reported_numeric'))
        with self.assertRaises(sqlite3.IntegrityError):
            db.execute('INSERT INTO daily_limits VALUES (?,?,?,?,?)', ('SYNTHETIC', '2000-01-03', 11.0, 9.0, 'source_reported_numeric'))
        with self.assertRaises(sqlite3.IntegrityError):
            db.execute('INSERT INTO daily_limits VALUES (?,?,?,?,?)', (None, '2000-01-04', None, None, 'unknown'))
        self.assertIn('WITHOUT ROWID', db.execute("SELECT sql FROM sqlite_master WHERE name='daily_limits'").fetchone()[0])

    def test_original_nullable_limit_values_are_preserved(self):
        db = self.database('001_daily_limits_original_20261031.sql')
        db.execute('INSERT INTO daily_limits VALUES (?,?,?,?,?)', ('SYNTHETIC', '2000-01-03', None, None, 'unknown'))
        self.assertEqual(db.execute('SELECT upper_limit,lower_limit FROM daily_limits').fetchone(), (None, None))

    def test_tencent_columns_exactly_match_original_fields(self):
        tree = ast.parse((ROOT / 'original/a-share-data-lake/market/scripts/acquire_tencent_daily.py').read_text())
        fields = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'FIELDS' for t in n.targets))
        db = self.database('002_source_prices_RECONSTRUCTED.sql')
        actual = [row[1] for row in db.execute('PRAGMA table_info(tencent_daily_unadjusted)')]
        self.assertEqual(actual, fields)

    def test_hf_columns_exactly_match_original_projection(self):
        tree = ast.parse((ROOT / 'original/a-share-data-lake/market/scripts/normalize_hf_prices.py').read_text())
        table = next(n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name) and n.func.value.id == 'pa' and n.func.attr == 'table')
        fields = [ast.literal_eval(key) for key in table.args[0].keys]
        db = self.database('002_source_prices_RECONSTRUCTED.sql')
        actual = [row[1] for row in db.execute('PRAGMA table_info(hf_daily_unadjusted)')]
        self.assertEqual(actual, fields)

    def test_reconstruction_keeps_sources_separate(self):
        db = self.database('002_source_prices_RECONSTRUCTED.sql')
        db.execute('INSERT INTO tencent_daily_unadjusted(date,instrument,close) VALUES (?,?,?)', ('2000-01-03', 'SYNTHETIC', 1.0))
        db.execute('INSERT INTO hf_daily_unadjusted(date,instrument,close) VALUES (?,?,?)', ('2000-01-03', 'SYNTHETIC', 2.0))
        self.assertEqual(db.execute('SELECT close FROM tencent_daily_unadjusted').fetchone()[0], 1.0)
        self.assertEqual(db.execute('SELECT close FROM hf_daily_unadjusted').fetchone()[0], 2.0)

    def test_reconstruction_does_not_invent_uniqueness(self):
        db = self.database('002_source_prices_RECONSTRUCTED.sql')
        for _ in range(2):
            db.execute('INSERT INTO hf_daily_unadjusted(date,instrument,close) VALUES (?,?,?)', ('2000-01-03', 'SYNTHETIC', 1.0))
        self.assertEqual(db.execute('SELECT COUNT(*) FROM hf_daily_unadjusted').fetchone()[0], 2)

    def test_no_payload_or_runtime_files_in_publish_set(self):
        allowed = {'.py', '.md', '.json', '.sql', '.txt'}
        for p in ROOT.rglob('*'):
            if not p.is_file() or '__pycache__' in p.parts:
                continue
            with self.subTest(path=str(p.relative_to(ROOT))):
                self.assertFalse(p.is_symlink())
                self.assertTrue(p.name == '.gitignore' or p.suffix in allowed)
                self.assertLess(p.stat().st_size, 256 * 1024)


if __name__ == '__main__':
    unittest.main()
