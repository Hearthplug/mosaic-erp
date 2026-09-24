"""Answer-shaping provider preference per workspace (the interview AI-assist chooser).

standard = Mosaic's built-in deterministic mapping. Nothing leaves the workspace.
jev      = the owner's own TypeSafe key (BYOK). Answers go to TypeSafe only to be mapped.
openai / claude / deepseek = the owner's own key for that provider (BYOK), same flow.

Every key option is BYOK: the key is stored masked per workspace (file-backed
secret dir, 0600), switching providers keeps each provider's saved key, and every
change writes an audit event. The schema CHECK rejects any id outside this list,
so an unwired provider can never silently take effect.
"""
import hashlib, json, os, secrets
from pathlib import Path

from store import utcnow
from jev_client import default_client, HttpJevClient, MockJevClient
from byok_clients import provider_client, PROVIDER_SPECS

PROVIDERS = (
    {'id': 'standard', 'name': 'Standard (built in)',
     'line': 'Mosaic matches your words to settings itself. Nothing leaves your workspace. No key needed.',
     'available': True, 'needs_key': False},
    {'id': 'jev', 'name': 'Jev by TypeSafe (your key)',
     'line': 'A focused English-first model maps your words faster and more precisely. Needs your own TypeSafe key.',
     'available': True, 'needs_key': True, 'key_brand': 'TypeSafe'},
    {'id': 'openai', 'name': 'OpenAI (your key)',
     'line': "OpenAI's model maps your words to settings. Needs your own OpenAI key.",
     'available': True, 'needs_key': True, 'key_brand': 'OpenAI'},
    {'id': 'claude', 'name': 'Claude (your key)',
     'line': "Claude maps your words to settings. Needs your own Anthropic key.",
     'available': True, 'needs_key': True, 'key_brand': 'Anthropic'},
    {'id': 'deepseek', 'name': 'DeepSeek (your key)',
     'line': "DeepSeek's model maps your words to settings. Needs your own DeepSeek key.",
     'available': True, 'needs_key': True, 'key_brand': 'DeepSeek'},
)
CONSENT_NOTE = 'With a key option, your interview answers go to that provider to be mapped. Standard keeps everything inside Mosaic.'
KEY_PROVIDERS = tuple(p['id'] for p in PROVIDERS if p['needs_key'])
BRANDS = {p['id']: p.get('key_brand', '') for p in PROVIDERS}


class AiPrefs:
    def __init__(self, store):
        self.s = store

    def _row(self, wid):
        return self.s._db.execute('SELECT provider,key_ref FROM ai_answer_prefs WHERE workspace_id=?', (wid,)).fetchone()

    @staticmethod
    def _refs(value):
        """key_ref holds a JSON map {provider: ref}; a legacy bare 'file:' value
        is the Jev key saved before multiple key providers existed."""
        if not value:
            return {}
        if value.startswith('file:'):
            return {'jev': value}
        try:
            refs = json.loads(value)
            return refs if isinstance(refs, dict) else {}
        except ValueError:
            return {}

    def get(self, wid):
        r = self._row(wid)
        provider = r['provider'] if r else 'standard'
        refs = self._refs(r['key_ref']) if r else {}
        return {'provider': provider, 'has_key': provider in refs,
                'key_brand': BRANDS.get(provider, ''),
                'key_storage': bool(os.environ.get('MOSAIC_ASSISTANT_SECRET_DIR', '').strip()),
                'options': list(PROVIDERS), 'consent_note': CONSENT_NOTE}

    def set_provider(self, wid, actor, provider, api_key=''):
        if provider not in tuple(p['id'] for p in PROVIDERS):
            raise ValueError('provider must be one of: ' + ', '.join(p['id'] for p in PROVIDERS))
        r = self._row(wid)
        refs = self._refs(r['key_ref']) if r else {}
        if api_key:
            if provider not in KEY_PROVIDERS:
                raise ValueError(f"{provider} does not take a key")
            refs[provider] = self._save_key(wid, provider, api_key)
        if provider in KEY_PROVIDERS and provider not in refs:
            raise ValueError(f"{BRANDS[provider]} needs your own key. Paste it to continue.")
        with self.s.tx():
            self.s._db.execute(
                'INSERT INTO ai_answer_prefs(workspace_id,provider,key_ref,updated_by,updated_at) VALUES(?,?,?,?,?) '
                'ON CONFLICT(workspace_id) DO UPDATE SET provider=excluded.provider,key_ref=excluded.key_ref,updated_by=excluded.updated_by,updated_at=excluded.updated_at',
                (wid, provider, json.dumps(refs, sort_keys=True), actor, utcnow()))
            self.s._audit(wid, actor, 'ai.preference.update', {'provider': provider, 'key': 'saved' if api_key else ('existing' if provider in refs else 'none')})
        return self.get(wid)

    def _save_key(self, wid, provider, api_key):
        if not api_key or len(api_key) > 4096:
            raise ValueError('API key is required')
        secret_dir = os.environ.get('MOSAIC_ASSISTANT_SECRET_DIR', '').strip()
        if not secret_dir:
            raise ValueError('Key storage is not set up on this deployment yet. Use Standard for now.')
        root = Path(secret_dir).resolve(); root.mkdir(mode=0o700, parents=True, exist_ok=True); os.chmod(root, 0o700)
        name = provider + '-' + hashlib.sha256(wid.encode()).hexdigest()[:24] + '.key'
        target = root / name; tmp = root / ('.tmp-' + secrets.token_hex(8))
        fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, 'w') as f:
                f.write(api_key); f.flush(); os.fsync(f.fileno())
            os.replace(tmp, target); os.chmod(target, 0o600)
        finally:
            if tmp.exists(): tmp.unlink()
        return 'file:' + name

    def _read_key(self, ref):
        root = Path(os.environ.get('MOSAIC_ASSISTANT_SECRET_DIR', '').strip()).resolve()
        key_file = (root / ref[5:]).resolve()
        if root in key_file.parents and key_file.is_file():
            return key_file.read_text().strip()
        return ''

    def client_for(self, wid):
        """The mapper client for this workspace: the owner's own key for the
        chosen provider, otherwise Mosaic's built-in deterministic mapping (the
        mock doubles as the built-in engine; env JEV_API_KEY remains a
        self-hosted deployment default)."""
        r = self._row(wid)
        if r:
            provider = r['provider']
            ref = self._refs(r['key_ref']).get(provider, '')
            if ref.startswith('file:'):
                key = self._read_key(ref)
                if key:
                    if provider == 'jev':
                        return HttpJevClient(key)
                    if provider in PROVIDER_SPECS:
                        return provider_client(provider, key)
        return default_client(os.environ.get('JEV_API_KEY'))
