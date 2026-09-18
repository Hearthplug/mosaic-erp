import unittest
from tax_pack_operational import all_candidates
class AllPacks(unittest.TestCase):
 def test_all_22_are_versioned_sourced_and_fail_closed(self):
  x=all_candidates();self.assertEqual(len(x),22)
  for country,p in x.items():
   self.assertEqual(p['verification_state'],'requires_owner_or_professional_review',country);self.assertEqual(p['statutory_adapter_state'],'disabled',country);self.assertTrue(p['sources'],country);self.assertTrue(p['pack_hash'],country);self.assertEqual(p['schema_version'],1)
 def test_candidates_never_masquerade_as_verified_rules(self):
  for p in all_candidates().values():
   for r in p['candidate_rules']:self.assertEqual(r['scope'],'candidate_only');self.assertIsNone(r['price_includes_tax'])
if __name__=='__main__':unittest.main()
