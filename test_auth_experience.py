import json,os,tempfile,threading,unittest,urllib.request,urllib.error
os.environ['MOSAIC_DB_PATH']=tempfile.mktemp();os.environ['MOSAIC_RATE_LIMIT_RPM']='1000'
import app
class AuthExperience(unittest.TestCase):
 @classmethod
 def setUpClass(c):
  c.old=(app.STORE,app.BOOKS,app.RETAIL,app.PROFILES,app.PROVISIONER,app.ONBOARDING,app.MIGRATIONS_API,app.TAX,app.OAUTH,app.LIMITER)

  from store import Store
  from accounting import Accounting
  from retail import Retail
  from operational_profile import Profiles
  from provisioning import Provisioner
  from onboarding import Onboarding
  from migration_packs import Migrations
  from tax_engine import TaxEngine
  app.STORE=Store(tempfile.mktemp());app.BOOKS=Accounting(app.STORE);app.RETAIL=Retail(app.STORE,app.BOOKS);app.PROFILES=Profiles(app.STORE);app.PROVISIONER=Provisioner(app.STORE);app.ONBOARDING=Onboarding(app.STORE,app.PROFILES,app.PROVISIONER);app.MIGRATIONS_API=Migrations(app.STORE,app.BOOKS,app.RETAIL);app.TAX=TaxEngine(app.STORE);app.OAUTH=app.OAuth(app.STORE,app.PROVISIONER);app.LIMITER=app.RateLimiter(1000,app.STORE)
  from http.server import ThreadingHTTPServer;c.s=ThreadingHTTPServer(('127.0.0.1',0),app.H);c.p=c.s.server_address[1];threading.Thread(target=c.s.serve_forever,daemon=True).start()
 @classmethod
 def tearDownClass(c):
  c.s.shutdown();c.s.server_close();app.STORE.close();(app.STORE,app.BOOKS,app.RETAIL,app.PROFILES,app.PROVISIONER,app.ONBOARDING,app.MIGRATIONS_API,app.TAX,app.OAUTH,app.LIMITER)=c.old
 def call(self,path,body=None,token=None):
  h={'Content-Type':'application/json'}
  if token:h['Authorization']='Bearer '+token
  q=urllib.request.Request(f'http://127.0.0.1:{self.p}{path}',data=json.dumps(body).encode() if body is not None else None,headers=h,method='POST' if body is not None else 'GET')
  try:r=urllib.request.urlopen(q);status=r.status;raw=r.read()
  except urllib.error.HTTPError as e:status=e.code;raw=e.read()
  return status,json.loads(raw or b'{}')
 def signup(self,name,email):return self.call('/api/signup',{'company_name':name,'email':email,'password':'a-secure-password'})[1]
 def test_first_sign_in_multi_workspace_choice_and_role_landing(self):
  first=self.signup('North Shop','same@example.test');second=self.signup('South Shop','same@example.test');self.assertEqual(first['landing'],'/interview')
  status,x=self.call('/api/session/options',{'email':'same@example.test','password':'a-secure-password'});self.assertEqual((status,{w['name'] for w in x['workspaces']}),(200,{'North Shop','South Shop'}))
  status,x=self.call('/api/session',{'workspace_id':second['workspace_id'],'email':'same@example.test','password':'a-secure-password'});self.assertEqual((status,x['workspace_name'],x['landing']),(201,'South Shop','/interview'))
 def test_invite_single_use_role_binding_and_revocation(self):
  owner=self.signup('Invite Shop','owner@example.test');w=owner['workspace_id'];app.PROVISIONER.rbac.assign(w,'owner','role:Cashier','Cashier',['sale.create','payment.accept'])
  _,made=self.call('/api/workspace/invitations',{'email':'cash@example.test','role':'editor','operational_role':'Cashier'},owner['session_token']);token=made['invite_url'].split('token=')[1]
  status,user=self.call('/api/invitations/accept',{'token':token,'password':'another-secure-password'});self.assertEqual((status,user['landing']),(201,'/operations'))
  self.assertEqual(self.call('/api/invitations/accept',{'token':token,'password':'another-secure-password'})[0],409)
  ident=app.STORE.authenticate_session(user['session_token']);app.STORE.revoke_session(ident[3],ident[1]);self.assertEqual(self.call('/api/workspace',token=user['session_token'])[0],401)
 def test_expired_session_is_rejected(self):
  x=self.signup('Expiry Shop','expire@example.test');h=app.sha256(x['session_token']);app.STORE._db.execute("UPDATE sessions SET expires_at='2000-01-01T00:00:00+00:00' WHERE token_hash=?",(h,));self.assertEqual(self.call('/api/workspace',token=x['session_token'])[0],401)
 def test_pages_and_assets_revalidate_and_api_stays_uncached(self):
  import urllib.request
  for p in ('/operations','/interview','/operations.js','/interview.js','/auth.js','/operations.css'):
   r=urllib.request.urlopen(f'http://127.0.0.1:{self.p}{p}');self.assertEqual(r.headers.get('Cache-Control'),'no-cache',p)
  q=urllib.request.Request(f'http://127.0.0.1:{self.p}/api/workspaces',data=json.dumps({'name':'CacheCheck'}).encode(),headers={'Content-Type':'application/json'},method='POST')
  r=urllib.request.urlopen(q);self.assertEqual(r.headers.get('Cache-Control'),'no-store')
 def test_everyday_pages_have_no_keys_or_internal_credential_copy(self):
  for p in ('/interview','/operations','/retail','/accounting','/migration','/signin'):
   raw=urllib.request.urlopen(f'http://127.0.0.1:{self.p}{p}').read().decode().lower();self.assertNotIn('workspace key',raw);self.assertNotIn('access key',raw);self.assertNotIn('api key',raw)
if __name__=='__main__':unittest.main()
