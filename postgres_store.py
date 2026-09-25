"""PostgreSQL production store with the same application contract as SQLite.

The runtime uses a bounded psycopg pool. Every tenant operation sets a
transaction-local ``mosaic.workspace_id`` and PostgreSQL RLS is forced on all
tenant tables. Migrations are serialized with an advisory lock.
"""
from __future__ import annotations
import contextlib, json, os, re, threading
from pathlib import Path
from psycopg import sql
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from store import Store, MIGRATIONS, Conflict, NotFound
from postgres_erp_schema import POSTGRES_ERP_MIGRATION, ALL_ERP_TABLES, ASSISTANT_PREVIEW_PG
from billing_schema import POSTGRES_BILLING_SCHEMA

SCHEMA_VERSION = 1
PG_MIGRATIONS = [r'''
CREATE TABLE workspaces(id text PRIMARY KEY,name text NOT NULL,created_at text NOT NULL,status text NOT NULL DEFAULT 'active');
CREATE TABLE api_keys(id text PRIMARY KEY,workspace_id text NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,label text NOT NULL DEFAULT '',role text NOT NULL CHECK(role IN ('viewer','editor','owner')),key_hash text NOT NULL UNIQUE,created_at text NOT NULL,revoked_at text);
CREATE TABLE config_versions(workspace_id text NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,version integer NOT NULL,answers_json text NOT NULL,config_json text NOT NULL,checksum text NOT NULL,summary text NOT NULL DEFAULT '',actor_key_id text,created_at text NOT NULL,PRIMARY KEY(workspace_id,version));
CREATE TABLE audit_events(id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,workspace_id text NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,at text NOT NULL,actor_key_id text,action text NOT NULL,detail_json text NOT NULL);
CREATE INDEX idx_audit_ws ON audit_events(workspace_id,id);
CREATE TABLE idempotency_keys(key text NOT NULL,workspace_id text NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,endpoint text NOT NULL,request_hash text NOT NULL,status integer NOT NULL,response_json text NOT NULL,created_at text NOT NULL,PRIMARY KEY(key,workspace_id));
CREATE TABLE users(id text PRIMARY KEY,workspace_id text NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,email text NOT NULL,password_hash text NOT NULL,role text NOT NULL CHECK(role IN ('viewer','editor','owner')),created_at text NOT NULL,disabled_at text,UNIQUE(workspace_id,email));
CREATE TABLE sessions(id text PRIMARY KEY,user_id text NOT NULL REFERENCES users(id) ON DELETE CASCADE,token_hash text NOT NULL UNIQUE,created_at text NOT NULL,expires_at text NOT NULL,revoked_at text);
CREATE TABLE rate_buckets(identity text PRIMARY KEY,tokens double precision NOT NULL,updated_at double precision NOT NULL);
''', POSTGRES_ERP_MIGRATION, r'''
CREATE TABLE oauth_challenges(state_hash text PRIMARY KEY,provider text NOT NULL,nonce text NOT NULL,code_verifier text NOT NULL,next_path text NOT NULL,invite_token text NOT NULL DEFAULT '',created_at text NOT NULL,expires_at text NOT NULL,used_at text);
CREATE TABLE oauth_identities(provider text NOT NULL,issuer text NOT NULL,subject text NOT NULL,user_id text NOT NULL REFERENCES users(id) ON DELETE CASCADE,workspace_id text NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,created_at text NOT NULL,PRIMARY KEY(provider,issuer,subject,workspace_id),UNIQUE(provider,issuer,subject,user_id));
CREATE INDEX idx_oauth_identity_user ON oauth_identities(user_id);
ALTER TABLE oauth_challenges ENABLE ROW LEVEL SECURITY; ALTER TABLE oauth_challenges FORCE ROW LEVEL SECURITY;
CREATE POLICY oauth_challenges_secret ON oauth_challenges USING (state_hash=current_setting('mosaic.oauth_state_hash',true)) WITH CHECK (state_hash=current_setting('mosaic.oauth_state_hash',true));
CREATE TABLE oauth_grants(code_hash text PRIMARY KEY,provider text NOT NULL,issuer text NOT NULL,subject text NOT NULL,email text NOT NULL,email_verified integer NOT NULL,mode text NOT NULL CHECK(mode IN ('signin','link','enter')),next_path text NOT NULL,created_at text NOT NULL,expires_at text NOT NULL,used_at text);
ALTER TABLE oauth_grants ENABLE ROW LEVEL SECURITY; ALTER TABLE oauth_grants FORCE ROW LEVEL SECURITY;
CREATE POLICY oauth_grants_secret ON oauth_grants USING (code_hash=current_setting('mosaic.oauth_grant_hash',true)) WITH CHECK (code_hash=current_setting('mosaic.oauth_grant_hash',true));
ALTER TABLE oauth_identities ENABLE ROW LEVEL SECURITY; ALTER TABLE oauth_identities FORCE ROW LEVEL SECURITY;
CREATE POLICY oauth_identities_tenant ON oauth_identities USING (workspace_id=current_setting('mosaic.workspace_id',true)) WITH CHECK (workspace_id=current_setting('mosaic.workspace_id',true));
CREATE OR REPLACE FUNCTION mosaic_oauth_users(p_provider text,p_issuer text,p_subject text) RETURNS TABLE(id text,workspace_id text,email text,role text,name text) LANGUAGE sql SECURITY DEFINER SET search_path=public,pg_temp AS $$ SELECT u.id,u.workspace_id,u.email,u.role,w.name FROM oauth_identities i JOIN users u ON u.id=i.user_id JOIN workspaces w ON w.id=u.workspace_id WHERE i.provider=p_provider AND i.issuer=p_issuer AND i.subject=p_subject AND u.disabled_at IS NULL AND w.status='active' $$;
REVOKE ALL ON FUNCTION mosaic_oauth_users(text,text,text) FROM PUBLIC; GRANT EXECUTE ON FUNCTION mosaic_oauth_users(text,text,text) TO CURRENT_USER;
''', ASSISTANT_PREVIEW_PG ]

# Additive migration for a single invitation bearer lookup before workspace context.
PG_MIGRATIONS.append(r'''
CREATE OR REPLACE FUNCTION mosaic_invitation(p_hash text) RETURNS TABLE(id text,workspace_id text,email text,role text,operational_role text,expires_at text,accepted_at text,revoked_at text) LANGUAGE sql SECURITY DEFINER SET search_path=public,pg_temp AS $$ SELECT i.id,i.workspace_id,i.email,i.role,i.operational_role,i.expires_at,i.accepted_at,i.revoked_at FROM workspace_invitations i WHERE i.token_hash=p_hash $$;
REVOKE ALL ON FUNCTION mosaic_invitation(text) FROM PUBLIC; GRANT EXECUTE ON FUNCTION mosaic_invitation(text) TO CURRENT_USER;
CREATE OR REPLACE FUNCTION mosaic_session_workspace(p_id text,p_user text) RETURNS text LANGUAGE sql SECURITY DEFINER SET search_path=public,pg_temp AS $$ SELECT u.workspace_id FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.id=p_id AND u.id=p_user $$;
REVOKE ALL ON FUNCTION mosaic_session_workspace(text,text) FROM PUBLIC; GRANT EXECUTE ON FUNCTION mosaic_session_workspace(text,text) TO CURRENT_USER;
''')
PG_MIGRATIONS.append(POSTGRES_BILLING_SCHEMA)

TENANT_TABLES=('workspaces','api_keys','config_versions','audit_events','idempotency_keys','users')
RLS_SQL=r'''
ALTER TABLE workspaces ENABLE ROW LEVEL SECURITY; ALTER TABLE workspaces FORCE ROW LEVEL SECURITY;
CREATE POLICY workspace_tenant ON workspaces USING (id=current_setting('mosaic.workspace_id',true)) WITH CHECK (id=current_setting('mosaic.workspace_id',true));
ALTER TABLE api_keys ENABLE ROW LEVEL SECURITY; ALTER TABLE api_keys FORCE ROW LEVEL SECURITY;
CREATE POLICY api_keys_tenant ON api_keys USING (workspace_id=current_setting('mosaic.workspace_id',true) OR key_hash=current_setting('mosaic.auth_key_hash',true)) WITH CHECK (workspace_id=current_setting('mosaic.workspace_id',true));
ALTER TABLE config_versions ENABLE ROW LEVEL SECURITY; ALTER TABLE config_versions FORCE ROW LEVEL SECURITY;
CREATE POLICY config_versions_tenant ON config_versions USING (workspace_id=current_setting('mosaic.workspace_id',true)) WITH CHECK (workspace_id=current_setting('mosaic.workspace_id',true));
ALTER TABLE audit_events ENABLE ROW LEVEL SECURITY; ALTER TABLE audit_events FORCE ROW LEVEL SECURITY;
CREATE POLICY audit_events_tenant ON audit_events USING (workspace_id=current_setting('mosaic.workspace_id',true)) WITH CHECK (workspace_id=current_setting('mosaic.workspace_id',true));
ALTER TABLE idempotency_keys ENABLE ROW LEVEL SECURITY; ALTER TABLE idempotency_keys FORCE ROW LEVEL SECURITY;
CREATE POLICY idempotency_tenant ON idempotency_keys USING (workspace_id=current_setting('mosaic.workspace_id',true)) WITH CHECK (workspace_id=current_setting('mosaic.workspace_id',true));
ALTER TABLE users ENABLE ROW LEVEL SECURITY; ALTER TABLE users FORCE ROW LEVEL SECURITY;
CREATE POLICY users_tenant ON users USING (workspace_id=current_setting('mosaic.workspace_id',true)) WITH CHECK (workspace_id=current_setting('mosaic.workspace_id',true));

CREATE OR REPLACE FUNCTION mosaic_login_options(p_email text) RETURNS TABLE(workspace_id text,password_hash text,role text,name text) LANGUAGE sql SECURITY DEFINER SET search_path=public,pg_temp AS $$ SELECT u.workspace_id,u.password_hash,u.role,w.name FROM users u JOIN workspaces w ON w.id=u.workspace_id WHERE u.email=p_email AND u.disabled_at IS NULL AND w.status='active' $$;
REVOKE ALL ON FUNCTION mosaic_login_options(text) FROM PUBLIC; GRANT EXECUTE ON FUNCTION mosaic_login_options(text) TO CURRENT_USER;
CREATE OR REPLACE FUNCTION mosaic_auth_session(p_hash text) RETURNS TABLE(id text,user_id text,workspace_id text,role text,expires_at text) LANGUAGE sql SECURITY DEFINER SET search_path=public,pg_temp AS $$ SELECT s.id,u.id,u.workspace_id,u.role,s.expires_at FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=p_hash AND s.revoked_at IS NULL AND u.disabled_at IS NULL $$;
REVOKE ALL ON FUNCTION mosaic_auth_session(text) FROM PUBLIC; GRANT EXECUTE ON FUNCTION mosaic_auth_session(text) TO CURRENT_USER;
CREATE OR REPLACE FUNCTION mosaic_parent_workspace(p_table text,p_id text) RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path=public,pg_temp AS $$ DECLARE w text; BEGIN IF p_table NOT IN ('purchase_orders','sales','retail_returns','stock_counts','documents') THEN RAISE EXCEPTION 'unsupported parent'; END IF; EXECUTE format('SELECT workspace_id FROM %I WHERE id=$1',p_table) INTO w USING p_id; RETURN w; END $$;
REVOKE ALL ON FUNCTION mosaic_parent_workspace(text,text) FROM PUBLIC; GRANT EXECUTE ON FUNCTION mosaic_parent_workspace(text,text) TO CURRENT_USER;
ALTER TABLE sessions ENABLE ROW LEVEL SECURITY; ALTER TABLE sessions FORCE ROW LEVEL SECURITY;
CREATE POLICY sessions_tenant ON sessions USING (EXISTS (SELECT 1 FROM users u WHERE u.id=sessions.user_id AND u.workspace_id=current_setting('mosaic.workspace_id',true)) OR token_hash=current_setting('mosaic.auth_session_hash',true)) WITH CHECK (EXISTS (SELECT 1 FROM users u WHERE u.id=sessions.user_id AND u.workspace_id=current_setting('mosaic.workspace_id',true)));
'''

def _q(q):
    return q.replace('?', '%s')

def _context(sql_text, params):
    vals=[str(x) for x in (params or ()) if x is not None]
    wid=next((x for x in vals if x.startswith('wsp_')),None)
    if 'api_keys WHERE key_hash=' in sql_text and vals: return ('mosaic.auth_key_hash',vals[0])
    if 'sessions s JOIN users' in sql_text and vals: return ('mosaic.auth_session_hash',vals[0])
    if not wid:
        # Child-table queries often carry only a parent id. Recover the tenant
        # from the parent while the connection is still outside tenant scope.
        child_parents={'purchase_order_lines':('purchase_orders','purchase_order_id'),'sale_lines':('sales','sale_id'),'retail_return_lines':('retail_returns','return_id'),'stock_count_lines':('stock_counts','stock_count_id'),'document_lines':('documents','document_id')}
        low=sql_text.lower()
        for child,(parent,fk) in child_parents.items():
            if child in low and vals:
                # When the query also filters the child id, the parent foreign
                # key is the later parameter (id=? AND parent_id=?).
                parent_id=vals[-1] if fk in low and len(vals)>1 else vals[0]
                return ('mosaic.parent_context',parent+'|'+str(parent_id))
    return ('mosaic.workspace_id',wid) if wid else (None,None)

class _Cursor:
    def __init__(self, cur, release=None): self.cur,self.release=cur,release
    @property
    def rowcount(self): return self.cur.rowcount
    def fetchone(self):
        try:return self.cur.fetchone()
        finally:
            if self.release:self.release();self.release=None
    def fetchall(self):
        try:return self.cur.fetchall()
        finally:
            if self.release:self.release();self.release=None

class _Proxy:
    def __init__(self, owner): self.owner=owner
    def execute(self, query, params=()):
        conn=self.owner._current()
        release=None
        if conn is None:
            cm=self.owner._pool.connection();conn=cm.__enter__()
            release=lambda: cm.__exit__(None,None,None)
        key,val=_context(query,params)
        if key=='mosaic.parent_context':
            parent,parent_id=val.split('|',1)
            # Parent tables are RLS-protected too, so resolve with a narrowly
            # scoped SECURITY DEFINER helper created by the schema migration.
            row=conn.execute('SELECT mosaic_parent_workspace(%s,%s)',(parent,parent_id)).fetchone();wid=next(iter(row.values())) if row else None
            if wid:conn.execute('SELECT set_config(%s,%s,true)',('mosaic.workspace_id',wid))
        elif key and val: conn.execute('SELECT set_config(%s,%s,true)',(key,val))
        cur=conn.execute(_q(query),params)
        if cur.description is None and release: release();release=None
        return _Cursor(cur,release)

class PostgresStore(Store):
    def __init__(self, dsn: str, min_size=1, max_size=10, auto_migrate=True):
        self.path=dsn;self._local=threading.local();self._lock=contextlib.nullcontext()
        self._pool=ConnectionPool(dsn, min_size=int(min_size), max_size=int(max_size), kwargs={'row_factory':dict_row}, open=True)
        self._db=_Proxy(self)
        if auto_migrate:
            self.migrate()
        else:
            self._check_schema()
    def _current(self): return getattr(self._local,'conn',None)
    def close(self): self._pool.close()
    @contextlib.contextmanager
    def tx(self, immediate=True):
        existing=self._current()
        if existing:
            with existing.transaction(): yield self._db
            return
        with self._pool.connection() as conn:
            self._local.conn=conn
            try:
                with conn.transaction(): yield self._db
            finally:self._local.conn=None
    def _check_schema(self):
        with self._pool.connection() as conn:
            row=conn.execute("SELECT to_regclass('public.mosaic_schema_migrations')").fetchone()
            if not row or not next(iter(row.values())): raise RuntimeError('PostgreSQL schema is not initialized; run the migration job')
            version=next(iter(conn.execute('SELECT COALESCE(MAX(version),0) FROM mosaic_schema_migrations').fetchone().values()))
            if version != len(PG_MIGRATIONS): raise RuntimeError(f'PostgreSQL schema v{version} does not match required v{len(PG_MIGRATIONS)}')

    def migrate(self):
        with self._pool.connection() as conn, conn.transaction():
            conn.execute("SELECT pg_advisory_xact_lock(hashtext('mosaic-erp-schema'))")
            conn.execute('CREATE TABLE IF NOT EXISTS mosaic_schema_migrations(version integer PRIMARY KEY,applied_at timestamptz NOT NULL DEFAULT now())')
            rows=conn.execute('SELECT version FROM mosaic_schema_migrations ORDER BY version').fetchall();current=len(rows)
            if current>len(PG_MIGRATIONS): raise RuntimeError('PostgreSQL schema is newer than this build')
            for i in range(current,len(PG_MIGRATIONS)):
                conn.execute(PG_MIGRATIONS[i]);
                if i == 0: conn.execute(RLS_SQL)
                conn.execute('INSERT INTO mosaic_schema_migrations(version) VALUES(%s)',(i+1,))
    def oauth_challenge_create(self, state, *args, **kwargs):
        with self.tx():
            self._current().execute("SELECT set_config('mosaic.oauth_state_hash',%s,true)", (__import__('store').sha256(state),))
            return super().oauth_challenge_create(state, *args, **kwargs)

    def oauth_challenge_consume(self, state, *args, **kwargs):
        with self.tx():
            self._current().execute("SELECT set_config('mosaic.oauth_state_hash',%s,true)", (__import__('store').sha256(state or ''),))
            return super().oauth_challenge_consume(state, *args, **kwargs)

    def oauth_grant_create(self, provider, issuer, subject, email, verified, next_path, mode):
        import secrets
        from datetime import datetime, timedelta, timezone
        from store import sha256
        code='mog_'+secrets.token_urlsafe(32);now=datetime.now(timezone.utc);expires=now+timedelta(minutes=5)
        with self.tx():
            self._current().execute("SELECT set_config('mosaic.oauth_grant_hash',%s,true)",(sha256(code),))
            self._db.execute('INSERT INTO oauth_grants(code_hash,provider,issuer,subject,email,email_verified,mode,next_path,created_at,expires_at) VALUES(?,?,?,?,?,?,?,?,?,?)',(sha256(code),provider,issuer,subject,email,int(verified),mode,next_path,now.isoformat(),expires.isoformat()))
        return code,mode

    def oauth_grant_consume(self, code, *args, **kwargs):
        with self.tx():
            self._current().execute("SELECT set_config('mosaic.oauth_grant_hash',%s,true)",(__import__('store').sha256(code or ''),))
            return super().oauth_grant_consume(code,*args,**kwargs)

    def oauth_auto_provision(self, provider, issuer, subject, email):
        # New-owner SSO from PR #90 inserts an identity without a workspace
        # parameter. Keep the freshly generated tenant context explicit for
        # its identity insert and audit event under forced RLS.
        import secrets
        from store import sha256, utcnow
        email=(email or '').strip().lower() or f"user-{sha256(issuer+'|'+subject)[:16]}@sso.local"
        with self.tx():
            wid,_=self.create_workspace('My company')
            self._current().execute("SELECT set_config('mosaic.workspace_id',%s,true)",(wid,))
            user=self.create_user(wid,email,secrets.token_urlsafe(48),'owner','signup')
            self._db.execute('INSERT INTO oauth_identities(provider,issuer,subject,user_id,workspace_id,created_at) VALUES(?,?,?,?,?,?)',(provider,issuer,subject,user['user_id'],wid,utcnow()))
            self._audit(wid,user['user_id'],'identity.sso_signup',{'provider':provider,'email':email})
        return {'user_id':user['user_id'],'workspace_id':wid,'email':email}

    def authenticate_session(self, token):
        from datetime import datetime, timezone
        from store import sha256
        if not token.startswith('mss_'):return None
        with self._pool.connection() as conn:
            row=conn.execute('SELECT * FROM mosaic_auth_session(%s)',(sha256(token),)).fetchone()
        if not row or datetime.fromisoformat(row['expires_at'])<=datetime.now(timezone.utc):return None
        return row['workspace_id'],row['user_id'],row['role'],row['id']

    def revoke_session(self, session_id, actor_id):
        # The API authenticates actor_id first. Resolve only the session that
        # belongs to that actor, then scope the UPDATE and audit to its tenant.
        from store import NotFound
        with self.tx():
            row=self._current().execute('SELECT mosaic_session_workspace(%s,%s) AS workspace_id',
                                        (session_id,actor_id)).fetchone()
            wid=row['workspace_id'] if row else None
            if not wid:raise NotFound('Session not found')
            self._current().execute("SELECT set_config('mosaic.workspace_id',%s,true)",(wid,))
            return super().revoke_session(session_id,actor_id)

    def invitation(self, token):
        from datetime import datetime, timezone
        from store import sha256
        with self._pool.connection() as conn:
            row=conn.execute('SELECT * FROM mosaic_invitation(%s)',(sha256(token or ''),)).fetchone()
        if not row or row['accepted_at'] or row['revoked_at'] or datetime.fromisoformat(row['expires_at'])<=datetime.now(timezone.utc):return None
        return dict(row)

    def rate_allow(self, identity, rpm, period_seconds=60):
        # Serialize the read/refill/write on a shared bucket across app replicas.
        # SQLite already serializes this through BEGIN IMMEDIATE; PostgreSQL needs
        # a transaction-scoped key lock or simultaneous callers may both pass.
        with self.tx():
            self._db.execute('SELECT pg_advisory_xact_lock(hashtext(%s))',
                             ('mosaic-rate:'+str(rpm)+':'+str(period_seconds)+':'+identity,))
            return super().rate_allow(identity, rpm, period_seconds)
    def login_options(self,email,password):
        with self._pool.connection() as conn:rows=conn.execute('SELECT * FROM mosaic_login_options(%s)',((email or '').strip().lower(),)).fetchall()
        valid=[{'workspace_id':r['workspace_id'],'name':r['name'],'role':r['role']} for r in rows if self._password_ok(password or '',r['password_hash'])]
        if not valid:self._password_ok(password or '',self._password_hash('dummy-password-value'))
        return valid

    def _session_for_user(self,row,ttl_hours=12):
        with self.tx():
            self._db.execute("SELECT set_config('mosaic.workspace_id',%s,true)",(row['workspace_id'],))
            return super()._session_for_user(row,ttl_hours)

    def oauth_identity_users(self,provider,issuer,subject):
        with self._pool.connection() as conn:rows=conn.execute('SELECT * FROM mosaic_oauth_users(%s,%s,%s)',(provider,issuer,subject)).fetchall()
        return [dict(x) for x in rows]

    def create_workspace(self,name,label='Owner key'):
        # Set the newly generated tenant before FORCE RLS checks the inserts.
        import secrets
        wid='wsp_'+secrets.token_hex(8);key_id,plaintext=self._mint_key()
        with self.tx():
            self._db.execute("SELECT set_config('mosaic.workspace_id',%s,true)",(wid,))
            self._db.execute('INSERT INTO workspaces(id,name,created_at) VALUES(?,?,?)',(wid,(name or 'Workspace')[:200],__import__('store').utcnow()))
            self._insert_key(wid,key_id,plaintext,'owner',label);self._audit(wid,key_id,'workspace.create',{'name':name or 'Workspace'})
        return wid,plaintext
    def integrity_check(self):
        try:
            with self._pool.connection() as conn: return conn.execute('SELECT 1').fetchone() is not None
        except Exception:return False
    def save_config(self,*args,**kwargs):
        # A per-workspace advisory lock makes MAX(version)+1 atomic across replicas.
        wid=args[0] if args else kwargs['wid']
        with self.tx():
            self._db.execute("SELECT set_config('mosaic.workspace_id',%s,true)",(wid,))
            self._db.execute("SELECT pg_advisory_xact_lock(hashtext(%s))",('mosaic-config:'+wid,))
            return super().save_config(*args,**kwargs)
    def rollback(self,*args,**kwargs):
        wid=args[0] if args else kwargs['wid']
        with self.tx():
            self._db.execute("SELECT set_config('mosaic.workspace_id',%s,true)",(wid,))
            self._db.execute("SELECT pg_advisory_xact_lock(hashtext(%s))",('mosaic-config:'+wid,))
            return super().rollback(*args,**kwargs)
    def accounting_lock(self,wid,scope):
        self._db.execute("SELECT pg_advisory_xact_lock(hashtext(%s))",('mosaic:'+scope+':'+wid,))
    def backup(self,out_path): raise RuntimeError('PostgreSQL backup is operator-managed; use pgBackRest/WAL-G or your managed service')
    @staticmethod
    def restore(from_path,db_path): raise RuntimeError('PostgreSQL restore is operator-managed; see docs/POSTGRESQL.md')
