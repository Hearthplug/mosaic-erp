import json,os,tempfile,threading,unittest,urllib.request,urllib.error
os.environ['MOSAIC_DB_PATH']=tempfile.mktemp();os.environ['MOSAIC_RATE_LIMIT_RPM']='1000'
import app
class OperationalRBACAPI(unittest.TestCase):
 @classmethod
 def setUpClass(c):
  # Other API suites replace app globals. Rebind this suite to one coherent store so test order cannot cross-wire foreign keys.
  import tempfile
  from store import Store
  from accounting import Accounting
  from retail import Retail
  from operational_profile import Profiles
  from provisioning import Provisioner
  from onboarding import Onboarding
  from migration_packs import Migrations
  from tax_engine import TaxEngine
  from artifact_builder import ArtifactBuilder
  from assistant_setup import AssistantSetup
  c.old=(app.STORE,app.BOOKS,app.RETAIL,app.PROFILES,app.PROVISIONER,app.ONBOARDING,app.MIGRATIONS_API,app.TAX,app.ARTIFACTS,app.ASSISTANT,app.OAUTH,app.LIMITER)
  app.STORE=Store(tempfile.mktemp());app.BOOKS=Accounting(app.STORE);app.RETAIL=Retail(app.STORE,app.BOOKS);app.PROFILES=Profiles(app.STORE);app.PROVISIONER=Provisioner(app.STORE);app.ONBOARDING=Onboarding(app.STORE,app.PROFILES,app.PROVISIONER);app.MIGRATIONS_API=Migrations(app.STORE,app.BOOKS,app.RETAIL);app.TAX=TaxEngine(app.STORE);app.ARTIFACTS=ArtifactBuilder(app.STORE,app.BOOKS,app.RETAIL);app.ASSISTANT=AssistantSetup(app.STORE);app.OAUTH=app.OAuth(app.STORE,app.PROVISIONER);app.LIMITER=app.RateLimiter(1000,app.STORE)
  from http.server import ThreadingHTTPServer;c.s=ThreadingHTTPServer(('127.0.0.1',0),app.H);c.p=c.s.server_address[1];threading.Thread(target=c.s.serve_forever,daemon=True).start()
 @classmethod
 def tearDownClass(c):
  c.s.shutdown();c.s.server_close();app.STORE.close();(app.STORE,app.BOOKS,app.RETAIL,app.PROFILES,app.PROVISIONER,app.ONBOARDING,app.MIGRATIONS_API,app.TAX,app.ARTIFACTS,app.ASSISTANT,app.OAUTH,app.LIMITER)=c.old
 def call(self,path,body=None,token=None):
  h={'Content-Type':'application/json'}
  if token:h['Authorization']='Bearer '+token
  q=urllib.request.Request(f'http://127.0.0.1:{self.p}{path}',data=json.dumps(body).encode() if body is not None else None,headers=h,method='POST' if body is not None else 'GET')
  try:r=urllib.request.urlopen(q);return r.status,json.loads(r.read() or b'{}')
  except urllib.error.HTTPError as e:return e.code,json.loads(e.read() or b'{}')
 def setup_user(self,permissions):
  w,key=app.STORE.create_workspace('RBAC API');app.BOOKS.setup(w,'owner');loc=app.RETAIL.setup_location(w,'owner','MAIN','Main')['id'];p=app.RETAIL.product(w,'owner','A','Apple',500,300)['id'];app.RETAIL.move_stock(w,'owner',p,loc,2,300,'opening','opening','1');u=app.STORE.create_user(w,'person@example.test','a-secure-password','editor','owner');assignment=app.PROVISIONER.rbac.assign(w,'owner',u['user_id'],'Staff',permissions,[loc]);session=app.STORE.login(w,u['email'],'a-secure-password');return w,loc,p,u,assignment,session['session_token']
 def snapshot(self,w):
  counts={t:app.STORE._db.execute(f'SELECT COUNT(*) n FROM {t} WHERE workspace_id=?',(w,)).fetchone()['n'] for t in ('sales','documents','stock_ledger','audit_events')};return counts
 def test_forbidden_named_user_causes_zero_mutations(self):
  w,loc,p,u,a,token=self.setup_user(['product.create']);before=self.snapshot(w);status,_=self.call('/api/retail/sales',{'location_id':loc,'lines':[{'product_id':p,'quantity':'1'}],'tenders':[{'kind':'cash','amount_minor':500}]},token);self.assertEqual(status,403);self.assertEqual(self.snapshot(w),before);self.assertEqual(app.RETAIL.stock(w,p,loc),2)
 def test_revoked_assignment_blocks_previously_allowed_action_with_zero_mutations(self):
  w,loc,p,u,a,token=self.setup_user(['sale.create']);app.PROVISIONER.rbac.revoke(w,'owner',a['id']);before=self.snapshot(w);status,_=self.call('/api/retail/sales',{'location_id':loc,'lines':[{'product_id':p,'quantity':'1'}],'tenders':[{'kind':'cash','amount_minor':500}]},token);self.assertEqual(status,403);self.assertEqual(self.snapshot(w),before);self.assertEqual(app.RETAIL.stock(w,p,loc),2)
if __name__=='__main__':unittest.main()
