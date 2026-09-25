import json,os,re,tempfile,threading,unittest,urllib.request,urllib.error
os.environ['MOSAIC_DB_PATH']=tempfile.mktemp();os.environ['MOSAIC_RATE_LIMIT_RPM']='1000'
import app

class CurrencyResolution(unittest.TestCase):
 EXPECT={'India':'INR','UAE':'AED','Singapore':'SGD','China':'CNY','Vietnam':'VND','Malaysia':'MYR','United Kingdom':'GBP','United States':'USD','Canada':'CAD','European Union':'EUR','Australia':'AUD','Brazil':'BRL','Indonesia':'IDR','Japan':'JPY','Mexico':'MXN','New Zealand':'NZD','Philippines':'PHP','Saudi Arabia':'SAR','South Africa':'ZAR','South Korea':'KRW','Switzerland':'CHF','Thailand':'THB'}
 def test_plain_pack_keys(self):
  for name,ccy in self.EXPECT.items():
   self.assertEqual(app.pack_currency_for_answer(name),ccy,name)
 def test_free_text_sentences(self):
  for name,ccy in self.EXPECT.items():
   got=app.pack_currency_for_answer('Registered in %s. We sell locally in one city.'%name)
   self.assertEqual(got,ccy,'sentence for '+name)
 def test_aliases(self):
  self.assertEqual(app.pack_currency_for_answer('We are in Dubai, UAE'),'AED')
  self.assertEqual(app.pack_currency_for_answer('Mumbai-based, selling across India'),'INR')
 def test_unknown_and_empty_fall_back_to_usd(self):
  self.assertEqual(app.pack_currency_for_answer(''),'USD')
  self.assertEqual(app.pack_currency_for_answer('Somewhere far away'),'USD')
  self.assertEqual(app.pack_currency_for_answer(None),'USD')

class CleanClientErrors(unittest.TestCase):
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
 def call(self,path,body=None,token=None,method=None):
  h={'Content-Type':'application/json'}
  if token:h['Authorization']='Bearer '+token
  q=urllib.request.Request(f'http://127.0.0.1:{self.p}{path}',data=json.dumps(body).encode() if body is not None else None,headers=h,method=method or ('POST' if body is not None else 'GET'))
  try:r=urllib.request.urlopen(q);status=r.status;raw=r.read()
  except urllib.error.HTTPError as e:status=e.code;raw=e.read()
  return status,json.loads(raw or b'{}')
 def ws(self,name):
  return self.call('/api/workspaces',{'name':name})[1]['api_key']
 def test_missing_fields_are_400_not_500(self):
  k=self.ws('Clean Errors')
  for path,body in [('/api/retail/products',{}),('/api/retail/locations',{}),('/api/retail/cash/open',{}),('/api/retail/cash/close',{}),('/api/accounting/documents',{}),('/api/accounting/payments',{}),('/api/accounting/periods/lock',{}),('/api/retail/transfers',{}),('/api/retail/returns',{}),('/api/onboarding/answer',{}),('/api/accounting/bank/import',{})]:
   st,res=self.call(path,body,k)
   self.assertEqual(st,400,(path,st,res)); self.assertIn('error',res)
 def test_bad_numbers_are_400_not_500(self):
  k=self.ws('Bad Numbers')
  st,loc=self.call('/api/retail/locations',{'code':'M','name':'M','kind':'store'},k)
  st,p=self.call('/api/retail/products',{'sku':'A-1','name':'A','selling_price_minor':100,'cost_minor':50},k)
  st,res=self.call('/api/retail/sales',{'location_id':loc.get('id') if isinstance(loc,dict) else None,'lines':[{'product_id':p.get('id'),'quantity':'abc'}],'tenders':[{'kind':'cash','amount_minor':100}],'currency':'USD'},k)
  self.assertEqual(st,400,(st,res))
 def test_wrong_types_are_400_not_500(self):
  k=self.ws('Wrong Types')
  st,res=self.call('/api/retail/returns',{'sale_id':'s_x','lines':None},k)
  self.assertEqual(st,400,(st,res))
 def test_duplicate_code_is_409_not_500(self):
  k=self.ws('Duplicates')
  st,_=self.call('/api/retail/products',{'sku':'DUP-1','name':'One','selling_price_minor':100,'cost_minor':50},k)
  self.assertEqual(st,201,st)
  st,res=self.call('/api/retail/products',{'sku':'DUP-1','name':'Two','selling_price_minor':100,'cost_minor':50},k)
  self.assertEqual(st,409,(st,res)); self.assertIn('already exists',res['error'])
 def test_tax_checklist_unknown_jurisdiction_is_400_not_500(self):
  k=self.ws('Tax Checklist')
  st,res=self.call('/api/tax/checklist',token=k)
  self.assertEqual(st,400,(st,res))
  st,res=self.call('/api/tax/checklist?jurisdiction=Atlantis',token=k)
  self.assertEqual(st,400,(st,res))
 ANSWERS={'vertical':'Groceries or food','locations':'One place',
  'selling':'Customers pick items, we ring them up at the counter, they pay by card or cash.',
  'buying':'I reorder when stock runs low. I approve each purchase myself and check every delivery against the supplier bill.',
  'stock_pain':'Running out','credit_behavior':'Only suppliers give us credit',
  'discounts':'Only the owner gives discounts. Refunds always need the owner.',
  'returns':'Within seven days with a receipt we refund or exchange. Unused items go back on the shelf.',
  'staff':'Two cashiers can ring up sales but cannot change prices. The owner manages everything else.',
  'money_view':['Sales','Low stock','Money I owe suppliers'],
  'selling_locations':['Near my registered business'],'buying_locations':['Nearby suppliers'],
  'price_display':'Tax is added at checkout','customer_type':'Households',
  'product_tax_facts':'No special tax treatment that our accountant flags.','existing_records':'Spreadsheets',
  'exceptions':'Partial deliveries from suppliers cause the most confusion.',
  'brand_style':'Clean and professional','brand_colors':'Deep green and warm white',
  'logo':'No, use the business name for now','screen_preference':'Today\u2019s manager checklist',
  'goal':'Know what to reorder each morning without digging through spreadsheets.'}
 def test_interview_country_sets_currency_end_to_end(self):
  for country,ccy in [('Registered in India. We sell locally in one city.','INR'),('Registered in UAE. We sell locally.','AED'),('Registered in Japan, selling in Tokyo.','JPY'),('Registered in China. We sell locally in one city.','CNY'),('Registered in the United States. We sell locally in one city.','USD')]:
   k=self.ws('Currency '+ccy)
   st,s=self.call('/api/onboarding/start',{},k); sid=s['id']
   a=dict(self.ANSWERS); a['business_name']='Currency '+ccy; a['country']=country
   for kk,vv in a.items(): self.call('/api/onboarding/answer',{'id':sid,'key':kk,'value':vv},k)
   st,res=self.call('/api/onboarding/apply',{'id':sid},k)
   self.assertIn(st,(200,201),(st,res))
   st,res=self.call('/api/accounting/status',token=k)
   self.assertEqual(res.get('base_currency'),ccy,(country,res))

if __name__=='__main__': unittest.main()

class V212StaticGuards(unittest.TestCase):
    """Regression guards for UI fixes verified live in the browser (see PR evidence)."""

    def test_notice_icons_use_hidden_attribute(self):
        js = open('operations.js').read()
        self.assertIn("$('#notice-icon-ok').toggleAttribute('hidden'", js)
        self.assertNotIn("$('#notice-icon-ok').hidden=", js)

    def test_setup_chain_is_fault_tolerant(self):
        js = open('operations.js').read()
        self.assertIn("const safe=(label,fn)=>{try{fn()}catch(e){console.error('setup '+label+' failed',e)}};", js)
        self.assertIn("safe('till',()=>tillSetup(c.locations||[]))", js)
        self.assertIn("if(wrap)wrap.hidden=true", js)

    def test_no_inline_style_attributes_in_pages(self):
        import re
        for page in ('static.html', 'migration.html', 'operations.html'):
            html = open(page).read()
            bad = re.findall(r'style="[^"]*"', html)
            self.assertEqual(bad, [], f'{page} still has inline styles: {bad}')

    def test_checklist_links_to_view_with_add_item_form(self):
        js = open('operations.js').read()
        html = open('operations.html').read()
        m = re.search(r"label:'Add your first item',view:'(\w+)'", js)
        self.assertIsNotNone(m)
        view = m.group(1)
        section = html.split('id="view-%s"' % view, 1)[1]
        self.assertIn('id="add-item"', section.split('<section', 1)[0])
        self.assertIn('on the Buying page', js)
