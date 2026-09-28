import json,os,tempfile,threading,unittest,urllib.request,urllib.error
os.environ['MOSAIC_DB_PATH']=tempfile.mktemp();os.environ['MOSAIC_RATE_LIMIT_RPM']='1000'
import app
def call(port,method,path,body=None,key=None):
 h={'Content-Type':'application/json'}
 if key:h['Authorization']='Bearer '+key
 r=urllib.request.urlopen(urllib.request.Request(f'http://127.0.0.1:{port}{path}',data=json.dumps(body).encode() if body is not None else None,headers=h,method=method));return json.loads(r.read() or b'{}')
ANS={'business_name':'Ravi Stores','vertical':'Groceries and daily needs','locations':'One place','selling':'Counter sales, cash mostly.','buying':'I restock weekly from the wholesale market.','stock_pain':'Running out of fast movers','credit_behavior':'Only customers use credit','discounts':'Only I can approve.','returns':'Exchange within a day.','staff':'Just me.','money_view':['Sales'],'country':'India','selling_locations':['Nearby'],'buying_locations':['Nearby suppliers'],'price_display':'Tax is included in the shown price','customer_type':'Households','product_tax_facts':'Staples.','existing_records':'Paper notebook','exceptions':'None.','brand_style':'Simple','brand_colors':'Green','logo':'No, use the business name for now','screen_preference':'Sales first','goal':'Not sure'}
class ReviewPreview(unittest.TestCase):
 @classmethod
 def setUpClass(c):
  from http.server import ThreadingHTTPServer
  from store import Store
  from accounting import Accounting
  from retail import Retail
  from operational_profile import Profiles
  from onboarding import Onboarding
  app.STORE=Store(tempfile.mktemp());app.BOOKS=Accounting(app.STORE);app.RETAIL=Retail(app.STORE,app.BOOKS);app.PROFILES=Profiles(app.STORE);app.PROVISIONER=app.Provisioner(app.STORE);app.ONBOARDING=Onboarding(app.STORE,app.PROFILES,app.PROVISIONER);app.LIMITER=app.RateLimiter(1000,app.STORE)
  c.s=ThreadingHTTPServer(('127.0.0.1',0),app.H);c.p=c.s.server_address[1];threading.Thread(target=c.s.serve_forever,daemon=True).start()
 @classmethod
 def tearDownClass(c):c.s.shutdown()
 def _session(self,k,answers):
  x=call(self.p,'POST','/api/onboarding/start',{},k)
  for q,v in answers.items():x=call(self.p,'POST','/api/onboarding/answer',{'id':x['id'],'key':q,'value':v},k)
  return x
 def test_preview_shape_for_ready_session(self):
  w=call(self.p,'POST','/api/workspaces',{'name':'PrevShape'});k=w['api_key']
  x=self._session(k,ANS);self.assertEqual(x['status'],'ready')
  p=call(self.p,'GET','/api/onboarding/review-preview?id='+x['id'],key=k)
  self.assertIn('profile',p);self.assertIn('currency',p)
  prof=p['profile'];self.assertIsInstance(prof.get('enabled_modules'),list)
  self.assertIn('sales',prof['enabled_modules'])
  self.assertEqual(p['currency'],'INR')
 def test_operations_profile_none_then_stored_after_apply(self):
  w=call(self.p,'POST','/api/workspaces',{'name':'PrevLive'});k=w['api_key']
  p0=call(self.p,'GET','/api/operations/profile',key=k)
  self.assertIsNone(p0['profile'],'no stored profile before the first apply')
  x=self._session(k,ANS);call(self.p,'POST','/api/onboarding/apply',{'id':x['id']},k)
  p1=call(self.p,'GET','/api/operations/profile',key=k)
  self.assertIsNotNone(p1['profile'],'apply stores the operational profile the app consumes')
  self.assertIsInstance(p1['profile'].get('enabled_modules'),list)
 def test_auth_and_workspace_isolation(self):
  w=call(self.p,'POST','/api/workspaces',{'name':'PrevAuth'});k=w['api_key']
  x=self._session(k,ANS)
  for path in ('/api/onboarding/review-preview?id='+x['id'],'/api/operations/profile'):
   try:call(self.p,'GET',path);self.fail('expected 401')
   except urllib.error.HTTPError as e:self.assertEqual(e.code,401)
  w2=call(self.p,'POST','/api/workspaces',{'name':'PrevAuth2'});k2=w2['api_key']
  try:call(self.p,'GET','/api/onboarding/review-preview?id='+x['id'],key=k2);self.fail('expected 404')
  except urllib.error.HTTPError as e:self.assertEqual(e.code,404)
  p=call(self.p,'GET','/api/operations/profile',key=k2)
  self.assertIsNone(p['profile'],'other workspace sees only its own (empty) profile')

 def test_preview_reflects_module_toggles(self):
  w=call(self.p,'POST','/api/workspaces',{'name':'PrevToggle'});k=w['api_key']
  x=self._session(k,ANS)
  call(self.p,'POST','/api/onboarding/modules',{'id':x['id'],'overrides':{'inventory':False}},k)
  p=call(self.p,'GET','/api/onboarding/review-preview?id='+x['id'],key=k)
  self.assertNotIn('inventory',p['profile']['enabled_modules'],'toggling Stock off must remove it from the preview')
  self.assertIn('sales',p['profile']['enabled_modules'])
 def test_operations_frameable_same_origin_other_pages_not(self):
  import urllib.request
  r=urllib.request.urlopen(f'http://127.0.0.1:{self.p}/operations')
  self.assertIn("frame-ancestors 'self'",r.headers.get('Content-Security-Policy',''),'review screen embeds /operations in same-origin iframes')
  r2=urllib.request.urlopen(f'http://127.0.0.1:{self.p}/signin')
  self.assertIn("frame-ancestors 'none'",r2.headers.get('Content-Security-Policy',''),'other pages keep clickjacking protection')
  r3=urllib.request.urlopen(f'http://127.0.0.1:{self.p}/interview')
  self.assertIn("frame-src 'self'",r3.headers.get('Content-Security-Policy',''),'review screen may embed same-origin app frames')
if __name__=='__main__':unittest.main()
