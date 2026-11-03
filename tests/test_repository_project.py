import importlib.util,json,tempfile,unittest,zipfile
from pathlib import Path
spec=importlib.util.spec_from_file_location('portable',Path(__file__).parents[1]/'scripts/project.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class RepositoryProjectTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.repo=Path(self.tmp.name)/'repo';self.repo.mkdir();self.root=self.repo/'project';m.init(self.root)
  (self.root/'skill').rmdir();(self.repo/'scripts').mkdir();(self.repo/'scripts/project.py').write_text('# tool');(self.repo/'SKILL.md').write_text('# skill')
  c=m.read(self.root/'project.json');c['skill_source']='..';m.write(self.root/'project.json',c)
  m.write(self.root/'environment/skill-snapshot.json',{'files':[{'path':str(p.relative_to(self.repo)),'sha256':m.digest(p)} for p in m.skill_files(self.repo)]})
 def tearDown(self):self.tmp.cleanup()
 def test_repository_export_is_standalone(self):
  out=Path(self.tmp.name)/'bundle.zip';m.export(self.root,out);dst=Path(self.tmp.name)/'imported';m.import_bundle(out,dst)
  self.assertNotIn('skill_source',m.read(dst/'project.json'));self.assertTrue((dst/'skill/SKILL.md').is_file());self.assertFalse((self.root/'skill').exists())
  self.assertFalse(any('project/project/' in x for x in zipfile.ZipFile(out).namelist()))
 def test_parent_drift_rejected(self):
  (self.repo/'SKILL.md').write_text('changed')
  with self.assertRaises(ValueError):m.validate(self.root)
 def test_arbitrary_reference_rejected(self):
  c=m.read(self.root/'project.json');c['skill_source']='../elsewhere';m.write(self.root/'project.json',c)
  with self.assertRaises(ValueError):m.validate(self.root)
if __name__=='__main__':unittest.main()
