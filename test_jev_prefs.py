import json,os,tempfile,threading,unittest,urllib.request,urllib.error
os.environ['MOSAIC_DB_PATH']=tempfile.mktemp();os.environ['MOSAIC_RATE_LIMIT_RPM']='1000'
os.environ['MOSAIC_ASSISTANT_SECRET_DIR']=tempfile.mkdtemp()
import app
from jev_client import HttpJevClient, MockJevClient

def call(port,method,path,body=None,key=None):
 h={'Content-Type':'application/json'}
 if key:h['Authorization']='Bearer '+key
 r=urllib.request.urlopen(urllib.request.Request(f'http://127.0.0.1:{port}{path}',data=json.dumps(body).encode() if body is not None else None,headers=h,method=method));return json.loads(r.read() or b'{}')

class AiPrefsAPI(unittest.TestCase):
 @classmethod
 def setUpClass(c):
  from http.server import ThreadingHTTPServer;c.s=ThreadingHTTPServer(('127.0.0.1',0),app.H);c.p=c.s.server_address[1];threading.Thread(target=c.s.serve_forever,daemon=True).start()
 @classmethod
 def tearDownClass(c):c.s.shutdown()

 def test_default_is_standard_with_three_options(self):
  w=call(self.p,'POST','/api/workspaces',{'name':'Prefs'});k=w['api_key']
  r=call(self.p,'GET','/api/ai/preference',None,k)
  self.assertEqual(r['provider'],'standard');self.assertFalse(r['has_key'])
  opts={o['id']:o for o in r['options']}
  self.assertEqual(set(opts),{'standard','jev','other'})
  self.assertTrue(opts['standard']['available']);self.assertTrue(opts['jev']['available'])
  self.assertFalse(opts['other']['available'])
  self.assertIn('Not available yet',opts['other']['line'])
  self.assertIn('Standard keeps everything inside Mosaic',r['consent_note'])

 def test_jev_requires_key_then_client_switches(self):
  w=call(self.p,'POST','/api/workspaces',{'name':'PrefsJev'});k=w['api_key']
  try:call(self.p,'POST','/api/ai/preference/switch',{'provider':'jev'},k);self.fail('expected 400')
  except urllib.error.HTTPError as e:self.assertEqual(e.code,400)
  r=call(self.p,'POST','/api/ai/preference/switch',{'provider':'jev','api_key':'ts-test-key-123'},k)
  self.assertEqual(r['provider'],'jev');self.assertTrue(r['has_key'])
  self.assertIsInstance(app.AIPREFS.client_for(r['provider'] and [x for x in app.STORE._db.execute('SELECT id FROM workspaces WHERE name=?',('PrefsJev',)).fetchone()][0]),HttpJevClient)
  r=call(self.p,'POST','/api/ai/preference/switch',{'provider':'standard'},k)
  self.assertEqual(r['provider'],'standard')

 def test_unknown_provider_rejected(self):
  w=call(self.p,'POST','/api/workspaces',{'name':'PrefsBad'});k=w['api_key']
  for bad in ('other','openai',''):
   try:call(self.p,'POST','/api/ai/preference/switch',{'provider':bad},k);self.fail('expected 400 for '+bad)
   except urllib.error.HTTPError as e:self.assertEqual(e.code,400)

 def test_switch_requires_owner(self):
  try:call(self.p,'POST','/api/ai/preference/switch',{'provider':'jev','api_key':'x'});self.fail('expected 401')
  except urllib.error.HTTPError as e:self.assertEqual(e.code,401)

 def test_built_in_is_default_client(self):
  self.assertIsInstance(app.AIPREFS.client_for('wsp_does_not_exist'),MockJevClient)
