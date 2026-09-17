import tempfile,unittest
from store import Store
from tax_engine import TaxEngine
class Tax(unittest.TestCase):
 def setUp(self):self.s=Store(tempfile.mktemp());self.w,_=self.s.create_workspace('Global');self.t=TaxEngine(self.s)
 def test_effective_version_and_inclusive_exclusive(self):
  self.t.add_rule(self.w,'accountant','IN','STANDARD','2026.1','2026-01-01','2026-06-30',10,False,verified_by='CA',source_url='https://example.test/rule');self.t.add_rule(self.w,'accountant','IN','STANDARD','2026.2','2026-07-01',None,20,True,verified_by='CA',source_url='https://example.test/rule2');a=self.t.calculate(self.w,'2026-03-01','IN','STANDARD',1000);b=self.t.calculate(self.w,'2026-08-01','IN','STANDARD',1200);self.assertEqual((a['tax_minor'],a['rules_version']),(100,'2026.1'));self.assertEqual((b['net_minor'],b['tax_minor']),(1000,200));self.assertFalse(b['statutory_document_allowed'])
 def test_unverified_or_unsupported_fails_closed(self):
  self.t.add_rule(self.w,'owner','XX','SPECIAL','draft','2026-01-01',None,5)
  with self.assertRaises(Exception):self.t.calculate(self.w,'2026-02-01','XX','SPECIAL',1000)
 def test_representative_jurisdictions_rounding(self):
  for j,r in [('IN',18),('AE',5),('SG',9),('GB',20),('CA',13),('EU-DE',19),('US-CA',7.25)]:
   self.t.add_rule(self.w,'pro',j,'STD','v1','2026-01-01',None,r,False,verified_by='local professional',source_url='https://example.test/'+j);x=self.t.calculate(self.w,'2026-09-01',j,'STD',10000);self.assertEqual(x['gross_minor'],10000+x['tax_minor']);self.assertEqual(x['rules_version'],'v1')
if __name__=='__main__':unittest.main()
