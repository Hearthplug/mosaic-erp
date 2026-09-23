"""Answer-shaping provider preference per workspace (the interview AI-assist chooser).

standard = Mosaic's built-in deterministic mapping. Nothing leaves the workspace.
jev      = the owner's own TypeSafe key (BYOK). Answers go to TypeSafe only to be mapped.
Other providers (OpenAI, Claude, DeepSeek) are shown in the chooser as unavailable;
the schema CHECK rejects anything but standard/jev so an unwired provider can never
silently take effect.
"""
import hashlib, os, secrets
from pathlib import Path

from store import utcnow
from jev_client import default_client, HttpJevClient, MockJevClient

PROVIDERS = (
    {'id': 'standard', 'name': 'Standard (built in)',
     'line': 'Mosaic matches your words to settings itself. Nothing leaves your workspace. No key needed.',
     'available': True, 'needs_key': False},
    {'id': 'jev', 'name': 'Jev by TypeSafe (your key)',
     'line': 'A focused English-first model maps your words faster and more precisely. Needs your own TypeSafe key.',
     'available': True, 'needs_key': True},
    {'id': 'other', 'name': 'OpenAI, Claude, or DeepSeek (your key)',
     'line': 'Use another provider\'s model with your own key. Not available yet.',
     'available': False, 'needs_key': True},
)
CONSENT_NOTE = 'With a key option, your interview answers go to that provider to be mapped. Standard keeps everything inside Mosaic.'


class AiPrefs:
    def __init__(self, store):
        self.s = store

    def get(self, wid):
        r = self.s._db.execute('SELECT provider,key_ref FROM ai_answer_prefs WHERE workspace_id=?', (wid,)).fetchone()
        provider = r['provider'] if r else 'standard'
        key_ref = r['key_ref'] if r else ''
        return {'provider': provider, 'has_key': bool(key_ref),
                'key_storage': bool(os.environ.get('MOSAIC_ASSISTANT_SECRET_DIR', '').strip()),
                'options': list(PROVIDERS), 'consent_note': CONSENT_NOTE}

    def set_provider(self, wid, actor, provider, api_key=''):
        if provider not in ('standard', 'jev'):
            raise ValueError('provider must be standard or jev')
        key_ref = ''
        if provider == 'jev' and api_key:
            key_ref = self._save_key(wid, api_key)
        else:
            r = self.s._db.execute('SELECT key_ref FROM ai_answer_prefs WHERE workspace_id=?', (wid,)).fetchone()
            key_ref = r['key_ref'] if r else ''
        if provider == 'jev' and not key_ref:
            raise ValueError('Jev needs your own TypeSafe key. Paste it to continue.')
        with self.s.tx():
            self.s._db.execute(
                'INSERT INTO ai_answer_prefs(workspace_id,provider,key_ref,updated_by,updated_at) VALUES(?,?,?,?,?) '
                'ON CONFLICT(workspace_id) DO UPDATE SET provider=excluded.provider,key_ref=excluded.key_ref,updated_by=excluded.updated_by,updated_at=excluded.updated_at',
                (wid, provider, key_ref, actor, utcnow()))
            self.s._audit(wid, actor, 'ai.preference.update', {'provider': provider, 'key': 'saved' if api_key else ('existing' if key_ref else 'none')})
        return self.get(wid)

    def _save_key(self, wid, api_key):
        if not api_key or len(api_key) > 4096:
            raise ValueError('API key is required')
        secret_dir = os.environ.get('MOSAIC_ASSISTANT_SECRET_DIR', '').strip()
        if not secret_dir:
            raise ValueError('Key storage is not set up on this deployment yet. Use Standard for now.')
        root = Path(secret_dir).resolve(); root.mkdir(mode=0o700, parents=True, exist_ok=True); os.chmod(root, 0o700)
        name = 'jev-' + hashlib.sha256(wid.encode()).hexdigest()[:24] + '.key'
        target = root / name; tmp = root / ('.tmp-' + secrets.token_hex(8))
        fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, 'w') as f:
                f.write(api_key); f.flush(); os.fsync(f.fileno())
            os.replace(tmp, target); os.chmod(target, 0o600)
        finally:
            if tmp.exists(): tmp.unlink()
        return 'file:' + name

    def client_for(self, wid):
        """The mapper client for this workspace: the owner's own Jev key when chosen,
        otherwise Mosaic's built-in deterministic mapping (the mock doubles as the
        built-in engine; env JEV_API_KEY remains a self-hosted deployment default)."""
        r = self.s._db.execute('SELECT provider,key_ref FROM ai_answer_prefs WHERE workspace_id=?', (wid,)).fetchone()
        if r and r['provider'] == 'jev' and r['key_ref'].startswith('file:'):
            root = Path(os.environ.get('MOSAIC_ASSISTANT_SECRET_DIR', '').strip()).resolve()
            key_file = (root / r['key_ref'][5:]).resolve()
            if root in key_file.parents and key_file.is_file():
                return HttpJevClient(key_file.read_text().strip())
        return default_client(os.environ.get('JEV_API_KEY'))
