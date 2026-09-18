import os,tempfile,unittest
os.environ['MOSAIC_DB_PATH']=tempfile.mktemp()
import app
class CSPUI(unittest.TestCase):
 def test_ui_has_no_inline_script_or_style_and_routes_assets(self):
  for n in ('interview','retail','accounting'):
   h=open(n+'.html').read();self.assertNotIn('<style>',h);self.assertNotIn('<script>',h.replace(f'<script src="/{n}.js"></script>',''))
   self.assertIn(f'/{n}.css',h);self.assertTrue(open(n+'.css').read().strip())
  self.assertIn('/retail.js',open('retail.html').read());self.assertIn("if p == '/retail.js'",open('app.py').read())
 def test_csp_remains_strict(self):
  s=open('app.py').read();self.assertIn("script-src 'self'",s);self.assertIn("style-src 'self'",s);self.assertNotIn("'unsafe-inline'",s);self.assertNotIn('.style.',open('interview.js').read())
if __name__=='__main__':unittest.main()
