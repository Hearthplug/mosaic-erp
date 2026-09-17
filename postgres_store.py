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
''']

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
CREATE OR REPLACE FUNCTION mosaic_auth_session(p_hash text) RETURNS TABLE(id text,user_id text,workspace_id text,role text,expires_at text) LANGUAGE sql SECURITY DEFINER SET search_path=public,pg_temp AS $$ SELECT s.id,u.id,u.workspace_id,u.role,s.expires_at FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=p_hash AND s.revoked_at IS NULL AND u.disabled_at IS NULL $$;
REVOKE ALL ON FUNCTION mosaic_auth_session(text) FROM PUBLIC; GRANT EXECUTE ON FUNCTION mosaic_auth_session(text) TO CURRENT_USER;
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
        if key and val: conn.execute('SELECT set_config(%s,%s,true)',(key,val))
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
            if not row or not row[0]: raise RuntimeError('PostgreSQL schema is not initialized; run the migration job')
            version=conn.execute('SELECT COALESCE(MAX(version),0) FROM mosaic_schema_migrations').fetchone()[0]
            if version != len(PG_MIGRATIONS): raise RuntimeError(f'PostgreSQL schema v{version} does not match required v{len(PG_MIGRATIONS)}')

    def migrate(self):
        with self._pool.connection() as conn, conn.transaction():
            conn.execute("SELECT pg_advisory_xact_lock(hashtext('mosaic-erp-schema'))")
            conn.execute('CREATE TABLE IF NOT EXISTS mosaic_schema_migrations(version integer PRIMARY KEY,applied_at timestamptz NOT NULL DEFAULT now())')
            rows=conn.execute('SELECT version FROM mosaic_schema_migrations ORDER BY version').fetchall();current=len(rows)
            if current>len(PG_MIGRATIONS): raise RuntimeError('PostgreSQL schema is newer than this build')
            for i in range(current,len(PG_MIGRATIONS)):
                conn.execute(PG_MIGRATIONS[i]);conn.execute(RLS_SQL);conn.execute('INSERT INTO mosaic_schema_migrations(version) VALUES(%s)',(i+1,))
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
    def backup(self,out_path): raise RuntimeError('PostgreSQL backup is operator-managed; use pgBackRest/WAL-G or your managed service')
    @staticmethod
    def restore(from_path,db_path): raise RuntimeError('PostgreSQL restore is operator-managed; see docs/POSTGRESQL.md')
