"""Offline Dodo TEST adapter tests. No provider requests or charges."""
import base64, hashlib, hmac, io, json, os, tempfile, time, unittest
from datetime import datetime, timezone, timedelta
from dodo_billing import verify_dodo_signature, bind_dodo_test_subscription, apply_dodo_test_webhook
from store import Store, Conflict

KEY=b'0123456789abcdefghijklmnopqrstuv'
SECRET='whsec_'+base64.b64encode(KEY).decode()

class DodoTest(unittest.TestCase):
 def setUp(self):
  self.db=Store(tempfile.mktemp());self.w1,_=self.db.create_workspace('A');self.w2,_=self.db.create_workspace('B')
 def tearDown(self):self.db.close()
 def intent(self,wid,nonce):
  self.db._db.execute('INSERT INTO dodo_test_checkout_intents(nonce,workspace_id,product_id,session_id,created_at) VALUES(?,?,?,?,?)',(nonce,wid,'prod_1','cks_1',datetime.now(timezone.utc).isoformat()))
 def payload(self, **fields):
  data=dict(subscription_id='sub_1', product_id='prod_1',status='active',metadata={'mosaic_workspace_id':self.w1,'mosaic_checkout_nonce':'nonce_1'},next_billing_date='2026-11-01T00:00:00Z');data.update(fields)
  return json.dumps(dict(business_id='biz_1',type='subscription.active',timestamp=datetime.now(timezone.utc).isoformat(),data=data)).encode()
 def test_standard_webhooks_signature(self):
  body=self.payload();now=int(time.time());ts=str(now);mid='msg_1'
  sig='v1,'+base64.b64encode(hmac.new(KEY,mid.encode()+b'.'+ts.encode()+b'.'+body,hashlib.sha256).digest()).decode()
  self.assertTrue(verify_dodo_signature(body,mid,ts,'v1,AAAA '+sig,SECRET,now))
  for args in [(body+b' ',mid,ts,sig,SECRET),(body,'msg_2',ts,sig,SECRET),(body,mid,str(now-301),sig,SECRET),(body,mid,ts,sig,'whsec_bad')]:
   self.assertFalse(verify_dodo_signature(*args,now))
 def test_binding_tenant_replay_order(self):
  self.intent(self.w1,'nonce_1')
  bind_dodo_test_subscription(self.db,self.w1,'sub_1','prod_1','nonce_1')
  first=self.payload()
  self.assertTrue(apply_dodo_test_webhook(self.db,self.w1,first,'msg_1')['applied'])
  with self.assertRaises(ValueError):apply_dodo_test_webhook(self.db,self.w1,self.payload(subscription_id='sub_other'),'msg_other')
  self.assertTrue(apply_dodo_test_webhook(self.db,self.w1,first,'msg_1')['duplicate'])
  with self.assertRaises(ValueError):apply_dodo_test_webhook(self.db,self.w2,first,'msg_2')
  with self.assertRaises(ValueError):apply_dodo_test_webhook(self.db,self.w1,self.payload(product_id='other'),'msg_2')
  with self.assertRaises(ValueError):bind_dodo_test_subscription(self.db,self.w2,'sub_1','prod_1','nonce_1')
  earlier=json.loads(first);earlier['timestamp']=(datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat();earlier['data']['status']='cancelled'
  self.assertFalse(apply_dodo_test_webhook(self.db,self.w1,json.dumps(earlier).encode(),'msg_3')['applied'])
  row=self.db._db.execute('SELECT status FROM billing_subscriptions WHERE workspace_id=?',(self.w1,)).fetchone()
  self.assertEqual(row['status'],'active')
  later=json.loads(first);later['timestamp']=(datetime.now(timezone.utc)+timedelta(minutes=1)).isoformat();later['data']['status']='cancelled'
  self.assertTrue(apply_dodo_test_webhook(self.db,self.w1,json.dumps(later).encode(),'msg_4')['applied'])
  self.assertEqual(self.db._db.execute('SELECT status FROM billing_subscriptions WHERE workspace_id=?',(self.w1,)).fetchone()['status'],'canceled')
 def test_http_route_signature_mode_and_no_unbound_write(self):
  import app, os, threading, urllib.request, urllib.error
  from http.server import ThreadingHTTPServer
  old_store=app.STORE;old_mode=os.environ.get('MOSAIC_DODO_TEST_MODE');old_secret=os.environ.get('MOSAIC_DODO_TEST_WEBHOOK_SECRET')
  app.STORE=self.db
  os.environ['MOSAIC_DODO_TEST_MODE']='true';os.environ['MOSAIC_DODO_TEST_WEBHOOK_SECRET']=SECRET
  server=ThreadingHTTPServer(('127.0.0.1',0),app.H)
  threading.Thread(target=server.serve_forever,daemon=True).start()
  def send(body, good=True):
   mid='msg_http';ts=str(int(time.time()))
   sig='v1,'+base64.b64encode(hmac.new(KEY,mid.encode()+b'.'+ts.encode()+b'.'+body,hashlib.sha256).digest()).decode()
   if not good:sig='v1,AAAA'
   req=urllib.request.Request('http://127.0.0.1:%s/api/billing/dodo-test-webhook'%server.server_address[1],data=body,
    headers={'webhook-id':mid,'webhook-timestamp':ts,'webhook-signature':sig},method='POST')
   try:r=urllib.request.urlopen(req)
   except urllib.error.HTTPError as e:r=e
   return r.status
  try:
   body=self.payload()
   self.assertEqual(send(body),400) # validly signed but unbound
   self.intent(self.w1,'nonce_1')
   bind_dodo_test_subscription(self.db,self.w1,'sub_1','prod_1','nonce_1')
   self.assertEqual(send(body,False),401)
   self.assertEqual(send(body),200)
   self.assertEqual(send(body),200)
   os.environ['MOSAIC_DODO_TEST_MODE']='false'
   self.assertEqual(send(body),404)
  finally:
   server.shutdown();server.server_close();app.STORE=old_store
   for k,v in (('MOSAIC_DODO_TEST_MODE',old_mode),('MOSAIC_DODO_TEST_WEBHOOK_SECRET',old_secret)):
    if v is None:os.environ.pop(k,None)
    else:os.environ[k]=v
 def test_malformed_signed_shape_is_rejected_without_server_error(self):
  self.intent(self.w1,'nonce_1')
  bind_dodo_test_subscription(self.db,self.w1,'sub_1','prod_1','nonce_1')
  base=json.loads(self.payload())
  cases=[dict(base,type=[]),dict(base,data=[]),dict(base,data=dict(base['data'],status=[])),
   dict(base,data=dict(base['data'],metadata={'mosaic_workspace_id':['not-a-workspace']})),
   dict(base,timestamp=[])]
  for n,bad in enumerate(cases):
   with self.subTest(n=n):
    with self.assertRaises(ValueError):apply_dodo_test_webhook(self.db,self.w1,json.dumps(bad).encode(),'bad_%s'%n)
  self.assertEqual(self.db._db.execute('SELECT COUNT(*) AS n FROM billing_events').fetchone()['n'],0)
 def test_owner_checkout_uses_only_test_host_and_external_product(self):
  import dodo_checkout
  old={k:os.environ.get(k) for k in ('MOSAIC_DODO_TEST_MODE','MOSAIC_DODO_TEST_API_KEY','MOSAIC_DODO_TEST_PRODUCT_ID','MOSAIC_DODO_TEST_RETURN_URL')}
  os.environ.update({'MOSAIC_DODO_TEST_MODE':'true','MOSAIC_DODO_TEST_API_KEY':'test_key_from_env',
    'MOSAIC_DODO_TEST_PRODUCT_ID':'pdt_external','MOSAIC_DODO_TEST_RETURN_URL':'https://example.com/return'})
  calls=[]
  class Response(io.BytesIO):
   def __enter__(self):return self
   def __exit__(self,*args):self.close()
  def opener(request,timeout):
   calls.append((request.full_url,dict(request.header_items()),json.loads(request.data),timeout))
   return Response(json.dumps({'session_id':'cks_test_1','checkout_url':'https://test.checkout.dodopayments.com/session/cks_test_1'}).encode())
  try:
   result=dodo_checkout.create_test_checkout(self.db,self.w1,opener)
   self.assertEqual(result['entitlements'],'none')
   self.assertEqual(calls[0][0],'https://test.dodopayments.com/checkouts')
   self.assertEqual(calls[0][2]['product_cart'],[{'product_id':'pdt_external','quantity':1}])
   self.assertNotIn('amount',str(calls[0][2]))
   nonce=calls[0][2]['metadata']['mosaic_checkout_nonce']
   self.assertEqual(self.db._db.execute('SELECT workspace_id FROM dodo_test_checkout_intents WHERE nonce=?',(nonce,)).fetchone()['workspace_id'],self.w1)
   os.environ['MOSAIC_DODO_TEST_MODE']='false'
   with self.assertRaises(ValueError):dodo_checkout.create_test_checkout(self.db,self.w1,opener)
   self.assertEqual(len(calls),1)
  finally:
   for k,v in old.items():
    if v is None:os.environ.pop(k,None)
    else:os.environ[k]=v
 def test_unbound_or_malformed_not_applied(self):
  with self.assertRaises(ValueError):apply_dodo_test_webhook(self.db,self.w1,self.payload(),'msg_1')
  self.intent(self.w1,'nonce_1')
  bind_dodo_test_subscription(self.db,self.w1,'sub_1','prod_1','nonce_1')
  with self.assertRaises(ValueError):apply_dodo_test_webhook(self.db,self.w1,b'{','msg_1')
  self.assertEqual(self.db._db.execute('SELECT COUNT(*) AS n FROM billing_events').fetchone()['n'],0)

if __name__=='__main__':unittest.main()
