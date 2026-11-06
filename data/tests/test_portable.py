"""Offline synthetic fixtures only. No supplier network requests or real data."""
import csv
import datetime as dt
import json
from pathlib import Path
import sys
import tempfile
import unittest
import urllib.error
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import duckdb
from portable.warehouse import initialize, ingest, fetch_series, metadata
from portable.fetch_tencent import parse_rows, download, AccessRestricted
from portable.normalize_hf import normalize
from portable.paths import output_path, FIN_DATA

KNOWN = '2020-01-10T00:00:00Z'
ASOF = '2020-01-11T00:00:00Z'


class PortableTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = duckdb.connect(':memory:')
        self.addCleanup(self.db.close)
        initialize(self.db)
        self.calendar = self.load('calendar', ['exchange','date','is_open'],
            [['SSE','2020-01-03','1'],['SSE','2020-01-04','0'],['SSE','2020-01-05','0'],['SSE','2020-01-06','1']])
        self.master = self.load('instruments', ['instrument','exchange','listed_on','delisted_on'],
            [['sh600001','SSE','1999-01-01','']])

    def meta(self, source='test', revision='synthetic-v1', known=KNOWN):
        return {'source':source,'source_revision':revision,'retrieved_at':known,
                'volume_unit':'shares','amount_unit':'CNY','price_basis':'unadjusted'}

    def load(self, kind, columns, rows, meta=None):
        path = self.root/(kind+str(len(list(self.root.iterdir())))+'.csv')
        with path.open('w', newline='') as file:
            writer = csv.writer(file);writer.writerow(columns);writer.writerows(rows)
        return ingest(self.db,kind,path,meta or self.meta())['batch_id']

    def prices(self, source='primary', dates=('2020-01-03','2020-01-06'), value=10, known=KNOWN):
        return self.load('prices', ['instrument','date','open','high','low','close','volume_shares','amount_cny'],
            [['sh600001',date,value,value,value,value,100,value*100] for date in dates],self.meta(source,known=known))

    def query(self, **kwargs):
        args = dict(code='sh600001',start='2020-01-03',end='2020-01-06',calendar_batch=self.calendar,
                    instruments_batch=self.master,sources=['primary','secondary'],as_of=ASOF)
        args.update(kwargs)
        return fetch_series(self.db,**args)

    def test_output_path_stays_under_fin_data(self):
        self.assertEqual(output_path(FIN_DATA/'test.duckdb'),(FIN_DATA/'test.duckdb').resolve())
        with self.assertRaisesRegex(ValueError,'fin_data'):
            output_path(FIN_DATA/'..'/'data'/'bad.duckdb')

    def test_output_path_rejects_symlink_escape(self):
        from portable import paths
        folder = self.root/'fin_data'
        folder.mkdir()
        (folder/'escape').symlink_to(self.root, target_is_directory=True)
        with patch.object(paths,'FIN_DATA',folder), self.assertRaises(ValueError):
            paths.output_path(folder/'escape'/'outside.duckdb')

    def test_unknown_schema_version_rejected_before_rewrite(self):
        self.db.execute('UPDATE schema_version SET version=2')
        with self.assertRaisesRegex(ValueError,'no changes'):
            initialize(self.db)
        self.assertEqual(self.db.execute('SELECT version FROM schema_version').fetchone()[0],2)

    def test_future_or_partial_daily_price_rejected(self):
        with self.assertRaisesRegex(ValueError,'completed prior'):
            self.prices(dates=('2020-01-10',))

    def test_public_source_tree_excludes_environment_paths_and_payloads(self):
        root = Path(__file__).resolve().parents[1]
        allowed = {'.py','.md','.json','.sql','.txt'}
        forbidden_paths = ('/work'+'space/', '/opt/'+'codex/', '/home/'+'agent/')
        for path in root.rglob('*'):
            if not path.is_file() or '__pycache__' in path.parts:
                continue
            with self.subTest(path=str(path.relative_to(root))):
                self.assertFalse(path.is_symlink())
                self.assertTrue(path.name == '.gitignore' or path.suffix in allowed)
                text = path.read_text()
                self.assertFalse(any(marker in text for marker in forbidden_paths))

    def test_ddl_is_idempotent(self):
        initialize(self.db)
        self.assertEqual(self.db.execute('SELECT count(*) FROM schema_version').fetchone()[0],1)

    def test_complete_snapshot_excludes_closed_dates(self):
        self.prices()
        result = self.query()
        self.assertEqual([r['date'] for r in result['rows']],['2020-01-03','2020-01-06'])
        self.assertEqual(result['selection']['source'],'primary')
        self.assertEqual(self.db.execute('SELECT count(*) FROM retrieval_audit').fetchone()[0],1)

    def test_cascade_selects_whole_secondary_not_mixed(self):
        self.prices(dates=('2020-01-03',),value=10)
        self.prices(source='secondary',value=20)
        result = self.query()
        self.assertEqual(result['selection']['source'],'secondary')
        self.assertEqual([r['close'] for r in result['rows']],[20,20])
        self.assertEqual(result['attempts'][0]['status'],'rejected_incomplete')

    def test_no_forward_fill_or_invented_suspension(self):
        self.prices(dates=('2020-01-03',))
        result = self.query(allow_gaps=True)
        self.assertIsNone(result['rows'][1]['close'])
        self.assertEqual(result['rows'][1]['observation_state'],'missing_unknown')

    def test_strict_missing_is_unavailable(self):
        self.prices(dates=('2020-01-03',))
        self.assertEqual(self.query()['status'],'unavailable')

    def test_no_weekend_prices(self):
        self.prices(dates=('2020-01-03','2020-01-04','2020-01-06'))
        self.assertEqual(self.query()['attempts'][0]['status'],'rejected_calendar')

    def test_missing_calendar_days_fail_closed(self):
        self.db.execute("DELETE FROM trading_calendar WHERE date='2020-01-04'")
        with self.assertRaisesRegex(ValueError,'every civil date'):
            self.query()

    def test_future_snapshot_does_not_leak(self):
        self.prices(known='2020-01-12T00:00:00Z')
        self.assertEqual(self.query()['status'],'unavailable')

    def test_dimensions_must_be_known_at_asof(self):
        with self.assertRaisesRegex(ValueError,'not known'):
            self.query(as_of='2020-01-09T00:00:00Z')

    def test_latest_revision_not_stale_filled(self):
        self.prices()
        self.prices(dates=('2020-01-03',),known='2020-01-10T01:00:00Z')
        self.assertEqual(self.query()['status'],'unavailable')

    def test_idempotent_and_duplicate_rejected_atomically(self):
        one = self.prices()
        self.assertEqual(one,self.prices())
        before = self.db.execute('SELECT count(*) FROM ingestion_batch').fetchone()[0]
        with self.assertRaises(duckdb.ConstraintException):
            self.prices(dates=('2020-01-03','2020-01-03'))
        self.assertEqual(self.db.execute('SELECT count(*) FROM ingestion_batch').fetchone()[0],before)

    def test_nonfinite_negative_and_bad_ohlc_rejected(self):
        for value in (float('nan'),float('inf'),-1):
            with self.subTest(value=value), self.assertRaises((ValueError,duckdb.ConstraintException)):
                self.prices(value=value)

    def test_adjusted_import_requires_reviewed_mapping(self):
        meta = self.meta();meta['price_basis']='hfq';meta['adjustment_id']='test'
        with self.assertRaisesRegex(ValueError,'raw prices'):
            self.load('prices',['instrument','date','open','high','low','close','volume_shares','amount_cny'],
                [['sh600001','2020-01-03',1,1,1,1,100,100]],meta)

    def test_units_and_timezone_mandatory(self):
        meta = self.meta();meta['volume_unit']='lots'
        with self.assertRaisesRegex(ValueError,'volume_unit'):
            self.load('prices',['instrument','date','open','high','low','close','volume_shares','amount_cny'],
                [['sh600001','2020-01-03',1,1,1,1,100,100]],meta)
        for timestamp in ('2020-01-01', '2020-01-01T00:00:00'):
            with self.assertRaises(ValueError):
                metadata(self.meta(known=timestamp))

    def test_backdated_available_at_rejected(self):
        meta = self.meta();meta['available_at']='2019-01-01T00:00:00Z'
        with self.assertRaisesRegex(ValueError,'predate'):
            metadata(meta)

    def test_lifecycle_clips_no_prelisting_fill(self):
        self.db.execute("UPDATE instrument_lifecycle SET listed_on='2020-01-06'")
        self.prices(dates=('2020-01-06',))
        self.assertEqual(len(self.query()['rows']),1)

    def test_financial_pit_uses_available_time_not_period_end(self):
        self.db.execute('INSERT INTO financial_fact VALUES (?,?,?,?,?,?,?,?,?,?)',
            [self.master,'sh600001','synthetic_profit','2019-12-31','2019-01-01','2020-04-01T08:00:00Z','2020-04-02T08:00:00Z',10,'CNY','v1'])
        count = self.db.execute("SELECT count(*) FROM financial_fact WHERE available_at <= TIMESTAMPTZ '2020-01-01T00:00:00Z'").fetchone()[0]
        self.assertEqual(count,0)
        with self.assertRaises(duckdb.ConstraintException):
            self.db.execute("UPDATE financial_fact SET available_at='2020-03-01T00:00:00Z'")

    def test_tencent_unit_mapping_and_bounds(self):
        for code,volume in [('sh600001',10),('sh688001',1000)]:
            body = json.dumps({'code':0,'data':{code:{'day':[['2020-01-03','10','10','10','10',str(volume),'','','1']]}}})
            result = parse_rows(body,code,'2020-01-03','2020-01-03')
            self.assertEqual(result['2020-01-03']['volume_shares'],1000)
            self.assertEqual(result['2020-01-03']['amount_cny'],10000)
        with self.assertRaises(ValueError):
            parse_rows('{}','bj430001','2020-01-01','2020-01-03')

    def test_http_denial_stops_and_blocks_same_destination(self):
        destination = self.root/'download'
        error = urllib.error.HTTPError('https://example.invalid',403,'denied',{},None)
        with patch('portable.fetch_tencent.urllib.request.build_opener') as builder:
            builder.return_value.open.side_effect = error
            with self.assertRaises(urllib.error.HTTPError):
                download('sh600001','2020-01-01','2020-01-03',destination,source_root=self.root/'source')
            self.assertEqual(builder.return_value.open.call_count,1)
            self.assertTrue((destination/'ACCESS_BLOCKED.json').exists())
            with self.assertRaisesRegex(RuntimeError,'access-denial'):
                download('sh600001','2020-01-01','2020-01-03',destination,source_root=self.root/'source')
            self.assertEqual(builder.return_value.open.call_count,1)
            with self.assertRaisesRegex(RuntimeError,'access-denial'):
                download('sh600002','2020-01-01','2020-01-03',self.root/'new-snapshot',source_root=self.root/'source')
            self.assertEqual(builder.return_value.open.call_count,1)

    def test_tencent_padded_dates_preserved_only_in_raw(self):
        body = json.dumps({'code':0,'data':{'sh600001':{'day':[
            ['2019-12-31','10','10','10','10','10','','','1'],
            ['2020-01-03','10','10','10','10','10','','','1']]}}})
        self.assertEqual(list(parse_rows(body,'sh600001','2020-01-03','2020-01-03')),['2020-01-03'])

    def test_http_200_captcha_persists_raw_and_stops_source(self):
        destination = self.root/'captcha'
        with patch('portable.fetch_tencent.urllib.request.build_opener') as builder:
            response = builder.return_value.open.return_value.__enter__.return_value
            response.read.return_value = b'<html>captcha access denied</html>'
            with self.assertRaises(AccessRestricted):
                download('sh600001','2020-01-01','2020-01-03',destination,source_root=self.root/'source')
            self.assertTrue((destination/'raw-2020.json').exists())
            self.assertEqual(json.loads((destination/'receipt-2020.json').read_text())['state'],'rejected')
            with self.assertRaisesRegex(RuntimeError,'access-denial'):
                download('sh600002','2020-01-01','2020-01-03',self.root/'different',source_root=self.root/'source')
            self.assertEqual(builder.return_value.open.call_count,1)

    def test_query_future_end_rejected(self):
        with self.assertRaisesRegex(ValueError,'Query end'):
            self.query(end='2020-01-11')

    def test_hf_adapter_requires_exact_revision_and_imports(self):
        parquet = self.root/'synthetic.parquet'
        self.db.execute("COPY (SELECT DATE '2020-01-03' AS date, 'sh600001' AS instrument,10.0 AS open,10.0 AS high,10.0 AS low,10.0 AS close,10.0 AS prev_close_reported,1000 AS volume_shares,10000 AS amount_cny,'synthetic-revision' AS source_revision) TO ? (FORMAT PARQUET)",[str(parquet)])
        with self.assertRaisesRegex(ValueError,'revision'):
            normalize(parquet,self.root/'bad','wrong',KNOWN)
        out = self.root/'hf'
        self.assertEqual(normalize(parquet,out,'synthetic-revision',KNOWN),1)
        result = ingest(self.db,'prices',out/'prices.csv',json.loads((out/'metadata.json').read_text()))
        self.assertEqual(result['rows'],1)


if __name__ == '__main__':
    unittest.main()
