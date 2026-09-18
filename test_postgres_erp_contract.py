import unittest
import postgres_erp_schema as p
class PGContract(unittest.TestCase):
 def test_every_erp_table_has_force_rls_policy(self):
  sql=p.POSTGRES_ERP_MIGRATION
  for t in p.ALL_ERP_TABLES:
   self.assertIn(f'ALTER TABLE {t} FORCE ROW LEVEL SECURITY',sql)
   self.assertIn(f'CREATE POLICY {t}_tenant',sql)
 def test_immutability_and_no_silent_sqlite_syntax(self):
  s=p.POSTGRES_ERP_MIGRATION;self.assertIn('mosaic_immutable_posted',s);self.assertNotIn('RAISE(ABORT',s);self.assertNotIn('AUTOINCREMENT',s);self.assertNotIn('INSERT OR REPLACE',s)
 def test_full_table_set_not_partial(self):
  self.assertGreaterEqual(len(p.ALL_ERP_TABLES),40);self.assertTrue({'documents','journal_lines','stock_ledger','sales','purchase_orders','onboarding_sessions','role_assignments'}<=p.ALL_ERP_TABLES)
if __name__=='__main__':unittest.main()
