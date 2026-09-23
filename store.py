"""Durable, tenant-isolated persistence for Mosaic ERP workspaces.

Design notes (docs/ARCHITECTURE.md carries the full rationale and sources):
- SQLite in WAL mode: atomic commits, consistent reads during writes, crash
  recovery, and an official online Backup API - all with zero dependencies.
- Every mutating write happens inside a single IMMEDIATE transaction so a
  version insert, its audit event, and its idempotency record commit or
  roll back together.
- Schema changes are ordered migrations tracked in PRAGMA user_version.
- API keys are random 160-bit tokens; only their SHA-256 digests are stored
  and compared with hmac.compare_digest.
"""
from __future__ import annotations
import contextlib, hashlib, hmac, json, os, secrets, shutil, sqlite3, tempfile, threading
from datetime import timedelta
from datetime import datetime, timezone

ROLES = ('viewer', 'editor', 'owner')
_ROLE_RANK = {r: i for i, r in enumerate(ROLES)}

from accounting_schema import ACCOUNTING_SQLITE_SCHEMA
from retail_schema import RETAIL_SQLITE_SCHEMA
from onboarding_schema import ONBOARDING_SQLITE_SCHEMA
from operating_model_schema import OPERATING_MODEL_SQLITE_SCHEMA
from migration_schema import MIGRATION_SQLITE_SCHEMA
from tax_verification_schema import TAX_VERIFICATION_SQLITE_SCHEMA
from provisioning_schema import PROVISIONING_SQLITE_SCHEMA
from artifact_builder_schema import ARTIFACT_BUILDER_SQLITE_SCHEMA
from assistant_setup_schema import ASSISTANT_SETUP_SQLITE_SCHEMA
from ai_prefs_schema import AI_PREFS_SQLITE_SCHEMA
from assistant_preview_schema import ASSISTANT_PREVIEW_SQLITE_SCHEMA

MIGRATIONS = [
    # 1: core workspace schema
    """
    CREATE TABLE workspaces(
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        created_at TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'active'
    );
    CREATE TABLE api_keys(
        id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
        label TEXT NOT NULL DEFAULT '',
        role TEXT NOT NULL CHECK(role IN ('viewer','editor','owner')),
        key_hash TEXT NOT NULL UNIQUE,
        created_at TEXT NOT NULL,
        revoked_at TEXT
    );
    CREATE TABLE config_versions(
        workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
        version INTEGER NOT NULL,
        answers_json TEXT NOT NULL,
        config_json TEXT NOT NULL,
        checksum TEXT NOT NULL,
        summary TEXT NOT NULL DEFAULT '',
        actor_key_id TEXT,
        created_at TEXT NOT NULL,
        PRIMARY KEY(workspace_id, version)
    );
    CREATE TABLE audit_events(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
        at TEXT NOT NULL,
        actor_key_id TEXT,
        action TEXT NOT NULL,
        detail_json TEXT NOT NULL DEFAULT '{}'
    );
    CREATE INDEX idx_audit_ws ON audit_events(workspace_id, id);
    CREATE TABLE idempotency_keys(
        key TEXT NOT NULL,
        workspace_id TEXT NOT NULL,
        endpoint TEXT NOT NULL,
        request_hash TEXT NOT NULL,
        status INTEGER NOT NULL,
        response_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        PRIMARY KEY(key, workspace_id)
    );
    """,
    # 2: named users, revocable sessions, and a process-shared rate limiter
    """
    CREATE TABLE users(
        id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
        email TEXT NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL CHECK(role IN ('viewer','editor','owner')),
        created_at TEXT NOT NULL,
        disabled_at TEXT,
        UNIQUE(workspace_id,email)
    );
    CREATE TABLE sessions(
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        token_hash TEXT NOT NULL UNIQUE,
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        revoked_at TEXT
    );
    CREATE INDEX idx_sessions_token ON sessions(token_hash);
    CREATE TABLE rate_buckets(
        identity TEXT PRIMARY KEY,
        tokens REAL NOT NULL,
        updated_at REAL NOT NULL
    );
    """,
    ACCOUNTING_SQLITE_SCHEMA,
    RETAIL_SQLITE_SCHEMA,
    ONBOARDING_SQLITE_SCHEMA,
    OPERATING_MODEL_SQLITE_SCHEMA,
    MIGRATION_SQLITE_SCHEMA,
    TAX_VERIFICATION_SQLITE_SCHEMA,
    PROVISIONING_SQLITE_SCHEMA,
    # 10: persistent, single-use OIDC challenges, identities, and browser grants
    """
    CREATE TABLE oauth_challenges(state_hash TEXT PRIMARY KEY,provider TEXT NOT NULL,nonce TEXT NOT NULL,code_verifier TEXT NOT NULL,next_path TEXT NOT NULL,invite_token TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL,expires_at TEXT NOT NULL,used_at TEXT);
    CREATE TABLE oauth_identities(provider TEXT NOT NULL,issuer TEXT NOT NULL,subject TEXT NOT NULL,user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,created_at TEXT NOT NULL,PRIMARY KEY(provider,issuer,subject,workspace_id),UNIQUE(provider,issuer,subject,user_id));
    CREATE INDEX idx_oauth_identity_user ON oauth_identities(user_id);
    CREATE TABLE oauth_grants(code_hash TEXT PRIMARY KEY,provider TEXT NOT NULL,issuer TEXT NOT NULL,subject TEXT NOT NULL,email TEXT NOT NULL,email_verified INTEGER NOT NULL,mode TEXT NOT NULL CHECK(mode IN ('signin','link','enter')),next_path TEXT NOT NULL,created_at TEXT NOT NULL,expires_at TEXT NOT NULL,used_at TEXT);
    """,
    ARTIFACT_BUILDER_SQLITE_SCHEMA,
    ASSISTANT_SETUP_SQLITE_SCHEMA,
    ASSISTANT_PREVIEW_SQLITE_SCHEMA,
    AI_PREFS_SQLITE_SCHEMA,
]

def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()

def canon(obj) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(',', ':'))

def sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()

class Conflict(Exception):
    """Optimistic-concurrency or idempotency conflict (HTTP 409)."""

class NotFound(Exception):
    """Requested record does not exist (HTTP 404)."""

class Store:
    """Thread-safe single-node store. One connection guarded by one lock:
    SQLite serializes writers anyway, and WAL gives non-blocking reads."""

    def __init__(self, path: str):
        self.path = str(path)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        self._db.row_factory = sqlite3.Row
        with self._lock:
            self._db.execute('PRAGMA journal_mode=WAL')
            self._db.execute('PRAGMA foreign_keys=ON')
            self._db.execute('PRAGMA busy_timeout=5000')
            self._db.execute('PRAGMA synchronous=NORMAL')
        self.migrate()

    def close(self):
        with self._lock:
            self._db.close()

    @contextlib.contextmanager
    def tx(self, immediate: bool = True):
        """Atomic unit; nested domain steps use savepoints under one outer commit."""
        with self._lock:
            if self._db.in_transaction:
                point='mosaic_nested_'+secrets.token_hex(6)
                self._db.execute('SAVEPOINT '+point)
                try:
                    yield self._db
                except Exception:
                    self._db.execute('ROLLBACK TO '+point)
                    self._db.execute('RELEASE '+point)
                    raise
                else:self._db.execute('RELEASE '+point)
                return
            self._db.execute('BEGIN IMMEDIATE' if immediate else 'BEGIN')
            try:
                yield self._db
            except Exception:
                self._db.execute('ROLLBACK')
                raise
            else:
                self._db.execute('COMMIT')

    def migrate(self):
        with self._lock:
            current = self._db.execute('PRAGMA user_version').fetchone()[0]
            if current > len(MIGRATIONS):
                raise RuntimeError(f'Database schema v{current} is newer than this build supports (v{len(MIGRATIONS)})')
            for version in range(current, len(MIGRATIONS)):
                # executescript runs in autocommit mode, so the script carries
                # its own transaction: all-or-nothing per migration step.
                self._db.executescript('BEGIN;' + MIGRATIONS[version] + f'PRAGMA user_version={version + 1};' + 'COMMIT;')

    def accounting_lock(self, wid, scope):
        # SQLite's BEGIN IMMEDIATE already serializes writers.
        return None

    def integrity_check(self) -> bool:
        with self._lock:
            return self._db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'

    # -- workspaces and keys -------------------------------------------------
    def create_workspace(self, name: str, label: str = 'Owner key'):
        wid = 'wsp_' + secrets.token_hex(8)
        key_id, plaintext = self._mint_key()
        with self.tx():
            self._db.execute('INSERT INTO workspaces(id,name,created_at) VALUES(?,?,?)', (wid, (name or 'Workspace')[:200], utcnow()))
            self._insert_key(wid, key_id, plaintext, 'owner', label)
            self._audit(wid, key_id, 'workspace.create', {'name': name or 'Workspace'})
        return wid, plaintext

    def _mint_key(self):
        return 'key_' + secrets.token_hex(8), 'msk_' + secrets.token_hex(20)

    def _insert_key(self, wid, key_id, plaintext, role, label):
        self._db.execute(
            'INSERT INTO api_keys(id,workspace_id,label,role,key_hash,created_at) VALUES(?,?,?,?,?,?)',
            (key_id, wid, (label or '')[:120], role, sha256(plaintext), utcnow()))

    def authenticate(self, presented: str):
        """Resolve a bearer token to (workspace_id, key_id, role) or None."""
        if not presented or not presented.startswith('msk_'):
            return None
        with self._lock:
            row = self._db.execute(
                "SELECT id,workspace_id,role,revoked_at FROM api_keys WHERE key_hash=?", (sha256(presented),)).fetchone()
        if not row or row['revoked_at'] is not None:
            return None
        return row['workspace_id'], row['id'], row['role']

    @staticmethod
    def role_ok(role: str, minimum: str) -> bool:
        return _ROLE_RANK.get(role, -1) >= _ROLE_RANK[minimum]

    @staticmethod
    def _password_hash(password: str, salt: bytes | None = None) -> str:
        if len(password) < 12:
            raise ValueError('password must be at least 12 characters')
        salt = salt or secrets.token_bytes(16)
        rounds = 600_000
        digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, rounds)
        return f'pbkdf2_sha256${rounds}${salt.hex()}${digest.hex()}'

    @staticmethod
    def _password_ok(password: str, encoded: str) -> bool:
        try:
            _, rounds, salt, expected = encoded.split('$')
            actual = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), int(rounds)).hex()
            return hmac.compare_digest(actual, expected)
        except (ValueError, TypeError):
            return False

    def create_user(self, wid: str, email: str, password: str, role: str, actor_key_id: str):
        if role not in ROLES:
            raise ValueError('role must be one of: ' + ', '.join(ROLES))
        email = (email or '').strip().lower()
        if '@' not in email or len(email) > 254:
            raise ValueError('valid email required')
        uid = 'usr_' + secrets.token_hex(8)
        encoded = self._password_hash(password)
        with self.tx():
            self._db.execute('INSERT INTO users(id,workspace_id,email,password_hash,role,created_at) VALUES(?,?,?,?,?,?)',
                             (uid, wid, email, encoded, role, utcnow()))
            self._audit(wid, actor_key_id, 'user.create', {'user_id': uid, 'email': email, 'role': role})
        return {'user_id': uid, 'email': email, 'role': role}

    def login_options(self, email: str, password: str):
        email=(email or '').strip().lower()
        rows=self._db.execute("SELECT u.workspace_id,u.password_hash,u.role,w.name FROM users u JOIN workspaces w ON w.id=u.workspace_id WHERE u.email=? AND u.disabled_at IS NULL AND w.status='active'",(email,)).fetchall()
        valid=[{'workspace_id':r['workspace_id'],'name':r['name'],'role':r['role']} for r in rows if self._password_ok(password or '',r['password_hash'])]
        if not valid:self._password_ok(password or '',self._password_hash('dummy-password-value'))
        return valid

    def login(self, workspace_id: str, email: str, password: str, ttl_hours: int = 12):
        # A generic failure prevents account enumeration. Password work is always performed.
        with self._lock:
            row = self._db.execute("SELECT * FROM users WHERE workspace_id=? AND email=? AND disabled_at IS NULL",
                                   (workspace_id, (email or '').strip().lower())).fetchone()
        encoded = row['password_hash'] if row else self._password_hash('dummy-password-value')
        ok = self._password_ok(password or '', encoded)
        if not row or not ok:
            return None
        return self._session_for_user(row,ttl_hours)

    def authenticate_session(self, token: str):
        if not token.startswith('mss_'):
            return None
        with self._lock:
            row = self._db.execute("""SELECT s.id,u.id user_id,u.workspace_id,u.role,s.expires_at
                FROM sessions s JOIN users u ON u.id=s.user_id
                WHERE s.token_hash=? AND s.revoked_at IS NULL AND u.disabled_at IS NULL""", (sha256(token),)).fetchone()
        if not row or datetime.fromisoformat(row['expires_at']) <= datetime.now(timezone.utc):
            return None
        return row['workspace_id'], row['user_id'], row['role'], row['id']

    def revoke_session(self, session_id: str, actor_id: str):
        with self.tx():
            row = self._db.execute('SELECT u.workspace_id FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.id=?', (session_id,)).fetchone()
            if not row: raise NotFound('Session not found')
            self._db.execute('UPDATE sessions SET revoked_at=? WHERE id=?', (utcnow(), session_id))
            self._audit(row['workspace_id'], actor_id, 'session.logout', {'session_id': session_id})


    def _session_for_user(self, row, ttl_hours=12):
        sid,token='ses_'+secrets.token_hex(8),'mss_'+secrets.token_hex(32);now=datetime.now(timezone.utc);expires=now+timedelta(hours=max(1,min(int(ttl_hours),24)))
        with self.tx():
            self._db.execute('INSERT INTO sessions(id,user_id,token_hash,created_at,expires_at) VALUES(?,?,?,?,?)',(sid,row['id'],sha256(token),now.isoformat(),expires.isoformat()))
            self._audit(row['workspace_id'],row['id'],'session.login',{'session_id':sid})
        return {'session_token':token,'expires_at':expires.isoformat(),'workspace_id':row['workspace_id'],'user_id':row['id'],'role':row['role']}

    def oauth_challenge_create(self,state,provider,nonce,verifier,next_path,invite_token=''):
        now=datetime.now(timezone.utc);expires=now+timedelta(minutes=10)
        with self.tx():self._db.execute('INSERT INTO oauth_challenges(state_hash,provider,nonce,code_verifier,next_path,invite_token,created_at,expires_at) VALUES(?,?,?,?,?,?,?,?)',(sha256(state),provider,nonce,verifier,next_path,invite_token or '',now.isoformat(),expires.isoformat()))
    def oauth_challenge_consume(self,state,provider):
        with self.tx():
            r=self._db.execute('SELECT * FROM oauth_challenges WHERE state_hash=? AND provider=?',(sha256(state or ''),provider)).fetchone()
            if not r or r['used_at'] or datetime.fromisoformat(r['expires_at'])<=datetime.now(timezone.utc):return None
            if self._db.execute('UPDATE oauth_challenges SET used_at=? WHERE state_hash=? AND used_at IS NULL',(utcnow(),sha256(state))).rowcount!=1:return None
            return dict(r)
    def oauth_identity_users(self,provider,issuer,subject):
        rows=self._db.execute("SELECT u.id,u.workspace_id,u.email,u.role,w.name FROM oauth_identities i JOIN users u ON u.id=i.user_id JOIN workspaces w ON w.id=u.workspace_id WHERE i.provider=? AND i.issuer=? AND i.subject=? AND u.disabled_at IS NULL AND w.status='active'",(provider,issuer,subject)).fetchall()
        return [dict(x) for x in rows]
    def oauth_grant_create(self,provider,issuer,subject,email,verified,next_path,mode):
        code='mog_'+secrets.token_urlsafe(32);now=datetime.now(timezone.utc);expires=now+timedelta(minutes=5)
        with self.tx():self._db.execute('INSERT INTO oauth_grants(code_hash,provider,issuer,subject,email,email_verified,mode,next_path,created_at,expires_at) VALUES(?,?,?,?,?,?,?,?,?,?)',(sha256(code),provider,issuer,subject,email,int(verified),mode,next_path,now.isoformat(),expires.isoformat()))
        return code,mode
    def oauth_grant_consume(self,code,mode):
        with self.tx():
            r=self._db.execute('SELECT * FROM oauth_grants WHERE code_hash=? AND mode=?',(sha256(code or ''),mode)).fetchone()
            if not r or r['used_at'] or datetime.fromisoformat(r['expires_at'])<=datetime.now(timezone.utc):return None
            if self._db.execute('UPDATE oauth_grants SET used_at=? WHERE code_hash=? AND used_at IS NULL',(utcnow(),sha256(code))).rowcount!=1:return None
            return dict(r)
    def oauth_complete(self,code):
        g=self.oauth_grant_consume(code,'signin')
        if not g:raise Conflict('sign-in grant is invalid or expired')
        users=self.oauth_identity_users(g['provider'],g['issuer'],g['subject'])
        enter,_=self.oauth_grant_create(g['provider'],g['issuer'],g['subject'],g['email'],bool(g['email_verified']),g['next_path'],'enter')
        return {'workspaces':[{'workspace_id':u['workspace_id'],'name':u['name'],'role':u['role']} for u in users],'enter_code':enter,'next_path':g['next_path']}
    def oauth_enter(self,code,workspace_id):
        g=self.oauth_grant_consume(code,'enter')
        if not g:raise Conflict('company-selection grant is invalid or expired')
        users=self.oauth_identity_users(g['provider'],g['issuer'],g['subject']);row=next((x for x in users if x['workspace_id']==workspace_id),None)
        if not row:raise NotFound('company is not linked to this identity')
        return self._session_for_user(row)
    def oauth_link(self,code,email,password):
        g=self.oauth_grant_consume(code,'link')
        if not g:raise Conflict('account-link grant is invalid or expired')
        email=(email or '').strip().lower();options=self.login_options(email,password)
        if not options:raise Conflict('email or password did not match an existing Mosaic account')
        if g['email_verified'] and g['email'] and email!=g['email']:raise Conflict('use the verified provider email to link this identity')
        with self.tx():
            for o in options:
                u=self._db.execute('SELECT id,workspace_id FROM users WHERE workspace_id=? AND email=? AND disabled_at IS NULL',(o['workspace_id'],email)).fetchone()
                self._db.execute('INSERT INTO oauth_identities(provider,issuer,subject,user_id,workspace_id,created_at) VALUES(?,?,?,?,?,?)',(g['provider'],g['issuer'],g['subject'],u['id'],u['workspace_id'],utcnow()))
                self._audit(u['workspace_id'],u['id'],'identity.link',{'provider':g['provider']})
        return self.oauth_grant_create(g['provider'],g['issuer'],g['subject'],email,bool(g['email_verified']),g['next_path'],'signin')[0]
    def accept_invitation_federated(self,token,provider,issuer,subject):
        invite=self.invitation(token)
        if not invite:raise Conflict('invitation is invalid or expired')
        with self.tx():
            user=self.create_user(invite['workspace_id'],invite['email'],secrets.token_urlsafe(48),invite['role'],invite['id'])
            self._db.execute('INSERT INTO oauth_identities(provider,issuer,subject,user_id,workspace_id,created_at) VALUES(?,?,?,?,?,?)',(provider,issuer,subject,user['user_id'],invite['workspace_id'],utcnow()))
            if self._db.execute('UPDATE workspace_invitations SET accepted_at=? WHERE id=? AND workspace_id=? AND accepted_at IS NULL',(utcnow(),invite['id'],invite['workspace_id'])).rowcount!=1:raise Conflict('invitation was already used')
        return user|{'workspace_id':invite['workspace_id'],'operational_role':invite['operational_role']}

    def rate_allow(self, identity: str, rpm: int):
        import time
        now = time.time(); rpm = max(int(rpm), 1)
        with self.tx():
            identity = f'{rpm}:{identity}'
            row = self._db.execute('SELECT tokens,updated_at FROM rate_buckets WHERE identity=?', (identity,)).fetchone()
            tokens, ts = (row['tokens'], row['updated_at']) if row else (float(rpm), now)
            tokens = min(float(rpm), tokens + max(0.0, now-ts) * rpm / 60.0)
            allowed = tokens >= 1.0
            tokens = tokens - 1.0 if allowed else tokens
            self._db.execute('INSERT INTO rate_buckets(identity,tokens,updated_at) VALUES(?,?,?) ON CONFLICT(identity) DO UPDATE SET tokens=excluded.tokens,updated_at=excluded.updated_at', (identity,tokens,now))
        return 0.0 if allowed else 60.0 / rpm

    def create_invitation(self,wid,email,role,operational_role,actor,ttl_hours=72):
        if role not in ROLES:raise ValueError('invalid role')
        iid,token='inv_'+secrets.token_hex(8),'miv_'+secrets.token_urlsafe(32);now=datetime.now(timezone.utc);expires=now+timedelta(hours=max(1,min(int(ttl_hours),168)))
        with self.tx():
            self._db.execute('INSERT INTO workspace_invitations(id,workspace_id,email,role,operational_role,token_hash,expires_at,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?)',(iid,wid,(email or '').strip().lower(),role,operational_role,sha256(token),expires.isoformat(),actor,now.isoformat()))
            self._audit(wid,actor,'invitation.create',{'invitation_id':iid,'email':(email or '').strip().lower(),'role':role,'operational_role':operational_role})
        return {'invitation_id':iid,'invite_token':token,'expires_at':expires.isoformat()}
    def invitation(self,token):
        r=self._db.execute('SELECT id,workspace_id,email,role,operational_role,expires_at,accepted_at,revoked_at FROM workspace_invitations WHERE token_hash=?',(sha256(token or ''),)).fetchone()
        if not r or r['accepted_at'] or r['revoked_at'] or datetime.fromisoformat(r['expires_at'])<=datetime.now(timezone.utc):return None
        return dict(r)
    def accept_invitation(self,token,password):
        invite=self.invitation(token)
        if not invite:raise Conflict('invitation is invalid or expired')
        user=self.create_user(invite['workspace_id'],invite['email'],password,invite['role'],invite['id'])
        with self.tx():
            if self._db.execute('UPDATE workspace_invitations SET accepted_at=? WHERE id=? AND workspace_id=? AND accepted_at IS NULL',(utcnow(),invite['id'],invite['workspace_id'])).rowcount!=1:raise Conflict('invitation was already used')
        return user|{'workspace_id':invite['workspace_id'],'operational_role':invite['operational_role']}

    def create_key(self, wid: str, role: str, label: str, actor_key_id: str):
        if role not in ROLES:
            raise ValueError('role must be one of: ' + ', '.join(ROLES))
        self.get_workspace(wid)
        key_id, plaintext = self._mint_key()
        with self.tx():
            self._insert_key(wid, key_id, plaintext, role, label)
            self._audit(wid, actor_key_id, 'key.create', {'key_id': key_id, 'role': role, 'label': label or ''})
        return key_id, plaintext

    def revoke_key(self, wid: str, key_id: str, actor_key_id: str):
        with self.tx():
            cur = self._db.execute(
                'UPDATE api_keys SET revoked_at=? WHERE id=? AND workspace_id=? AND revoked_at IS NULL',
                (utcnow(), key_id, wid))
            if cur.rowcount == 0:
                raise NotFound('key not found or already revoked')
            self._audit(wid, actor_key_id, 'key.revoke', {'key_id': key_id})

    def get_workspace(self, wid: str):
        with self._lock:
            row = self._db.execute('SELECT id,name,created_at,status FROM workspaces WHERE id=?', (wid,)).fetchone()
        if not row:
            raise NotFound('workspace not found')
        return dict(row)

    # -- versioned configurations --------------------------------------------
    def save_config(self, wid, answers, config, base_version, summary, actor_key_id,
                    idem_key=None, endpoint='PUT /api/workspace/config', request_hash=''):
        self.get_workspace(wid)
        if idem_key:
            hit = self._idem_lookup(idem_key, wid, endpoint, request_hash)
            if hit is not None:
                return hit['body'], True
        checksum = sha256(canon(config))
        with self.tx():
            row = self._db.execute(
                'SELECT COALESCE(MAX(version),0) AS v FROM config_versions WHERE workspace_id=?', (wid,)).fetchone()
            latest = row['v']
            if base_version != latest:
                raise Conflict(f'base_version {base_version} does not match latest version {latest}; fetch the latest config and retry')
            version = latest + 1
            self._db.execute(
                'INSERT INTO config_versions(workspace_id,version,answers_json,config_json,checksum,summary,actor_key_id,created_at) VALUES(?,?,?,?,?,?,?,?)',
                (wid, version, canon(answers), canon(config), checksum, (summary or '')[:500], actor_key_id, utcnow()))
            self._db.execute("UPDATE generated_artifacts SET status='reverification_required',legal_status=CASE WHEN kind='statutory_invoice' THEN 'review_required' ELSE legal_status END WHERE workspace_id=? AND status='active' AND COALESCE(config_version,-1)<>?",(wid,version))
            self._audit(wid, actor_key_id, 'config.save', {'version': version, 'summary': summary or '', 'checksum': checksum})
            result = {'version': version, 'checksum': checksum, 'saved_at': utcnow()}
            if idem_key:
                self._idem_store(idem_key, wid, endpoint, request_hash, 200, result)
        return result, False

    def get_config(self, wid, version=None):
        self.get_workspace(wid)
        with self._lock:
            if version is None:
                row = self._db.execute(
                    'SELECT * FROM config_versions WHERE workspace_id=? ORDER BY version DESC LIMIT 1', (wid,)).fetchone()
            else:
                row = self._db.execute(
                    'SELECT * FROM config_versions WHERE workspace_id=? AND version=?', (wid, version)).fetchone()
        if not row:
            raise NotFound('no configuration version found')
        return self._row_config(row)

    @staticmethod
    def _row_config(row):
        config = json.loads(row['config_json'])
        if sha256(canon(config)) != row['checksum']:
            raise Conflict(f"stored checksum mismatch at version {row['version']}; treat the database as suspect and restore from backup")
        return {'version': row['version'], 'answers': json.loads(row['answers_json']),
                'config': config, 'checksum': row['checksum'], 'summary': row['summary'],
                'saved_at': row['created_at']}

    def list_versions(self, wid):
        self.get_workspace(wid)
        with self._lock:
            rows = self._db.execute(
                'SELECT version,summary,checksum,created_at FROM config_versions WHERE workspace_id=? ORDER BY version DESC', (wid,)).fetchall()
        return [dict(r) for r in rows]

    def rollback(self, wid, target_version, actor_key_id, idem_key=None, request_hash=''):
        endpoint = 'POST /api/workspace/rollback'
        if idem_key:
            hit = self._idem_lookup(idem_key, wid, endpoint, request_hash)
            if hit is not None:
                return hit['body'], True
        target = self.get_config(wid, target_version)
        with self.tx():
            latest = self._db.execute(
                'SELECT COALESCE(MAX(version),0) AS v FROM config_versions WHERE workspace_id=?', (wid,)).fetchone()['v']
            version = latest + 1
            summary = f'Rollback to version {target_version}'
            self._db.execute(
                'INSERT INTO config_versions(workspace_id,version,answers_json,config_json,checksum,summary,actor_key_id,created_at) VALUES(?,?,?,?,?,?,?,?)',
                (wid, version, canon(target['answers']), canon(target['config']), target['checksum'], summary, actor_key_id, utcnow()))
            self._db.execute("UPDATE generated_artifacts SET status='reverification_required',legal_status=CASE WHEN kind='statutory_invoice' THEN 'review_required' ELSE legal_status END WHERE workspace_id=? AND status='active' AND COALESCE(config_version,-1)<>?",(wid,version))
            self._audit(wid, actor_key_id, 'config.rollback', {'from_version': latest, 'restored_version': target_version, 'version': version})
            result = {'version': version, 'restored_from': target_version, 'checksum': target['checksum'],
                      'answers': target['answers'], 'config': target['config']}
            if idem_key:
                self._idem_store(idem_key, wid, endpoint, request_hash, 200, result)
        return result, False

    # -- audit ----------------------------------------------------------------
    def _audit(self, wid, actor_key_id, action, detail):
        self._db.execute(
            'INSERT INTO audit_events(workspace_id,at,actor_key_id,action,detail_json) VALUES(?,?,?,?,?)',
            (wid, utcnow(), actor_key_id, action, canon(detail)))

    def audit_trail(self, wid, limit=200):
        self.get_workspace(wid)
        with self._lock:
            rows = self._db.execute(
                'SELECT id,at,actor_key_id,action,detail_json FROM audit_events WHERE workspace_id=? ORDER BY id DESC LIMIT ?',
                (wid, min(int(limit), 1000))).fetchall()
        return [{'id': r['id'], 'at': r['at'], 'actor_key_id': r['actor_key_id'],
                 'action': r['action'], 'detail': json.loads(r['detail_json'])} for r in rows]

    # -- idempotency ------------------------------------------------------------
    def _idem_lookup(self, key, wid, endpoint, request_hash):
        with self._lock:
            row = self._db.execute(
                'SELECT endpoint,request_hash,status,response_json FROM idempotency_keys WHERE key=? AND workspace_id=?',
                (key, wid)).fetchone()
        if not row:
            return None
        if row['endpoint'] != endpoint or row['request_hash'] != request_hash:
            raise Conflict('Idempotency-Key was already used with a different request')
        return {'status': row['status'], 'body': json.loads(row['response_json'])}

    def _idem_store(self, key, wid, endpoint, request_hash, status, body):
        self._db.execute(
            'INSERT INTO idempotency_keys(key,workspace_id,endpoint,request_hash,status,response_json,created_at) VALUES(?,?,?,?,?,?,?)',
            (key, wid, endpoint, request_hash, status, canon(body), utcnow()))

    # -- export and erasure -------------------------------------------------------
    def export_workspace(self, wid, actor_key_id):
        ws = self.get_workspace(wid)
        with self.tx():
            self._audit(wid, actor_key_id, 'workspace.export', {})
            keys = [dict(r) for r in self._db.execute(
                'SELECT id,label,role,created_at,revoked_at FROM api_keys WHERE workspace_id=?', (wid,)).fetchall()]
            versions = [self._row_config(r) for r in self._db.execute(
                'SELECT * FROM config_versions WHERE workspace_id=? ORDER BY version', (wid,)).fetchall()]
            events = self.audit_trail(wid, limit=1000)
        return {'format': 'mosaic-erp-workspace-export', 'schema': 1, 'exported_at': utcnow(),
                'workspace': ws, 'api_keys': keys, 'config_versions': versions, 'audit_events': events}

    def delete_workspace(self, wid, actor_key_id):
        self.get_workspace(wid)
        with self.tx():
            self._db.execute('DELETE FROM idempotency_keys WHERE workspace_id=?', (wid,))
            self._db.execute('DELETE FROM workspaces WHERE id=?', (wid,))  # cascades keys, versions, audit
        return True

    # -- backup and restore ---------------------------------------------------------
    def backup(self, out_path: str):
        """Consistent online backup via SQLite's Backup API; verifies the copy."""
        out_path = str(out_path)
        with self._lock:
            dest = sqlite3.connect(out_path)
            try:
                self._db.backup(dest)
                ok = dest.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
            finally:
                dest.close()
        if not ok:
            os.unlink(out_path)
            raise RuntimeError('backup failed integrity check; no file kept')
        return out_path

    @staticmethod
    def restore(from_path: str, db_path: str):
        """Verify the backup, then atomically replace the database file.
        The server must be stopped first (documented runbook step)."""
        src = sqlite3.connect(str(from_path))
        try:
            if src.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise RuntimeError('backup file failed integrity check; restore refused')
            version = src.execute('PRAGMA user_version').fetchone()[0]
            if version < 1 or version > len(MIGRATIONS):
                raise RuntimeError(f'backup schema v{version} is not restorable by this build')
        finally:
            src.close()
        directory = os.path.dirname(os.path.abspath(db_path))
        fd, tmp = tempfile.mkstemp(prefix='.restore-', dir=directory)
        os.close(fd)
        try:
            shutil.copyfile(from_path, tmp)
            for suffix in ('-wal', '-shm'):
                stale = db_path + suffix
                if os.path.exists(stale):
                    os.unlink(stale)
            os.replace(tmp, db_path)
        except Exception:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise
        return db_path
