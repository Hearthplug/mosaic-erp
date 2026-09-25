import os,secrets,threading,unittest
try:
 from psycopg.conninfo import conninfo_to_dict, make_conninfo
 from postgres_store import PostgresStore
except ImportError:
 PostgresStore=None
class PostgreSQLIntegration(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  url=os.getenv('MOSAIC_TEST_POSTGRES_URL')
  if not url: raise unittest.SkipTest('MOSAIC_TEST_POSTGRES_URL not set')
  cls.owner=PostgresStore(url,min_size=1,max_size=4)
  cls.role='mosaic_ci_runtime'; runtime_secret=secrets.token_urlsafe(24)
  with cls.owner._pool.connection() as conn:
   conn.execute(f'DROP ROLE IF EXISTS {cls.role}')
   conn.execute(f"CREATE ROLE {cls.role} LOGIN PASSWORD '{runtime_secret}' NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS")
   conn.execute(f'GRANT CONNECT ON DATABASE {conn.info.dbname} TO {cls.role}')
   conn.execute(f'GRANT USAGE ON SCHEMA public TO {cls.role}')
   conn.execute(f'GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA public TO {cls.role}')
   conn.execute(f'GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA public TO {cls.role}')
   conn.execute(f'GRANT EXECUTE ON FUNCTION mosaic_auth_session(text) TO {cls.role}');conn.execute(f'GRANT EXECUTE ON FUNCTION mosaic_login_options(text) TO {cls.role}');conn.execute(f'GRANT EXECUTE ON FUNCTION mosaic_invitation(text) TO {cls.role}');conn.execute(f'GRANT EXECUTE ON FUNCTION mosaic_session_workspace(text,text) TO {cls.role}');conn.execute(f'GRANT EXECUTE ON FUNCTION mosaic_oauth_users(text,text,text) TO {cls.role}')
  parts=conninfo_to_dict(url);parts.update(user=cls.role,password=runtime_secret)
  cls.s=PostgresStore(make_conninfo(**parts),min_size=1,max_size=8,auto_migrate=False)
 @classmethod
 def tearDownClass(cls):
  cls.s.close()
  with cls.owner._pool.connection() as conn:
   conn.execute(f'DROP OWNED BY {cls.role}')
   conn.execute(f'DROP ROLE IF EXISTS {cls.role}')
  cls.owner.close()
 def test_crud_idempotency_audit_and_isolation(self):
  a,ka=self.s.create_workspace('A');b,kb=self.s.create_workspace('B')
  aa=self.s.authenticate(ka);bb=self.s.authenticate(kb);self.assertEqual(aa[0],a);self.assertEqual(bb[0],b)
  r,replay=self.s.save_config(a,{}, {'v':1},0,'first',aa[1],idem_key='x',request_hash='h');self.assertFalse(replay)
  r2,replay=self.s.save_config(a,{}, {'v':1},0,'first',aa[1],idem_key='x',request_hash='h');self.assertTrue(replay);self.assertEqual(r,r2)
  with self.assertRaises(Exception): self.s.get_config(b)
  self.assertEqual(self.s.get_config(a)['config'],{'v':1});self.assertEqual(self.s.audit_trail(a)[0]['action'],'config.save')
 def test_runtime_role_password_session_and_oauth_grants(self):
  w,_=self.s.create_workspace('Runtime sign in');self.s.create_user(w,'runtime@example.test','a secure long password','owner','test')
  options=self.s.login_options('runtime@example.test','a secure long password');self.assertEqual(options[0]['workspace_id'],w)
  login=self.s.login(w,'runtime@example.test','a secure long password')
  self.assertEqual(self.s.authenticate_session(login['session_token'])[:3],(w,login['user_id'],'owner'))
  self.s.revoke_session(self.s.authenticate_session(login['session_token'])[3],login['user_id'])
  self.assertIsNone(self.s.authenticate_session(login['session_token']))
  state='state-'+secrets.token_urlsafe(16)
  self.s.oauth_challenge_create(state,'google','nonce','verifier','/interview')
  self.assertIsNotNone(self.s.oauth_challenge_consume(state,'google'))
  self.assertIsNone(self.s.oauth_challenge_consume(state,'google'))
  code,_=self.s.oauth_grant_create('google','https://accounts.google.com','subject','runtime@example.test',True,'/interview','signin')
  self.assertIsNotNone(self.s.oauth_grant_consume(code,'signin'))
  self.assertIsNone(self.s.oauth_grant_consume(code,'signin'))
  invite=self.s.create_invitation(w,'invited@example.test','viewer',None,login['user_id'])
  self.assertEqual(self.s.invitation(invite['invite_token'])['workspace_id'],w)
 def test_concurrent_writers_only_one_wins(self):
  w,k=self.s.create_workspace('C');actor=self.s.authenticate(k)[1];out=[]
  def f(v):
   try: out.append(('ok',self.s.save_config(w,{}, {'v':v},0,'',actor)[0]))
   except Exception as e: out.append(('err',type(e).__name__))
  ts=[threading.Thread(target=f,args=(i,)) for i in range(2)]
  [t.start() for t in ts];[t.join() for t in ts]
  self.assertEqual([x[0] for x in out].count('ok'),1);self.assertEqual(len(self.s.list_versions(w)),1)
 def test_forced_rls_denies_cross_tenant_sql(self):
  a,_=self.s.create_workspace('RLS-A');b,_=self.s.create_workspace('RLS-B')
  with self.s.tx():
   self.s._db.execute("SELECT set_config('mosaic.workspace_id',%s,true)",(a,))
   self.assertIsNone(self.s._current().execute('SELECT id FROM workspaces WHERE id=%s',(b,)).fetchone())
if __name__=='__main__':unittest.main()
