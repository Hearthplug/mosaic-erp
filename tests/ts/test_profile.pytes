import unittest
from app import configure,partial,QUESTIONS
BASE={'name':'Asha','vertical':'Grocery','locations':'One store','channels':['In store'],'inventory':'Stockouts','sales':'POS software','credit':'No credit','staff':['Cashiers'],'priority':'Checkout speed'}
class EngineTests(unittest.TestCase):
 def ids(self,a):return {x['id'] for x in configure(a)['modules']}
 def test_interview_is_complete(self):self.assertEqual(len(QUESTIONS),9)
 def test_live_partial_configuration(self):
  p=partial({'name':'Asha','vertical':'Fashion'});self.assertEqual(p['terminology']['items'],'Styles');self.assertGreater(p['completion'],0)
 def test_grocery_language_and_expiry_flow(self):
  r=configure(BASE);self.assertEqual(r['terminology']['customers'],'Shoppers');self.assertTrue(any('Expiry' in x for x in r['workflows']))
 def test_fashion_changes_real_structure(self):
  r=configure(BASE|{'vertical':'Fashion','inventory':'Variants / serials'});self.assertEqual(r['terminology']['items'],'Styles');self.assertEqual(r['terminology']['stock_unit'],'Variant');self.assertIn('Size & colour matrix',[x['name'] for x in r['modules']])
 def test_pharmacy_multistore_omnichannel_credit(self):
  a=BASE|{'vertical':'Pharmacy','locations':'2–5 stores','channels':['In store','WhatsApp / social'],'credit':'Customer + supplier','staff':['Store managers','Accountant']};r=configure(a);self.assertTrue({'network','channel','ledger','team'}<=self.ids(a));self.assertIn('Batch & expiry',[x['name'] for x in r['modules']]);self.assertTrue(any('manager' in x.lower() for x in r['roles']))
 def test_electronics_warranty_and_serials(self):
  r=configure(BASE|{'vertical':'Electronics'});self.assertEqual(r['terminology']['stock_unit'],'Serial');self.assertIn('Serials & warranty',[x['name'] for x in r['modules']])
 def test_beauty_adds_service_model(self):
  r=configure(BASE|{'vertical':'Beauty & wellness'});self.assertIn('Services & appointments',[x['name'] for x in r['modules']]);self.assertIn('Bookings',r['kpis'])
 def test_single_store_has_no_network_module(self):self.assertNotIn('network',self.ids(BASE))
 def test_incomplete_final_rejected(self):
  with self.assertRaises(ValueError):configure({'name':'A'})
if __name__=='__main__':unittest.main()
