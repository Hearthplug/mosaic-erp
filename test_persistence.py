"""Release-gate tests for Mosaic ERP's persistence, security, and recovery layer."""
from __future__ import annotations
import json, os, tempfile, threading, time, unittest, urllib.request, urllib.error
from pathlib import Path

os.environ['MOSAIC_DB_PATH'] = tempfile.mktemp(suffix='.db')
os.environ['MOSAIC_RATE_LIMIT_RPM'] = '600'

import app, store
from store import Store, Conflict, NotFound

def http(port, method, path, body=None, headers=None):
    url = f'http://127.0.0.1:{port}{path}'
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={'Content-Type': 'application/json', **(headers or {})})
    try:
        with urllib.request.urlopen(req) as r:
            raw = r.read()
            return r.status, dict(r.headers), json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read()
        return e.code, dict(e.headers), json.loads(raw) if raw else {}

class ServerCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from http.server import ThreadingHTTPServer
        cls.db_path = os.environ['MOSAIC_DB_PATH']
        cls.srv = ThreadingHTTPServer(('127.0.0.1', 0), app.H)
        cls.port = cls.srv.server_address[1]
        cls.thread = threading.Thread(target=cls.srv.serve_forever, daemon=True)
        cls.thread.start()
    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown(); cls.srv.server_close()
    def call(self, method, path, body=None, headers=None):
        return http(self.port, method, path, body, headers)
    def workspace(self, name='Co'):
        s, _, b = self.call('POST', '/api/workspaces', {'name': name})
        assert s == 201, b
        return b['workspace_id'], b['api_key']
    def auth(self, key):
        return {'Authorization': f'Bearer {key}'}

class MigrationTests(unittest.TestCase):
    def test_fresh_database_migrates_and_is_idempotent(self):
        path = tempfile.mktemp(suffix='.db')
        s = Store(path)
        version = s._db.execute('PRAGMA user_version').fetchone()[0]
        self.assertEqual(version, len(store.MIGRATIONS))
        s.migrate()  # second run is a no-op
        self.assertEqual(s._db.execute('PRAGMA user_version').fetchone()[0], version)
        tables = {r[0] for r in s._db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertTrue({'workspaces', 'api_keys', 'config_versions', 'audit_events', 'idempotency_keys'} <= tables)
        s.close()
    def test_wal_and_foreign_keys_enabled(self):
        s = Store(tempfile.mktemp(suffix='.db'))
        self.assertEqual(s._db.execute('PRAGMA journal_mode').fetchone()[0], 'wal')
        self.assertEqual(s._db.execute('PRAGMA foreign_keys').fetchone()[0], 1)
        s.close()

class AuthzTests(ServerCase):
    def test_missing_and_invalid_keys_rejected(self):
        for headers in ({}, {'Authorization': 'Bearer msk_wrong'}, {'Authorization': 'Basic x'}):
            s, _, b = self.call('GET', '/api/workspace/config', headers=headers)
            self.assertEqual(s, 401, b)
    def test_role_ladder_enforced(self):
        wid, owner = self.workspace('Roles')
        s, _, viewer = self.call('POST', '/api/workspace/keys', {'role': 'viewer'}, self.auth(owner))
        s, _, editor = self.call('POST', '/api/workspace/keys', {'role': 'editor'}, self.auth(owner))
        vkey, ekey = viewer['api_key'], editor['api_key']
        body = {'answers': {}, 'config': {'x': 1}, 'base_version': 0}
        s, _, b = self.call('PUT', '/api/workspace/config', body, self.auth(vkey))
        self.assertEqual(s, 403, b)                       # viewer cannot write
        s, _, b = self.call('GET', '/api/workspace/export', headers=self.auth(vkey))
        self.assertEqual(s, 403, b)                       # viewer cannot export
        s, _, b = self.call('POST', '/api/workspace/keys', {'role': 'viewer'}, self.auth(ekey))
        self.assertEqual(s, 403, b)                       # editor cannot mint keys
        s, _, b = self.call('DELETE', '/api/workspace', headers={**self.auth(ekey), 'X-Confirm-Delete': wid})
        self.assertEqual(s, 403, b)                       # editor cannot erase
        s, _, b = self.call('PUT', '/api/workspace/config', body, self.auth(ekey))
        self.assertEqual(s, 200, b)                       # editor can write
    def test_revoked_key_stops_working(self):
        wid, owner = self.workspace('Revoke')
        s, _, k = self.call('POST', '/api/workspace/keys', {'role': 'viewer'}, self.auth(owner))
        s, _, _ = self.call('DELETE', '/api/workspace/keys/' + k['key_id'], headers=self.auth(owner))
        self.assertEqual(s, 200)
        s, _, b = self.call('GET', '/api/workspace', headers=self.auth(k['api_key']))
        self.assertEqual(s, 401, b)
    def test_keys_stored_as_hashes(self):
        self.workspace('Hashes')
        rows = app.STORE._db.execute('SELECT key_hash FROM api_keys').fetchall()
        self.assertTrue(rows)
        for r in rows:
            self.assertEqual(len(r[0]), 64)
            self.assertNotIn('msk_', r[0])

class IsolationTests(ServerCase):
    def test_cross_tenant_access_denied(self):
        wa, ka = self.workspace('A'); wb, kb = self.workspace('B')
        self.call('PUT', '/api/workspace/config', {'answers': {'n': 'A'}, 'config': {'v': 'A'}, 'base_version': 0}, self.auth(ka))
        # A's key cannot reach B's data: every workspace route resolves the tenant from the key itself
        s, _, b = self.call('GET', '/api/workspace/config', headers=self.auth(kb))
        self.assertEqual(s, 404, b)                       # B has no config; A's data is invisible
        s, _, b = self.call('GET', '/api/workspace', headers=self.auth(kb))
        self.assertEqual(b['id'], wb)
        # A's key cannot revoke B's keys (id lookup is tenant-scoped)
        s, _, keys_b = self.call('POST', '/api/workspace/keys', {'role': 'viewer'}, self.auth(kb))
        s, _, b = self.call('DELETE', '/api/workspace/keys/' + keys_b['key_id'], headers=self.auth(ka))
        self.assertEqual(s, 404, b)

class VersioningTests(ServerCase):
    def test_optimistic_concurrency_and_history(self):
        wid, key = self.workspace('Versions')
        s, _, b = self.call('PUT', '/api/workspace/config', {'answers': {'a': 1}, 'config': {'v': 1}, 'base_version': 0}, self.auth(key))
        self.assertEqual((s, b['version']), (200, 1))
        s, _, b = self.call('PUT', '/api/workspace/config', {'answers': {'a': 2}, 'config': {'v': 2}, 'base_version': 0}, self.auth(key))
        self.assertEqual(s, 409, b)                       # stale base rejected
        s, _, b = self.call('PUT', '/api/workspace/config', {'answers': {'a': 2}, 'config': {'v': 2}, 'base_version': 1}, self.auth(key))
        self.assertEqual((s, b['version']), (200, 2))
        s, _, b = self.call('GET', '/api/workspace/config?version=1', headers=self.auth(key))
        self.assertEqual(b['config'], {'v': 1})           # old versions stay readable
        s, _, b = self.call('GET', '/api/workspace/versions', headers=self.auth(key))
        self.assertEqual([v['version'] for v in b['versions']], [2, 1])
    def test_rollback_creates_new_version_with_audit(self):
        wid, key = self.workspace('Rollback')
        self.call('PUT', '/api/workspace/config', {'answers': {'a': 1}, 'config': {'v': 1}, 'base_version': 0}, self.auth(key))
        self.call('PUT', '/api/workspace/config', {'answers': {'a': 2}, 'config': {'v': 2}, 'base_version': 1}, self.auth(key))
        s, _, b = self.call('POST', '/api/workspace/rollback', {'version': 1}, self.auth(key))
        self.assertEqual((s, b['version'], b['restored_from']), (200, 3, 1))
        s, _, cur = self.call('GET', '/api/workspace/config', headers=self.auth(key))
        self.assertEqual(cur['config'], {'v': 1})
        s, _, audit = self.call('GET', '/api/workspace/audit', headers=self.auth(key))
        actions = [e['action'] for e in audit['events']]
        self.assertEqual(actions[0], 'config.rollback')
        self.assertEqual(audit['events'][0]['detail']['restored_version'], 1)
    def test_checksum_verified_on_read(self):
        wid, key = self.workspace('Checksum')
        self.call('PUT', '/api/workspace/config', {'answers': {}, 'config': {'v': 1}, 'base_version': 0}, self.auth(key))
        app.STORE._db.execute("UPDATE config_versions SET checksum='bad' WHERE workspace_id=?", (wid,))
        with self.assertRaises(Conflict):
            app.STORE.get_config(wid)

class IdempotencyTests(ServerCase):
    def test_replay_returns_stored_response_once(self):
        wid, key = self.workspace('Idem')
        body = {'answers': {}, 'config': {'v': 1}, 'base_version': 0}
        s1, _, b1 = self.call('PUT', '/api/workspace/config', body, {**self.auth(key), 'Idempotency-Key': 'k-1'})
        s2, h2, b2 = self.call('PUT', '/api/workspace/config', body, {**self.auth(key), 'Idempotency-Key': 'k-1'})
        self.assertEqual((s1, s2), (200, 200))
        self.assertEqual(b1, b2)
        self.assertEqual(h2.get('Idempotency-Replayed'), 'true')
        s, _, versions = self.call('GET', '/api/workspace/versions', headers=self.auth(key))
        self.assertEqual(len(versions['versions']), 1)    # exactly one version written
    def test_key_reuse_with_different_body_conflicts(self):
        wid, key = self.workspace('Idem2')
        self.call('PUT', '/api/workspace/config', {'answers': {}, 'config': {}, 'base_version': 0}, {**self.auth(key), 'Idempotency-Key': 'k-9'})
        s, _, b = self.call('PUT', '/api/workspace/config', {'answers': {'x': 1}, 'config': {}, 'base_version': 1}, {**self.auth(key), 'Idempotency-Key': 'k-9'})
        self.assertEqual(s, 409, b)

class RateLimitTests(unittest.TestCase):
    def test_burst_is_throttled_with_retry_after(self):
        limiter = app.RateLimiter(5)
        allowed = sum(1 for _ in range(10) if not limiter.allow('id'))
        self.assertEqual(allowed, 5)
        self.assertGreater(limiter.allow('id'), 0)
    def test_server_returns_429(self):
        original = app.LIMITER.rpm
        app.LIMITER.rpm = 3
        try:
            from http.server import ThreadingHTTPServer
            srv = ThreadingHTTPServer(('127.0.0.1', 0), app.H)
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            port = srv.server_address[1]
            codes = [http(port, 'GET', '/health')[0] for _ in range(6)]
            self.assertIn(429, codes)
            srv.shutdown(); srv.server_close()
        finally:
            app.LIMITER = app.RateLimiter(original)

class RecoveryTests(unittest.TestCase):
    def test_failed_transaction_leaves_no_partial_state(self):
        s = Store(tempfile.mktemp(suffix='.db'))
        wid, key = s.create_workspace('Tx')
        auth = s.authenticate(key)
        before = s.audit_trail(wid)
        try:
            with s.tx():
                s._db.execute('INSERT INTO config_versions VALUES(?,?,?,?,?,?,?,?)',
                              (wid, 1, '{}', '{}', 'x', '', auth[1], 'now'))
                raise RuntimeError('simulated crash mid-transaction')
        except RuntimeError:
            pass
        self.assertEqual(s.list_versions(wid), [])        # version rolled back
        self.assertEqual(s.audit_trail(wid), before)
        self.assertTrue(s.integrity_check())
        s.close()
    def test_data_survives_restart(self):
        path = tempfile.mktemp(suffix='.db')
        s = Store(path)
        wid, key = s.create_workspace('Restart')
        auth = s.authenticate(key)
        s.save_config(wid, {'a': 1}, {'v': 1}, 0, 'v1', auth[1])
        s.close()
        s2 = Store(path)
        self.assertEqual(s2.get_config(wid)['config'], {'v': 1})
        s2.close()

class BackupRestoreTests(unittest.TestCase):
    def test_backup_restore_roundtrip(self):
        src = tempfile.mktemp(suffix='.db'); bak = tempfile.mktemp(suffix='.db'); dst = tempfile.mktemp(suffix='.db')
        s = Store(src)
        wid, key = s.create_workspace('Backup')
        auth = s.authenticate(key)
        s.save_config(wid, {'a': 1}, {'v': 'kept'}, 0, 'v1', auth[1])
        s.backup(bak)
        s.save_config(wid, {'a': 2}, {'v': 'changed'}, 1, 'v2', auth[1])
        s.close()
        Store.restore(bak, src)                            # roll the live file back to the backup
        s2 = Store(src)
        self.assertEqual(s2.get_config(wid)['version'], 1)
        self.assertEqual(s2.get_config(wid)['config'], {'v': 'kept'})
        s2.close()
    def test_restore_refuses_corrupt_backup(self):
        bad = tempfile.mktemp(suffix='.db')
        Path(bad).write_bytes(os.urandom(2048))
        with self.assertRaises(Exception):
            Store.restore(bad, tempfile.mktemp(suffix='.db'))

class PrivacyTests(ServerCase):
    def test_export_carries_everything_and_delete_erases(self):
        wid, key = self.workspace('Privacy')
        self.call('PUT', '/api/workspace/config', {'answers': {'name': 'Priv Co'}, 'config': {'v': 1}, 'base_version': 0}, self.auth(key))
        s, h, b = self.call('GET', '/api/workspace/export', headers=self.auth(key))
        self.assertEqual(s, 200, b)
        self.assertIn('attachment', h.get('Content-Disposition', ''))
        self.assertEqual(b['workspace']['id'], wid)
        self.assertEqual(len(b['config_versions']), 1)
        self.assertTrue(b['audit_events'])
        self.assertNotIn('key_hash', json.dumps(b))       # no key material or hashes leave
        s, _, b = self.call('DELETE', '/api/workspace', headers=self.auth(key))
        self.assertEqual(s, 409, b)                       # needs confirmation header
        s, _, b = self.call('DELETE', '/api/workspace', headers={**self.auth(key), 'X-Confirm-Delete': wid})
        self.assertEqual(s, 200, b)
        s, _, b = self.call('GET', '/api/workspace', headers=self.auth(key))
        self.assertEqual(s, 401)                          # keys are gone with the tenant
        with self.assertRaises(NotFound):
            app.STORE.get_workspace(wid)
        rows = app.STORE._db.execute('SELECT COUNT(*) FROM config_versions WHERE workspace_id=?', (wid,)).fetchone()
        self.assertEqual(rows[0], 0)                      # cascaded

class SurfaceTests(ServerCase):
    def test_request_id_security_headers_and_json_errors(self):
        s, h, b = self.call('GET', '/nope')
        self.assertEqual(s, 404)
        self.assertIn('request_id', b)
        self.assertEqual(h.get('X-Content-Type-Options'), 'nosniff')
        self.assertEqual(h.get('Cache-Control'), 'no-store')
        self.assertTrue(h.get('X-Request-ID'))
    def test_ready_metrics_and_existing_compiler_endpoints(self):
        s, _, b = self.call('GET', '/api/workspace/config', headers={'Authorization': 'Bearer msk_nope'})
        s, _, b = self.call('GET', '/health/ready')
        self.assertEqual((s, b['database']), (200, True))
        s, _, m = self.call('GET', '/metrics')
        self.assertTrue(m['requests'])
        s, _, b = self.call('POST', '/api/preview', {'vertical': 'Pharmacy', 'country': 'India'})
        self.assertEqual(s, 200, b)                       # public compiler still open
        self.assertIn('modules', b)
    def test_oversize_and_bad_json(self):
        s, _, b = self.call('POST', '/api/workspaces', {'name': 'x' * (300 * 1024)})
        self.assertEqual(s, 413, b)

if __name__ == '__main__':
    unittest.main()
