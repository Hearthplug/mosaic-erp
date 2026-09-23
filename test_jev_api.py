import json,os,tempfile,threading,unittest,urllib.request,urllib.error
os.environ['MOSAIC_DB_PATH']=tempfile.mktemp();os.environ['MOSAIC_RATE_LIMIT_RPM']='1000'
import app

def call(port,method,path,body=None,key=None):
 h={'Content-Type':'application/json'}
 if key:h['Authorization']='Bearer '+key
 r=urllib.request.urlopen(urllib.request.Request(f'http://127.0.0.1:{port}{path}',data=json.dumps(body).encode() if body is not None else None,headers=h,method=method));return json.loads(r.read() or b'{}')

class JevAPI(unittest.TestCase):
 @classmethod
 def setUpClass(c):
  from http.server import ThreadingHTTPServer;c.s=ThreadingHTTPServer(('127.0.0.1',0),app.H);c.p=c.s.server_address[1];threading.Thread(target=c.s.serve_forever,daemon=True).start()
 @classmethod
 def tearDownClass(c):c.s.shutdown()

 def _workspace_with_answers(self):
  w=call(self.p,'POST','/api/workspaces',{'name':'JevFlow'});k=w['api_key']
  x=call(self.p,'POST','/api/onboarding/start',{},k)
  call(self.p,'POST','/api/onboarding/answer',{'id':x['id'],'key':'business_name','value':'northstar general store'},k)
  call(self.p,'POST','/api/onboarding/answer',{'id':x['id'],'key':'selling','value':'Customer walks in, cashier scans items, pays cash'},k)
  call(self.p,'POST','/api/onboarding/answer',{'id':x['id'],'key':'country','value':'registered in India'},k)
  return k,x

 def test_map_interview_returns_side_by_side_proposals(self):
  k,x=self._workspace_with_answers()
  r=call(self.p,'POST','/api/jev/map-interview',{'id':x['id']},k)
  self.assertEqual(r['client'],'mock');self.assertTrue(r['english_only'])
  by={p['key']:p for p in r['proposals']}
  self.assertEqual(by['selling']['raw'],'Customer walks in, cashier scans items, pays cash')
  self.assertEqual(by['selling']['proposed'],'Walk-in checkout, pays on the spot')
  self.assertEqual(by['country']['currency'],'INR')

 def test_map_interview_requires_owner(self):
  try:call(self.p,'POST','/api/jev/map-interview',{'id':'x'});self.fail('expected 401')
  except urllib.error.HTTPError as e:self.assertEqual(e.code,401)

 def test_reconfigure_proposes_then_applies_only_confirmed(self):
  k,x=self._workspace_with_answers()
  r=call(self.p,'POST','/api/jev/reconfigure',{'request':'we opened a second shop and customers can now pay monthly on account'},k)
  targets={c['target'] for c in r['changes']}
  self.assertIn('locations',targets);self.assertIn('credit',targets)
  picked=[c for c in r['changes'] if c['target']=='locations']
  a=call(self.p,'POST','/api/jev/reconfigure/apply',{'changes':picked},k)
  self.assertEqual(a['answers']['locations'],'2 to 5 places')
  self.assertNotEqual(a['answers'].get('credit'),'Customer credit')  # unconfirmed change not applied
  self.assertIn('transfers',a['profile']['enabled_modules'])

 def test_reconfigure_apply_rejects_unknown_options(self):
  k,x=self._workspace_with_answers()
  a=call(self.p,'POST','/api/jev/reconfigure/apply',{'changes':[{'target':'locations','proposed':'A million places'},{'target':'evil_key','proposed':'x'}]},k)
  self.assertNotIn('locations',a['answers'] if a['answers'].get('locations')=='A million places' else {})
  self.assertNotIn('evil_key',a['answers'])

 def test_reconfigure_non_english_refused(self):
  k,x=self._workspace_with_answers()
  r=call(self.p,'POST','/api/jev/reconfigure',{'request':'nous avons ouvert un deuxieme magasin la semaine derniere ici'},k)
  self.assertEqual(r['error'],'non_english');self.assertEqual(r['changes'],[])

if __name__=='__main__':unittest.main()
