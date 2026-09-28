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
 def test_owner_toggles_modules_and_apply_uses_exactly_the_reviewed_set(self):
  import json
  for q in self.o.get(self.w,self.x)['questions']:self.o.answer(self.w,'owner',self.x,q['key'],q.get('options',[None])[0] if q['type']!='text' else 'Ravi Stores')
  d=self.o.get(self.w,self.x);self.assertEqual(d['status'],'ready')
  reviewed={m['key']:m['enabled'] for m in d['inference']['module_review']}
  self.assertTrue(reviewed['inventory'])
  d=self.o.set_modules(self.w,'owner',self.x,{'inventory':False,'manufacturing':True})
  now={m['key']:m['enabled'] for m in d['inference']['module_review']}
  self.assertFalse(now['inventory']);self.assertTrue(now['manufacturing'])
  self.assertEqual(d['inference']['module_overrides'],{'inventory':False,'manufacturing':True})
  res=self.o.apply(self.w,'owner',self.x)
  self.assertNotIn('inventory',res['profile']['enabled_modules'])
  self.assertIn('manufacturing',res['profile']['enabled_modules'])
  ws=json.loads(self.o.s._db.execute('SELECT operational_profile_json FROM workspaces WHERE id=?',(self.w,)).fetchone()[0])
  self.assertNotIn('inventory',ws['enabled_modules']);self.assertIn('manufacturing',ws['enabled_modules'])
 def test_toggling_back_to_the_inferred_state_clears_the_override(self):
  for q in self.o.get(self.w,self.x)['questions']:self.o.answer(self.w,'owner',self.x,q['key'],q.get('options',[None])[0] if q['type']!='text' else 'Ravi Stores')
  self.o.set_modules(self.w,'owner',self.x,{'inventory':False})
  d=self.o.set_modules(self.w,'owner',self.x,{'inventory':True})
  self.assertEqual(d['inference']['module_overrides'],{})
  self.assertTrue({m['key']:m['enabled'] for m in d['inference']['module_review']}['inventory'])
 def test_unknown_module_keys_are_rejected(self):
  with self.assertRaises(ValueError):self.o.set_modules(self.w,'owner',self.x,{'warp_drive':True})
if __name__=='__main__':unittest.main()
