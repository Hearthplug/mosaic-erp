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
  self.assertIn('ALTER TABLE oauth_challenges FORCE ROW LEVEL SECURITY',p.PG_MIGRATIONS[2])
  self.assertIn('ALTER TABLE oauth_grants FORCE ROW LEVEL SECURITY',p.PG_MIGRATIONS[2])
  self.assertIn('ALTER TABLE oauth_identities FORCE ROW LEVEL SECURITY',p.PG_MIGRATIONS[2])
  self.assertIn('mosaic_oauth_users',p.PG_MIGRATIONS[2])
 def test_queries_are_portable(self):
  self.assertEqual(p._q('SELECT * FROM x WHERE a=? AND b=?'),'SELECT * FROM x WHERE a=%s AND b=%s')
 def test_pool_prepings_on_checkout(self):
  import inspect
  self.assertIn('check=ConnectionPool.check_connection',inspect.getsource(p.PostgresStore.__init__))
 def test_fresh_retries_acquisition_once(self):
  import psycopg,contextlib
  s=object.__new__(p.PostgresStore)
  class Pool:
   def __init__(s2):s2.calls=0
   def connection(s2):
    s2.calls+=1
    @contextlib.contextmanager
    def cm():
     if s2.calls==1: raise psycopg.OperationalError('stale ssl connection')
     yield 'conn-2'
    return cm()
  s._pool=Pool()
  with s._fresh() as conn:self.assertEqual(conn,'conn-2')
  self.assertEqual(s._pool.calls,2)
 def test_fresh_raises_after_single_retry(self):
  import psycopg,contextlib
  s=object.__new__(p.PostgresStore)
  class Pool:
   def __init__(s2):s2.calls=0
   def connection(s2):
    s2.calls+=1
    @contextlib.contextmanager
    def cm():
     raise psycopg.OperationalError('still down')
     yield
    return cm()
  s._pool=Pool()
  with self.assertRaises(psycopg.OperationalError):
   with s._fresh():pass
  self.assertEqual(s._pool.calls,2)
 def test_fresh_never_retries_body_errors(self):
  import contextlib
  s=object.__new__(p.PostgresStore)
  class Pool:
   def __init__(s2):s2.calls=0
   @contextlib.contextmanager
   def connection(s2):s2.calls+=1;yield 'c'
  s._pool=Pool()
  with self.assertRaises(ValueError):
   with s._fresh():raise ValueError('body')
  self.assertEqual(s._pool.calls,1)
if __name__=='__main__':unittest.main()
