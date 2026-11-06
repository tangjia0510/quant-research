"""Exercise collector function without running live artifact traversal."""
import ast,unittest
from pathlib import Path
class MarginUnionTests(unittest.TestCase):
 def test_overlap_and_source_specific_fields(self):
  tree=ast.parse((Path(__file__).parents[1]/'build_margin_union_coverage.py').read_text())
  fun=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='accept')
  env={'markets':{},'sources':{},'FIELDS':['balance','buy','repay']}
  exec(compile(ast.Module(body=[fun],type_ignores=[]),'fixture','exec'),env)
  f=env['accept'];f('SSE','2026-10-30','600000',{'b':1,'x':2},['b','x',None],'official');f('SSE','2026-10-30','600000',{'b':1,'x':2,'r':3},['b','x','r'],'vendor')
  self.assertEqual(len(env['markets']['SSE']['2026-10-30']),1)
  self.assertEqual(env['markets']['SSE']['2026-10-30']['600000'],7)
  self.assertEqual(env['sources']['official']['SSE']['2026-10-30']['nonnull_field_rows'],[1,1,0])
  self.assertEqual(env['sources']['vendor']['SSE']['2026-10-30']['nonnull_field_rows'],[1,1,1])
if __name__=='__main__':unittest.main()
