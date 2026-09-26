"""Offline sandbox billing boundary and webhook tests."""
import hashlib,hmac,json,os,tempfile,time,unittest
from datetime import datetime,timezone,timedelta
from billing import apply_test_event,list_test_subscriptions,verify_test_signature
from store import Store,Conflict

class BillingTest(unittest.TestCase):
 def setUp(self):
  self.db=Store(tempfile.mktemp());self.w1,_=self.db.create_workspace('A');self.w2,_=self.db.create_workspace('B')
 def tearDown(self):self.db.close()
 def event(self,**kw):
  return dict(id='evt1',workspace_id=self.w1,subscription_id='sub1',plan_ref='provider_price_ref',status='active',event_at=datetime.now(timezone.utc).isoformat(),**kw)
 def test_signature_exact_bytes_expiry_and_tampering(self):
  body=b'{"hello":"world"}';ts=str(int(time.time()));sig=hmac.new(b'secret',ts.encode()+b'.'+body,hashlib.sha256).hexdigest()
  self.assertTrue(verify_test_signature(body,ts,sig,'secret'))
  self.assertFalse(verify_test_signature(body+b' ',ts,sig,'secret'))
  self.assertFalse(verify_test_signature(body,str(int(ts)-301),sig,'secret'))
  self.assertFalse(verify_test_signature(body,ts,sig,'wrong'))
  self.assertFalse(verify_test_signature(body,ts,sig,''))
 def test_tenant_events_dedupe_order_and_no_entitlements(self):
  first=self.event();self.assertTrue(apply_test_event(self.db,first)['applied']);self.assertTrue(apply_test_event(self.db,first)['duplicate'])
  self.assertEqual(list_test_subscriptions(self.db,self.w2)['subscriptions'],[])
  self.assertEqual(list_test_subscriptions(self.db,self.w1)['entitlements'],'none')
  foreign=dict(first,id='evt2',workspace_id=self.w2)
  with self.assertRaises((Conflict, __import__('sqlite3').IntegrityError)):apply_test_event(self.db,foreign)
  older=dict(first,id='evt3',status='canceled',event_at=(datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat())
  self.assertFalse(apply_test_event(self.db,older)['applied'])
  self.assertEqual(list_test_subscriptions(self.db,self.w1)['subscriptions'][0]['status'],'active')
  newer=dict(first,id='evt4',status='canceled',event_at=(datetime.now(timezone.utc)+timedelta(minutes=1)).isoformat())
  self.assertTrue(apply_test_event(self.db,newer)['applied'])
  self.assertEqual(list_test_subscriptions(self.db,self.w1)['subscriptions'][0]['status'],'canceled')
 def test_bad_event_rejected(self):
  e=self.event();e['status']='paid';
  with self.assertRaises(ValueError):apply_test_event(self.db,e)
  e=self.event();e['workspace_id']='wsp_nonexistent';
  with self.assertRaises(ValueError):apply_test_event(self.db,e)

class BillingHttpTest(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  import app,threading
  from http.server import ThreadingHTTPServer
  cls.app=app;cls.old=(app.STORE,app.LIMITER);cls.old_mode=os.environ.get('MOSAIC_BILLING_TEST_MODE');cls.old_secret=os.environ.get('MOSAIC_BILLING_TEST_SECRET')
  app.STORE=Store(tempfile.mktemp());app.LIMITER=app.RateLimiter(1000,app.STORE)
  cls.w1,cls.k1=app.STORE.create_workspace('A');cls.w2,cls.k2=app.STORE.create_workspace('B')
  cls.server=ThreadingHTTPServer(('127.0.0.1',0),app.H);threading.Thread(target=cls.server.serve_forever,daemon=True).start()
  os.environ['MOSAIC_BILLING_TEST_MODE']='true';os.environ['MOSAIC_BILLING_TEST_SECRET']='local-only-test-secret'
 @classmethod
 def tearDownClass(cls):
  cls.server.shutdown();cls.server.server_close();cls.app.STORE.close();cls.app.STORE,cls.app.LIMITER=cls.old
  for k,v in (('MOSAIC_BILLING_TEST_MODE',cls.old_mode),('MOSAIC_BILLING_TEST_SECRET',cls.old_secret)):
   if v is None:os.environ.pop(k,None)
   else:os.environ[k]=v
 def call(self,path,data=None,headers=None):
  import urllib.request,urllib.error
  req=urllib.request.Request('http://127.0.0.1:%s%s'%(self.server.server_address[1],path),data=data,headers=headers or {},method='POST' if data is not None else 'GET')
  try:r=urllib.request.urlopen(req)
  except urllib.error.HTTPError as e:r=e
  return r.status,json.loads(r.read())
 def test_webhook_auth_and_tenant_read(self):
  e=dict(id='evt_http',workspace_id=self.w1,subscription_id='sub_http',plan_ref='price_external',status='active',event_at=datetime.now(timezone.utc).isoformat())
  body=json.dumps(e).encode();ts=str(int(time.time()))
  sig=hmac.new(b'local-only-test-secret',ts.encode()+b'.'+body,hashlib.sha256).hexdigest()
  headers={'X-Mosaic-Test-Timestamp':ts,'X-Mosaic-Test-Signature':sig}
  self.assertEqual(self.call('/api/billing/test-webhook',body,headers)[0],200)
  self.assertEqual(self.call('/api/billing/test-webhook',body+b' ',headers)[0],401)
  self.assertEqual(self.call('/api/billing/test-subscriptions',headers={'Authorization':'Bearer '+self.k2})[1]['subscriptions'],[])
  self.assertEqual(len(self.call('/api/billing/test-subscriptions',headers={'Authorization':'Bearer '+self.k1})[1]['subscriptions']),1)
  self.assertEqual(self.call('/api/billing/test-subscriptions')[0],401)
  os.environ['MOSAIC_BILLING_TEST_MODE']='false'
  self.assertEqual(self.call('/api/billing/test-webhook',body,headers)[0],404)
  os.environ['MOSAIC_BILLING_TEST_MODE']='true'

class BillingSchemaTest(unittest.TestCase):
 def test_postgres_force_rls_and_tenant_context(self):
  from billing_schema import POSTGRES_BILLING_SCHEMA
  from postgres_store import _context
  for table in ('billing_subscriptions','billing_events'):
   self.assertIn('ALTER TABLE '+table+' FORCE ROW LEVEL SECURITY',POSTGRES_BILLING_SCHEMA)
   self.assertIn("workspace_id=current_setting('mosaic.workspace_id',true)",POSTGRES_BILLING_SCHEMA)
  self.assertEqual(_context('SELECT * FROM billing_subscriptions WHERE workspace_id=?',('wsp_test',)),('mosaic.workspace_id','wsp_test'))

if __name__=='__main__':unittest.main()
