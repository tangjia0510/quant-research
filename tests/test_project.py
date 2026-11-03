import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

spec = importlib.util.spec_from_file_location('portable', Path(__file__).parents[1] / 'scripts' / 'project.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

class PortableTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.base=Path(self.temp.name)
        self.root=self.base/'p'; m.init(self.root)
    def tearDown(self): self.temp.cleanup()
    def study(self):
        p=self.root/'research'/'test'; p.mkdir()
        m.write(p/'research.yaml',dict(schema_version=1,id='test',title='Test',type='factor',status='rejected',data_refs=[],entrypoint=None))
        (p/'conclusion.md').write_text('Rejected, no valid signal.')
    def test_init_idempotent(self): self.assertTrue(m.init(self.root)['existing'])
    def test_roundtrip_excludes_work_and_bindings(self):
        self.study(); (self.root/'work'/'large.parquet').write_bytes(b'x')
        m.write(self.root/'local-paths.json',{'secret':'/private'})
        z=self.base/'p.zip'; m.export(self.root,z)
        with zipfile.ZipFile(z) as f:
            self.assertFalse(any(x.startswith('work/') or x=='local-paths.json' for x in f.namelist()))
        dst=self.base/'relocated'; m.import_bundle(z,dst)
        self.assertEqual(m.validate(dst)['research_count'],1)
        with self.assertRaises(ValueError): m.import_bundle(z,dst)
    def test_unbound_and_hash_mismatch(self):
        raw=self.base/'raw';raw.mkdir();f=raw/'x.txt';f.write_text('value')
        m.write(self.root/'data-catalog'/'x.json',dict(schema_version=1,id='x',version='v1',kind='file',sha256=m.digest(f),locator=dict(root='raw',path='x.txt')))
        with self.assertRaises(ValueError): m.resolve(self.root,'x')
        m.write(self.root/'local-paths.json',{'raw':'../raw'})
        self.assertTrue(m.resolve(self.root,'x')['identity_verified'])
        f.write_text('tampered')
        with self.assertRaises(ValueError): m.resolve(self.root,'x')
    def test_escape_rejected(self):
        for bad in ('../evil','/evil','x/../evil','C:/evil','x\\evil','x//evil','x/'):
            with self.assertRaises(ValueError): m.relative(bad)
    def test_link_rejected(self):
        (self.root/'research'/'x').symlink_to(self.base/'outside')
        with self.assertRaises(ValueError): m.portable_files(self.root)
    def test_zip_slip(self):
        z=self.base/'bad.zip'
        with zipfile.ZipFile(z,'w') as f: f.writestr('../evil','x')
        with self.assertRaises(ValueError):m.import_bundle(z,self.base/'dst')
        self.assertFalse((self.base/'evil').exists())
    def test_payload_tamper(self):
        z=self.base/'bad.zip'
        with zipfile.ZipFile(z,'w') as f:
            f.writestr('project.json','bad')
            f.writestr('PORTABLE_MANIFEST.json',json.dumps({'files':[dict(path='project.json',size=3,sha256='0'*64)]}))
        with self.assertRaises(ValueError):m.import_bundle(z,self.base/'dst')
    def test_registry_rejects_bookmark(self):
        self.study();p=self.root/'registry'/'factors'/'x';p.mkdir()
        m.write(p/'asset.json',dict(status='bookmarked',version='1',research_ids=['test']))
        with self.assertRaises(ValueError):m.validate(self.root)
    def test_derived_in_asset_rejected(self):
        (self.root/'research'/'bad.parquet').write_bytes(b'123')
        with self.assertRaises(ValueError):m.portable_files(self.root)
    def test_dry_run_does_not_write(self):
        z=self.base/'p.zip'; r=m.export(self.root,z,True)
        self.assertTrue(r['dry_run']);self.assertFalse(z.exists())
    def test_snapshot_drift(self):
        source=self.base/'source';source.mkdir();(source/'SKILL.md').write_text('v1')
        m.snapshot(self.root,source);m.validate(self.root)
        (self.root/'skill'/'SKILL.md').write_text('v2')
        with self.assertRaises(ValueError):m.validate(self.root)
    def test_snapshot_extra_file_rejected(self):
        source=self.base/'source';source.mkdir();(source/'SKILL.md').write_text('v1')
        m.snapshot(self.root,source)
        (self.root/'skill'/'extra.py').write_text('pass')
        with self.assertRaises(ValueError):m.validate(self.root)
    def test_import_directory_member_rejected(self):
        z=self.base/'bad.zip'
        with zipfile.ZipFile(z,'w') as f:f.writestr('research/','')
        with self.assertRaises(ValueError):m.import_bundle(z,self.base/'dst')
    def test_export_no_overwrite(self):
        z=self.base/'p.zip';m.export(self.root,z)
        with self.assertRaises(ValueError):m.export(self.root,z)
    def test_native_uppercase_id_preserved(self):
        self.assertEqual(m.check_id('20261101-144735Z-factor-example'), '20261101-144735Z-factor-example')
    def test_snapshot_cache_is_not_asset(self):
        source=self.base/'source';source.mkdir();(source/'SKILL.md').write_text('v1')
        m.snapshot(self.root,source)
        (self.root/'skill'/'__pycache__').mkdir()
        (self.root/'skill'/'__pycache__'/'x.pyc').write_bytes(b'cache')
        m.snapshot(self.root,source);m.validate(self.root)
    def test_research_runtime_cache_not_study(self):
        (self.root/'research'/'__pycache__').mkdir()
        (self.root/'research'/'__pycache__'/'helper.pyc').write_bytes(b'cache')
        self.assertEqual(m.validate(self.root)['research_count'],0)
    def test_catalog_traversal(self):
        m.write(self.root/'data-catalog'/'x.json',dict(schema_version=1,id='x',version='v1',kind='file',sha256='0'*64,locator=dict(root='raw',path='../evil')))
        with self.assertRaises(ValueError):m.validate(self.root)

if __name__=='__main__':unittest.main()
