import tempfile,unittest
from store import Store
from operational_profile import Profiles
class ProfilesTest(unittest.TestCase):
 def test_interview_applies_working_module_profile(self):
  s=Store(tempfile.mktemp());w,_=s.create_workspace('Retail');p=Profiles(s).apply(w,'owner',{'vertical':'Electronics','locations':'2–5 stores','credit':'Customer credit','country':'India'});self.assertTrue({'service','serials','transfers','receivables'}<=set(p['enabled_modules']));row=s._db.execute('SELECT operational_profile_hash FROM workspaces WHERE id=?',(w,)).fetchone();self.assertTrue(row['operational_profile_hash'])
if __name__=='__main__':unittest.main()

class CompileProfileHonestyTest(unittest.TestCase):
 def test_customer_only_credit_skips_payables(self):
  from operational_profile import compile_profile
  p=compile_profile({'vertical':'Repairs or services','locations':'One store','credit':'Customer credit','country':'India'})
  m=set(p['enabled_modules']);self.assertIn('receivables',m);self.assertNotIn('payables',m)
 def test_supplier_only_credit_skips_receivables(self):
  from operational_profile import compile_profile
  p=compile_profile({'vertical':'Grocery','locations':'One store','credit':'Supplier credit','country':'India'})
  m=set(p['enabled_modules']);self.assertIn('payables',m);self.assertNotIn('receivables',m)
 def test_no_stock_service_business_skips_inventory_and_gets_service(self):
  from operational_profile import compile_profile
  p=compile_profile({'vertical':'Repairs or services','locations':'One store','credit':'Customer credit','stock_pain':'I do not keep stock','country':'India'})
  m=set(p['enabled_modules']);self.assertNotIn('inventory',m);self.assertIn('service',m)
