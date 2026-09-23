import io,json,os,tempfile,unittest
from unittest.mock import patch
from store import Store
from assistant_setup import AssistantSetup
class AssistantSetupTests(unittest.TestCase):
 def setUp(self):self.t=tempfile.NamedTemporaryFile();self.secret=tempfile.TemporaryDirectory();self.env=patch.dict(os.environ,{'MOSAIC_ASSISTANT_SECRET_DIR':self.secret.name});self.env.start();self.s=Store(self.t.name);self.w,self.k=self.s.create_workspace('Chat setup');self.a=AssistantSetup(self.s)
 def tearDown(self):self.s.close();self.env.stop();self.secret.cleanup()
 def test_default_and_remote_preview_secret_no_audit_leak(self):
  self.assertEqual(self.a.get(self.w)['mode'],'deterministic')
  p=self.a.chat(self.w,self.k,'use endpoint https://api.openai.com/v1 model tiny-model');self.assertEqual(p['intent'],'preview');self.a.stage(self.w,self.k,p['preview']);x=self.a.chat(self.w,self.k,'confirm');self.assertTrue(x['open_secret_form']);secret='sk-super-secret-value';self.a.save_secret(self.w,self.k,secret);dump=' '.join(str(x) for x in self.s.audit_trail(self.w));self.assertNotIn(secret,dump);self.assertNotIn(secret,str(self.a.get(self.w)));self.assertEqual(os.stat(next(__import__('pathlib').Path(self.secret.name).glob('*.key'))).st_mode & 0o777,0o600)
 def test_schema_constrained_canary(self):
  p=self.a.chat(self.w,self.k,'use endpoint https://api.openai.com/v1 model tiny-model');self.a.stage(self.w,self.k,p['preview']);self.a.chat(self.w,self.k,'confirm');self.a.save_secret(self.w,self.k,'secret')
  response=json.dumps({'choices':[{'message':{'content':json.dumps({'kind':'status','confidence':1})}}]}).encode()
  with patch('assistant_setup._pinned_post',return_value=response):self.assertTrue(self.a.test(self.w)['healthy'])
 def test_local_download_preview_with_measurements(self):
  x=self.a.chat(self.w,self.k,'use private local assistant');self.assertEqual(x['intent'],'preview');self.assertTrue(x['requires_confirmation']);self.assertEqual(x['local_model']['bytes'],1117320736);self.assertEqual(x['local_model']['adapter']['sha256'],'353fe1febb5b3adc03a3b8a0bf3aa4b86bea55a5d3dfce17b102d5a61c73cd55');m=x['local_model']['measured_requirements'];self.assertEqual(m['amd64']['unsafe_fail_closed'],1.0);self.assertEqual(m['arm64']['unsafe_fail_closed'],1.0);self.assertEqual(m['amd64']['schema_validity'],1.0);self.assertEqual(m['arm64']['schema_validity'],1.0)
 def test_private_or_http_endpoint_rejected(self):
  for u in ('http://example.com/v1','https://127.0.0.1/v1','https://localhost/v1'):
   with self.assertRaises(ValueError):self.a.chat(self.w,self.k,f'use endpoint {u} model x')
 def test_disable_is_previewed(self):
  x=self.a.chat(self.w,self.k,'disable assistant');self.assertEqual(x['intent'],'preview');self.assertEqual(x['preview']['mode'],'deterministic')
if __name__=='__main__':unittest.main()

class EverydayRoutingTest(unittest.TestCase):
 @classmethod
 def setUpClass(c):
  os.environ['MOSAIC_DB_PATH']=tempfile.mktemp()
  global app
  import app as _app;app=_app
 def test_tax_question_gets_real_answer_not_canned_list(self):
  out=app.ASSISTANT.chat('wsp_q','owner','Show me the tax settings for India')
  self.assertEqual(out['intent'],'answer');self.assertIn('GST',out['reply']);self.assertNotIn('keep simple built-in chat',out['reply'])
 def test_navigation_question_routes_to_screen(self):
  out=app.ASSISTANT.chat('wsp_q','owner','where do I see my stock')
  self.assertEqual(out['intent'],'answer');self.assertIn('Stock',out['reply'])
 def test_unknown_question_is_honest_not_canned(self):
  out=app.ASSISTANT.chat('wsp_q','owner','what is the weather tomorrow')
  self.assertIn("can't answer",out['reply']);self.assertNotIn('keep simple built-in chat, connect your own',out['reply'])
