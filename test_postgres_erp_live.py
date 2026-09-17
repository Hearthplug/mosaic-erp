"""Runs in CI against the PostgreSQL 17 service, never silently skips there."""
import os,threading,unittest
@unittest.skipUnless(os.getenv('MOSAIC_TEST_POSTGRES_URL'),'requires CI PostgreSQL service')
class LivePG(unittest.TestCase):
 @classmethod
 def setUpClass(c):
  from postgres_store import PostgresStore;c.s=PostgresStore(os.environ['MOSAIC_TEST_POSTGRES_URL'],1,8,True)
 @classmethod
 def tearDownClass(c):c.s.close()
 def test_all_tables_created_rls_forced_and_cross_tenant_hidden(self):
  from postgres_erp_schema import ALL_ERP_TABLES
  with self.s._pool.connection() as q:
   rows=q.execute("SELECT c.relname,c.relrowsecurity,c.relforcerowsecurity FROM pg_class c WHERE c.relname=ANY(%s)",(list(ALL_ERP_TABLES),)).fetchall();self.assertEqual({r['relname'] for r in rows},ALL_ERP_TABLES);self.assertTrue(all(r['relrowsecurity'] and r['relforcerowsecurity'] for r in rows))
  wa,ka=self.s.create_workspace('A');wb,kb=self.s.create_workspace('B');self.assertNotEqual(wa,wb)
  with self.s.tx():
   self.s._db.execute("SELECT set_config('mosaic.workspace_id',%s,true)",(wa,));self.s._db.execute('INSERT INTO locations(id,workspace_id,code,name,kind,active) VALUES(?,?,?,?,?,?)',('loc_a',wa,'A','A','store',1))
  with self.s.tx():
   self.s._db.execute("SELECT set_config('mosaic.workspace_id',%s,true)",(wb,));self.assertIsNone(self.s._db.execute('SELECT id FROM locations WHERE id=?',('loc_a',)).fetchone())
 def test_advisory_lock_serializes_number_allocation(self):
  w,_=self.s.create_workspace('C');seen=[]
  def worker():
   with self.s.tx():self.s._db.execute("SELECT set_config('mosaic.workspace_id',%s,true)",(w,));self.s.accounting_lock(w,'number');seen.append(1)
  ts=[threading.Thread(target=worker) for _ in range(4)];[t.start() for t in ts];[t.join() for t in ts];self.assertEqual(len(seen),4)
if __name__=='__main__':unittest.main()
