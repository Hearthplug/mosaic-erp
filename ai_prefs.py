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
    {'id': 'custom', 'name': 'OpenAI-compatible (your own server)',
     'line': 'Any server that speaks the OpenAI API - Ollama, LM Studio, LocalAI, vLLM or a self-hosted Whisper. Set its address and models; a key is optional.',
     'available': True, 'needs_key': False, 'key_brand': 'Custom server'},
)
CONSENT_NOTE = 'With a key option, your interview answers go to that provider to be mapped. Standard keeps everything inside Mosaic.'
KEY_PROVIDERS = tuple(p['id'] for p in PROVIDERS if p['needs_key'])
BRANDS = {p['id']: p.get('key_brand', '') for p in PROVIDERS}


class AiPrefs:
    def __init__(self, store):
        self.s = store

    def _row(self, wid):
        return self.s._db.execute('SELECT provider,key_ref,config FROM ai_answer_prefs WHERE workspace_id=?', (wid,)).fetchone()

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
        custom = {}
        if provider == 'custom' and r and r['config']:
            try:
                saved = json.loads(r['config'])
                custom = {'base_url': saved.get('base_url', ''), 'models': saved.get('models', {})}
            except ValueError:
                custom = {}
        return {'provider': provider, 'has_key': provider in refs,
                'key_brand': BRANDS.get(provider, ''),
                'key_storage': bool(os.environ.get('MOSAIC_ASSISTANT_SECRET_DIR', '').strip()),
                'custom': custom,
                'options': list(PROVIDERS), 'consent_note': CONSENT_NOTE}

    @staticmethod
    def _clean_custom(config):
        base = str((config or {}).get('base_url') or '').strip().rstrip('/')
        if not base.startswith(('http://', 'https://')):
            raise ValueError('Set the server address, starting with http:// or https:// - for example http://localhost:8080/v1')
        if len(base) > 500:
            raise ValueError('The server address is too long.')
        models = (config or {}).get('models') or {}
        clean = {}
        for cap in ('chat', 'vision', 'transcription'):
            m = str(models.get(cap) or '').strip()[:120]
            if m:
                clean[cap] = m
        if not clean.get('chat'):
            raise ValueError('Set at least the chat model name - the name the server knows it by, for example llama3.1 or qwen2.5.')
        return {'base_url': base, 'models': clean}

    def set_provider(self, wid, actor, provider, api_key='', config=None):
        if provider not in tuple(p['id'] for p in PROVIDERS):
            raise ValueError('provider must be one of: ' + ', '.join(p['id'] for p in PROVIDERS))
        r = self._row(wid)
        refs = self._refs(r['key_ref']) if r else {}
        custom_cfg = self._clean_custom(config) if provider == 'custom' else (r['config'] if r else '')
        if api_key:
            if provider != 'custom' and provider not in KEY_PROVIDERS:
                raise ValueError(f"{provider} does not take a key")
            refs[provider] = self._save_key(wid, provider, api_key)
        if provider in KEY_PROVIDERS and provider not in refs:
            raise ValueError(f"{BRANDS[provider]} needs your own key. Paste it to continue.")
        with self.s.tx():
            self.s._db.execute(
                'INSERT INTO ai_answer_prefs(workspace_id,provider,key_ref,config,updated_by,updated_at) VALUES(?,?,?,?,?,?) '
                'ON CONFLICT(workspace_id) DO UPDATE SET provider=excluded.provider,key_ref=excluded.key_ref,config=excluded.config,updated_by=excluded.updated_by,updated_at=excluded.updated_at',
                (wid, provider, json.dumps(refs, sort_keys=True),
                 json.dumps(custom_cfg, sort_keys=True) if isinstance(custom_cfg, dict) else (custom_cfg or ''), actor, utcnow()))
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
            key = self._read_key(ref) if ref.startswith('file:') else ''
            if provider == 'custom' and r['config']:
                try:
                    cfg = json.loads(r['config'])
                except ValueError:
                    cfg = {}
                if cfg.get('base_url'):
                    return provider_client('custom', key, config=cfg)
            if key:
                if provider == 'jev':
                    return HttpJevClient(key)
                if provider in PROVIDER_SPECS:
                    return provider_client(provider, key)
        return default_client(os.environ.get('JEV_API_KEY'))


    def test_connection(self, wid, provider, api_key='', config=None):
        """Try the proposed (or saved) provider settings for real: one tiny chat
        call on the owner's key or server. Returns {ok, detail} and never saves."""
        from byok_clients import ChatProviderClient, ProviderError, _chat_once
        try:
            row = self._row(wid)
            saved_refs = self._refs(row['key_ref']) if row else {}
            if provider == 'custom':
                cfg = self._clean_custom(config)
                key = api_key or ''
                if not key:
                    ref = saved_refs.get('custom', '')
                    key = self._read_key(ref) if ref.startswith('file:') else ''
                client = ChatProviderClient('custom', key, config=cfg, timeout=15, max_retries=1)
            elif provider in PROVIDER_SPECS:
                key = api_key or ''
                if not key:
                    ref = saved_refs.get(provider, '')
                    key = self._read_key(ref) if ref.startswith('file:') else ''
                client = ChatProviderClient(provider, key, timeout=15, max_retries=1)
            else:
                return {'ok': False, 'detail': 'Only key providers and custom servers can be tested.'}
            models = client.spec.get('models') or {}
            caps = [('chat', models.get('chat') or client.spec['model'])]
            if models.get('vision'):
                caps.append(('vision', models['vision']))
            if models.get('transcription'):
                caps.append(('transcription', models['transcription']))
            answered = []
            for cap, model in caps:
                try:
                    if cap == 'chat':
                        _chat_once(client, 'You are a connectivity check.', 'Reply with the word OK.')
                    elif cap == 'transcription':
                        from voice_intake import transcribe_audio
                        transcribe_audio(client, _silent_wav_b64(), name='probe.wav', mime='audio/wav')
                    else:
                        from byok_clients import _extract_chat_body, _vision_model
                        body, _style = _extract_chat_body(client, _ONE_PIXEL_PNG, 'image/png')
                        body['model'] = _vision_model(client)
                        client._request(body)
                    answered.append((cap, model))
                except (ProviderError, ValueError) as e:
                    names = ' and '.join(c + ' (' + m + ')' for c, m in answered)
                    prefix = (names + ' answered, but ') if answered else 'Could not connect - '
                    return {'ok': False, 'detail': prefix + cap + ' (' + model + ') did not answer: ' + str(e)}
            names = [c + ' (' + m + ')' for c, m in answered]
            if len(names) == 1:
                listed = names[0]; verb = ' answered.'
            elif len(names) == 2:
                listed = ' and '.join(names); verb = ' both answered.'
            else:
                listed = ', '.join(names[:-1]) + ' and ' + names[-1]; verb = ' all answered.'
            return {'ok': True, 'detail': 'Connected - ' + listed + verb}
        except (ProviderError, ValueError) as e:
            return {'ok': False, 'detail': str(e)}


_ONE_PIXEL_PNG = ('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQ'
                  'AAAABJRU5ErkJggg==')


def _silent_wav_b64():
    import base64, struct
    frames = b'\x00\x00' * 800  # 0.05s of silence, 16 kHz 16-bit mono
    hdr = (b'RIFF' + struct.pack('<I', 36 + len(frames)) + b'WAVEfmt ' +
           struct.pack('<IHHIIHH', 16, 1, 1, 16000, 32000, 2, 16) +
           b'data' + struct.pack('<I', len(frames)))
    return base64.b64encode(hdr + frames).decode()
