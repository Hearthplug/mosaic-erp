"""Runs in CI against PostgreSQL 17 through a NOBYPASSRLS runtime role."""
import os,secrets,threading,unittest
@unittest.skipUnless(os.getenv('MOSAIC_TEST_POSTGRES_URL'),'requires CI PostgreSQL service')
class LivePG(unittest.TestCase):
 @classmethod
 def setUpClass(c):
  from psycopg.conninfo import conninfo_to_dict,make_conninfo
  from postgres_store import PostgresStore
  c.owner=PostgresStore(os.environ['MOSAIC_TEST_POSTGRES_URL'],1,4,True);c.role='mosaic_erp_runtime';secret=secrets.token_urlsafe(24)
  with c.owner._pool.connection() as q:
   q.execute(f'DROP ROLE IF EXISTS {c.role}');q.execute(f"CREATE ROLE {c.role} LOGIN PASSWORD '{secret}' NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS");q.execute(f'GRANT CONNECT ON DATABASE {q.info.dbname} TO {c.role}');q.execute(f'GRANT USAGE ON SCHEMA public TO {c.role}');q.execute(f'GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA public TO {c.role}');q.execute(f'GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA public TO {c.role}');q.execute(f'GRANT EXECUTE ON FUNCTION mosaic_auth_session(text) TO {c.role}')
  parts=conninfo_to_dict(os.environ['MOSAIC_TEST_POSTGRES_URL']);parts.update(user=c.role,password=secret);c.s=PostgresStore(make_conninfo(**parts),1,8,False)
 @classmethod
 def tearDownClass(c):
  c.s.close()
  with c.owner._pool.connection() as q:q.execute(f'DROP OWNED BY {c.role}');q.execute(f'DROP ROLE IF EXISTS {c.role}')
  c.owner.close()
 def test_all_tables_created_rls_forced_and_cross_tenant_hidden(self):
  from postgres_erp_schema import ALL_ERP_TABLES
  with self.owner._pool.connection() as q:
   rows=q.execute("SELECT c.relname,c.relrowsecurity,c.relforcerowsecurity FROM pg_class c WHERE c.relname=ANY(%s)",(list(ALL_ERP_TABLES),)).fetchall();self.assertEqual({r['relname'] for r in rows},ALL_ERP_TABLES);self.assertTrue(all(r['relrowsecurity'] and r['relforcerowsecurity'] for r in rows))
  wa,_=self.s.create_workspace('A');wb,_=self.s.create_workspace('B')
  with self.s.tx():self.s._db.execute("SELECT set_config('mosaic.workspace_id',%s,true)",(wa,));self.s._db.execute('INSERT INTO locations(id,workspace_id,code,name,kind,active) VALUES(?,?,?,?,?,?)',('loc_a',wa,'A','A','store',1))
  with self.s.tx():self.s._db.execute("SELECT set_config('mosaic.workspace_id',%s,true)",(wb,));self.assertIsNone(self.s._db.execute('SELECT id FROM locations WHERE id=?',('loc_a',)).fetchone())
 def test_advisory_lock_serializes_number_allocation(self):
  w,_=self.s.create_workspace('C');seen=[]
  def worker():
   with self.s.tx():self.s._db.execute("SELECT set_config('mosaic.workspace_id',%s,true)",(w,));self.s.accounting_lock(w,'number');seen.append(1)
  ts=[threading.Thread(target=worker) for _ in range(4)];[t.start() for t in ts];[t.join() for t in ts];self.assertEqual(len(seen),4)
if __name__=='__main__':unittest.main()
