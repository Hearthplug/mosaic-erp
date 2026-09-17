import unittest
import postgres_store as p
class PostgreSQLContract(unittest.TestCase):
 def test_schema_has_rls_and_tenant_keys(self):
  for table in p.TENANT_TABLES:
   self.assertIn('ALTER TABLE '+table+' ENABLE ROW LEVEL SECURITY',p.RLS_SQL)
   self.assertIn('ALTER TABLE '+table+' FORCE ROW LEVEL SECURITY',p.RLS_SQL)
  self.assertIn('PRIMARY KEY(workspace_id,version)',p.PG_MIGRATIONS[0])
  self.assertIn('PRIMARY KEY(key,workspace_id)',p.PG_MIGRATIONS[0])
 def test_session_function_hardens_search_path(self):
  self.assertIn('SECURITY DEFINER SET search_path=public,pg_temp',p.RLS_SQL)
 def test_queries_are_portable(self):
  self.assertEqual(p._q('SELECT * FROM x WHERE a=? AND b=?'),'SELECT * FROM x WHERE a=%s AND b=%s')
if __name__=='__main__':unittest.main()
