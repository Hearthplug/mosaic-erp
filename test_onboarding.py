import tempfile,unittest
from store import Store
from operational_profile import Profiles
from onboarding import Onboarding,QUESTIONS
class OwnerInterview(unittest.TestCase):
 def setUp(self):self.s=Store(tempfile.mktemp());self.w,_=self.s.create_workspace('Owner');self.o=Onboarding(self.s,Profiles(self.s));self.x=self.o.start(self.w,'owner')['id']
 def test_low_tech_owner_answers_save_resume_explain_and_apply(self):
  answers={'business_name':'Ravi Stores','vertical':'Electronics','locations':'2 to 5 places','selling':'People walk in, choose a phone and pay cash','buying':'My manager approves, staff check each delivery','stock_pain':'Serial numbers or warranty','credit_behavior':'Everything is paid immediately','discounts':'Cashier up to 5%, manager above','returns':'Manager checks it, then refund and restock if unopened','staff':'Cashiers sell, manager approves, accountant sees books','money_view':['Sales','Cash counted','Profit'],'country':'Registered in India and sell in Karnataka','selling_locations':['Near my registered business'],'buying_locations':['Nearby suppliers'],'price_display':'Tax is included in the shown price','customer_type':'Households','product_tax_facts':'Phones use the standard rate; accountant checks accessories','brand_style':'Clean and professional','brand_colors':'Blue and white','logo':'No, use the business name for now','screen_preference':'Start selling','existing_records':'Spreadsheets','exceptions':'Warranty returns','goal':'Know correct stock at every branch'}
  for k,v in answers.items():d=self.o.answer(self.w,'owner',self.x,k,v)
  self.assertEqual(d['status'],'ready');self.assertTrue(any(x['enabled']=='serials' for x in d['inference']['explanations']));self.assertTrue(d['inference']['professional_verification']);self.assertEqual(self.o.get(self.w,self.x)['answers']['business_name'],'Ravi Stores');self.assertIn('profile',self.o.apply(self.w,'owner',self.x))
 def test_contradiction_is_plain_language(self):
  self.o.answer(self.w,'owner',self.x,'credit_behavior','Everything is paid immediately');d=self.o.answer(self.w,'owner',self.x,'selling','They take it now and pay later on monthly credit');self.assertEqual(d['status'],'needs_review');self.assertIn('Which happens in real life?',d['contradictions'][0]['message'])
 def test_no_question_asks_for_modules_or_technology(self):
  text=' '.join(q['text'].lower() for q in QUESTIONS)
  for forbidden in ('module','database','docker','kubernetes','api','chart of accounts','debit','credit account'):self.assertNotIn(forbidden,text)
if __name__=='__main__':unittest.main()
