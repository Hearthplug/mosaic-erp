import tempfile,unittest
from store import Store
from operational_profile import Profiles
from onboarding import Onboarding,QUESTIONS
from provisioning import Provisioner
class Provisioning(unittest.TestCase):
 def test_interview_apply_provisions_capabilities_roles_brand_reports_and_tasks(self):
  s=Store(tempfile.mktemp());w,_=s.create_workspace('X');p=Provisioner(s);o=Onboarding(s,Profiles(s),p);x=o.start(w,'owner')['id']
  answers={'business_name':'Ravi','vertical':'Electronics','locations':'2 to 5 places','selling':'Walk in and pay cash','buying':'Buyer orders, receiver checks','stock_pain':'Serial numbers or warranty','credit_behavior':'Everything is paid immediately','discounts':'Manager above 5%','returns':'Manager checks','staff':'Cashier, buyer, receiver, accountant','money_view':['Sales','Profit'],'country':'India','selling_locations':['Near my registered business'],'buying_locations':['Nearby suppliers'],'price_display':'Tax is included in the shown price','customer_type':'Households','product_tax_facts':'Accountant maps HSN','existing_records':'Spreadsheets','exceptions':'Warranty','brand_style':'Clean and professional','brand_colors':'#112233 and #ffcc00','logo':'No, use the business name for now','screen_preference':'Start selling','goal':'Correct stock'}
  for q in QUESTIONS:o.answer(w,'owner',x,q['key'],answers[q['key']])
  out=o.apply(w,'owner',x)['provisioned'];self.assertIn('serials',out['modules']);self.assertIn('transfers',out['modules']);self.assertIn('trial_balance',out['reports']);self.assertEqual(out['branding']['primary'],'#112233');self.assertTrue(any(x['role']=='Cashier' for x in out['roles']));self.assertGreater(len(out['verification_tasks']),3);self.assertFalse(out['go_live_ready'])
  status=p.status(w);self.assertTrue(status['capabilities']);self.assertFalse(status['go_live_ready'])
if __name__=='__main__':unittest.main()
