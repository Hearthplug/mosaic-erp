import tempfile,unittest
from store import Store,Conflict
from accounting import Accounting
from tax_engine import TaxEngine
from tax_pack_operational import candidate
class Verification(unittest.TestCase):
 def setUp(self):self.s=Store(tempfile.mktemp());self.w,_=self.s.create_workspace('X');Accounting(self.s).setup(self.w,'owner');self.t=TaxEngine(self.s)
 def data(self,price='exclusive'):return {'jurisdiction':'Singapore','rules_version':'review-1','reviewer_kind':'owner','reviewer_name':'Business owner','credentials':'','verified_on':'2026-09-18','effective_from':'2026-01-01','registration_scope':'GST registered domestic retailer','supply_scope':'Domestic B2C goods only','item_classification_basis':'Reviewed SKU mapping v1','price_basis':price,'rounding_basis':'half-up per line','source_urls':['https://www.iras.gov.sg/'],'limitations':'No exports, reverse charge, filing or e-invoicing'}
 def test_incomplete_verification_fails_closed(self):
  with self.assertRaises(ValueError):self.t.attest(self.w,'owner',{},[])
  with self.assertRaises(Conflict):self.t.calculate(self.w,'2026-09-18','Singapore','STD',1000)
 def test_attestation_enables_only_reviewed_math_not_statutory_output(self):
  a=self.t.attest(self.w,'owner',self.data(),[{'code':'STD','rate_percent':9,'source_url':'https://www.iras.gov.sg/'}]);self.assertEqual(a['statutory_adapter_state'],'disabled');self.assertEqual(a['reviewer_kind'],'owner');self.assertTrue(a['professional_review_recommended'])
  out=self.t.regression(self.w,'Singapore',[{'name':'exclusive','transaction_date':'2026-09-18','code':'STD','amount_minor':1000,'net_minor':1000,'tax_minor':90,'gross_minor':1090}]);self.assertTrue(out['passed']);self.assertFalse(out['statutory_document_allowed'])
 def test_inclusive_rounding_regression(self):
  self.t.attest(self.w,'owner',self.data('inclusive'),[{'code':'STD','rate_percent':9,'source_url':'https://www.iras.gov.sg/'}]);out=self.t.regression(self.w,'Singapore',[{'transaction_date':'2026-09-18','code':'STD','amount_minor':1090,'net_minor':1000,'tax_minor':90,'gross_minor':1090}]);self.assertTrue(out['passed'])
 def test_every_candidate_produces_explicit_review_checklist(self):
  for country in ('India','UAE','Singapore','United States','European Union'):
   x=self.t.verification_checklist(candidate(country));self.assertGreaterEqual(len(x['must_verify']),10);self.assertEqual(x['statutory_adapter_state'],'disabled');self.assertTrue(x['sources'])
if __name__=='__main__':unittest.main()
