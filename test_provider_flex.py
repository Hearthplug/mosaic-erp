"""Slice 8: custom OpenAI-compatible provider across every AI capability."""
import json
import unittest
import urllib.error

import ai_prefs
import byok_clients
import voice_intake
from store import Store
import tempfile


def _store():
    s = Store(tempfile.mktemp(suffix='.db'))
    wid, _ = s.create_workspace('Flex Co')
    return s, wid


class _FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def read(self):
        return json.dumps(self.payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class CustomProvider(unittest.TestCase):
    CFG = {'base_url': 'http://localhost:8080/v1',
           'models': {'chat': 'llama3.1', 'vision': 'llava', 'transcription': 'whisper-large-v3'}}

    def test_set_and_get(self):
        s, wid = _store()
        p = ai_prefs.AiPrefs(s)
        import os
        os.environ['MOSAIC_ASSISTANT_SECRET_DIR'] = tempfile.mkdtemp()
        out = p.set_provider(wid, 'owner', 'custom', config=self.CFG)
        self.assertEqual(out['provider'], 'custom')
        self.assertEqual(out['custom']['base_url'], 'http://localhost:8080/v1')
        self.assertEqual(out['custom']['models']['transcription'], 'whisper-large-v3')

    def test_validation(self):
        s, wid = _store()
        p = ai_prefs.AiPrefs(s)
        with self.assertRaises(ValueError):
            p.set_provider(wid, 'owner', 'custom', config={'base_url': 'localhost:8080', 'models': {'chat': 'x'}})
        with self.assertRaises(ValueError):
            p.set_provider(wid, 'owner', 'custom', config={'base_url': 'http://x/v1', 'models': {}})

    def test_client_uses_per_capability_models(self):
        c = byok_clients.ChatProviderClient('custom', '', config=self.CFG)
        self.assertEqual(c.spec['endpoint'], 'http://localhost:8080/v1/chat/completions')
        self.assertEqual(c.spec['model'], 'llama3.1')
        audio = c.audio_spec()
        self.assertEqual(audio['endpoint'], 'http://localhost:8080/v1/audio/transcriptions')
        self.assertEqual(audio['model'], 'whisper-large-v3')
        seen = {}

        def opener(req, timeout=30):
            seen['auth'] = req.headers.get('Authorization')
            return _FakeResponse({'choices': [{'message': {'content': '{"document_type":"doc","fields":[],"summary":"s","lines":[]}'}}]})
        c2 = byok_clients.ChatProviderClient('custom', '', config=self.CFG, opener=opener)
        c2.extract_transcript('hello')
        self.assertIsNone(seen['auth'])  # keyless local server sends no Authorization

    def test_custom_without_transcription_fails_closed(self):
        c = byok_clients.ChatProviderClient('custom', '', config={'base_url': 'http://x/v1', 'models': {'chat': 'm'}})
        self.assertIsNone(c.audio_spec())
        with self.assertRaises(byok_clients.ProviderError) as ctx:
            voice_intake.transcribe_audio(c, 'AAAA', 'a.webm', 'audio/webm')
        self.assertIn('no transcription model', str(ctx.exception))
        with self.assertRaises(byok_clients.ProviderError) as ctx2:
            c.extract_image('AAAA', 'image/png')
        self.assertIn('no vision model', str(ctx2.exception))

    def test_voice_status_custom(self):
        s, wid = _store()
        p = ai_prefs.AiPrefs(s)
        import os
        os.environ['MOSAIC_ASSISTANT_SECRET_DIR'] = tempfile.mkdtemp()
        p.set_provider(wid, 'owner', 'custom', config=self.CFG)
        self.assertTrue(voice_intake.voice_status(p, wid)['available'])
        p.set_provider(wid, 'owner', 'custom', config={'base_url': 'http://x/v1', 'models': {'chat': 'm'}})
        st = voice_intake.voice_status(p, wid)
        self.assertFalse(st['available'])
        self.assertIn('transcription model', st['reason'])

    def test_transcribe_hits_custom_endpoint(self):
        c = byok_clients.ChatProviderClient('custom', 'k', config=self.CFG)
        seen = {}

        def opener(req, timeout=30):
            seen['url'] = req.full_url
            seen['auth'] = req.headers.get('Authorization')
            seen['body'] = req.data.decode('utf-8', 'replace')
            return _FakeResponse({'text': 'hello world'})
        import base64
        out = voice_intake.transcribe_audio(c, base64.b64encode(b'x' * 50).decode(), 'a.webm', 'audio/webm', opener=opener)
        self.assertEqual(out['transcript'], 'hello world')
        self.assertEqual(seen['url'], 'http://localhost:8080/v1/audio/transcriptions')
        self.assertEqual(seen['auth'], 'Bearer k')
        self.assertIn('whisper-large-v3', seen['body'])

    def test_test_connection(self):
        s, wid = _store()
        p = ai_prefs.AiPrefs(s)
        bad = p.test_connection(wid, 'custom', config={'base_url': 'http://127.0.0.1:9/v1', 'models': {'chat': 'm'}})
        self.assertFalse(bad['ok'])
        self.assertTrue(bad['detail'])


if __name__ == '__main__':
    unittest.main()
