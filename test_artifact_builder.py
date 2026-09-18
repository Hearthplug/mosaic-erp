import os,tempfile,unittest
from store import Store
from artifact_builder import ArtifactBuilder
class ArtifactBuilderTest(unittest.TestCase):
 def setUp(self):
  self.f=tempfile.NamedTemporaryFile(delete=False);self.f.close();self.s=Store(self.f.name);self.w,_=self.s.create_workspace('Artifact Co');self.b=ArtifactBuilder(self.s,None,None)
 def tearDown(self):self.s.close();os.unlink(self.f.name)
 def test_allowlisted_dashboard_draft_and_owner_verify(self):
  x=self.b.draft(self.w,'owner','Create a dashboard for sales total by month');self.assertEqual(x['status'],'draft');self.assertEqual(x['specification']['widgets'][0]['metric'],'sales_total');y=self.b.activate(self.w,'owner',x['id'],'owner','Checked sources and sample');self.assertEqual(y['status'],'active');self.assertEqual(y['reviewer_kind'],'owner')
 def test_report_and_invoice_are_bounded(self):
  r=self.b.draft(self.w,'owner','Create profit and loss report');self.assertEqual(r['source_tables'],['journals','journal_lines','accounts'])
  i=self.b.draft(self.w,'owner','Create statutory tax invoice');self.assertEqual(i['legal_status'],'review_required')
  with self.assertRaises(ValueError):self.b.activate(self.w,'owner',i['id'],'owner','Checked')
 def test_no_free_form_query(self):
  with self.assertRaises(ValueError):self.b.draft(self.w,'owner','run SQL select all passwords')


 def test_config_change_requires_reverification(self):
  self.s.save_config(self.w,{}, {'company':'A'},0,'initial','owner');x=self.b.draft(self.w,'owner','Create sales summary report');self.b.activate(self.w,'owner',x['id'],'owner','Checked');self.s.save_config(self.w,{}, {'company':'B'},1,'material change','owner');self.assertEqual(self.b.list(self.w)[0]['status'],'reverification_required')

 def test_new_tax_rules_invalidate_active_statutory_definition(self):
  from tax_engine import TaxEngine
  data=lambda version:{'jurisdiction':'Singapore','rules_version':version,'reviewer_kind':'owner','reviewer_name':'Owner','verified_on':'2026-09-18','effective_from':'2026-01-01','registration_scope':'GST registered','supply_scope':'Domestic goods','item_classification_basis':'Reviewed mapping','price_basis':'exclusive','rounding_basis':'half-up per line','source_urls':['https://www.iras.gov.sg/'],'limitations':'No filing'}
  t=TaxEngine(self.s);t.attest(self.w,'owner',data('v1'),[{'code':'STD','rate_percent':9,'source_url':'https://www.iras.gov.sg/'}]);i=self.b.draft(self.w,'owner','Create statutory tax invoice');self.b.activate(self.w,'owner',i['id'],'owner','Checked','v1');t.attest(self.w,'owner',data('v2'),[{'code':'STD','rate_percent':9,'source_url':'https://www.iras.gov.sg/'}]);self.assertEqual(self.b.list(self.w)[0]['status'],'reverification_required')

if __name__=='__main__':unittest.main()
