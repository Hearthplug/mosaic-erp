import json,os,tempfile,threading,unittest,urllib.request
os.environ['MOSAIC_DB_PATH']=tempfile.mktemp();os.environ['MOSAIC_RATE_LIMIT_RPM']='1000'
import app
def call(port,method,path,body=None,key=None):
 h={'Content-Type':'application/json'}
 if key:h['Authorization']='Bearer '+key
 r=urllib.request.urlopen(urllib.request.Request(f'http://127.0.0.1:{port}{path}',data=json.dumps(body).encode() if body is not None else None,headers=h,method=method));return json.loads(r.read() or b'{}')
class InterviewAPI(unittest.TestCase):
 @classmethod
 def setUpClass(c):
  from http.server import ThreadingHTTPServer;c.s=ThreadingHTTPServer(('127.0.0.1',0),app.H);c.p=c.s.server_address[1];threading.Thread(target=c.s.serve_forever,daemon=True).start()
 @classmethod
 def tearDownClass(c):c.s.shutdown()
 def test_authenticated_save_resume_boundary(self):
  w=call(self.p,'POST','/api/workspaces',{'name':'Layman'});k=w['api_key'];schema=call(self.p,'GET','/api/onboarding/schema');self.assertGreater(len(schema['questions']),15);x=call(self.p,'POST','/api/onboarding/start',{},k);call(self.p,'POST','/api/onboarding/answer',{'id':x['id'],'key':'business_name','value':'Ravi Stores'},k);res=call(self.p,'GET','/api/onboarding/session?id='+x['id'],key=k);self.assertEqual(res['answers']['business_name'],'Ravi Stores');self.assertEqual(res['current_question'],'vertical')

 def test_apply_after_final_question_and_summary_wiring(self):
  w=call(self.p,'POST','/api/workspaces',{'name':'ApplyFlow'});k=w['api_key'];schema=call(self.p,'GET','/api/onboarding/schema');x=call(self.p,'POST','/api/onboarding/start',{},k)
  for q in schema['questions']:
   v='Not sure' if q['type']=='text' else (q['options'][0] if q['type']=='choice' else q['options'][:1])
   x=call(self.p,'POST','/api/onboarding/answer',{'id':x['id'],'key':q['key'],'value':v},k)
  self.assertIn(x['status'],('ready','needs_review'))
  h=open('interview.html').read();j=open('interview.js').read()
  self.assertIn('id="apply"',h);self.assertIn('summary-actions',h)
  self.assertIn("/api/onboarding/apply",j);self.assertIn('open-workspace',j);self.assertIn('/operations',j)
  if x['status']=='ready':
   r=call(self.p,'POST','/api/onboarding/apply',{'id':x['id']},k);self.assertIn('profile',r)
 def test_signup_validation_errors_are_400_not_500(self):
  import urllib.error
  try:call(self.p,'POST','/api/signup',{'company_name':'Short PW','email':'shortpw@test.local','password':'tiny'});self.fail('expected 400')
  except urllib.error.HTTPError as e:
   self.assertEqual(e.code,400);self.assertIn('password',e.read().decode())
if __name__=='__main__':unittest.main()

class NonRetailInferenceHonestyTest(unittest.TestCase):
 @classmethod
 def setUpClass(c):
  from http.server import ThreadingHTTPServer;c.s=ThreadingHTTPServer(('127.0.0.1',0),app.H);c.p=c.s.server_address[1];threading.Thread(target=c.s.serve_forever,daemon=True).start()
 @classmethod
 def tearDownClass(c):c.s.shutdown()
 def test_service_business_gets_honest_modules_and_summary(self):
  w=call(self.p,'POST','/api/workspaces',{'name':'Educlaas'});k=w['api_key']
  x=call(self.p,'POST','/api/onboarding/start',{},k)
  A={'business_name':'Educlaas','vertical':'Repairs or services','locations':'One place','selling':'Students enroll for a coaching batch and pay a monthly fee at the front desk.','buying':'We rarely buy anything to resell. Occasionally books and stationery.','stock_pain':'I do not keep stock','credit_behavior':'Only customers use credit','discounts':'Only I can waive a fee.','returns':'Refund unused months after approval.','staff':'Owner, two teachers, one front desk.','money_view':['Sales','Money customers owe','Profit'],'country':'India','selling_locations':['Near my registered business'],'buying_locations':['Nearby suppliers'],'price_display':'Tax is included in the shown price','customer_type':'Households','product_tax_facts':'Coaching fees are services.','existing_records':'Spreadsheets','exceptions':'Instalment fees confuse the front desk.','brand_style':'Clean and professional','brand_colors':'Blue','logo':'No, use the business name for now','screen_preference':'Money and collections','goal':'Not sure'}
  r=None
  for q,v in A.items():r=call(self.p,'POST','/api/onboarding/answer',{'id':x['id'],'key':q,'value':v},k)
  self.assertEqual(r['status'],'ready')
  inf=r['inference'];mods=set(inf['enabled_modules'])
  self.assertIn('receivables',mods);self.assertNotIn('payables',mods)
  self.assertNotIn('inventory',mods);self.assertIn('service',mods);self.assertNotIn('transfers',mods)
  self.assertFalse(any('supplier' in e['because'].lower() for e in inf['explanations']))
  self.assertIsNone(inf['owner_summary']['first_goal'])
  ap=call(self.p,'POST','/api/onboarding/apply',{'id':x['id']},k)
  self.assertEqual(set(ap['profile']['enabled_modules']),mods)
  st=call(self.p,'GET','/api/accounting/status',key=k)
  self.assertEqual(st['base_currency'],'INR')
