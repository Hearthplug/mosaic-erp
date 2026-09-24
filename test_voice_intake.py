"""Slice 7 scaffold: voice intake deterministic parts."""
import io
import json
import unittest

import voice_intake
from byok_clients import provider_client, ProviderError

B64 = voice_intake.base64.b64encode(b'fake-audio-bytes').decode()


def _client(provider='openai'):
    return provider_client(provider, 'sk-test-key')


def _ok_opener(payload):
    class R(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def open_fn(req, timeout=30):
        return R(json.dumps(payload).encode())

    return open_fn


class DecodeAndSniff(unittest.TestCase):
    def test_decode_rejects_bad_input(self):
        with self.assertRaises(ValueError):
            voice_intake.decode_audio('!!!not-base64!!!')
        with self.assertRaises(ValueError):
            voice_intake.decode_audio('')

    def test_sniff_prefers_declared_then_extension(self):
        self.assertEqual(voice_intake.sniff_audio_mime('x.bin', 'audio/webm'), 'audio/webm')
        self.assertEqual(voice_intake.sniff_audio_mime('note.m4a', ''), 'audio/x-m4a')
        self.assertEqual(voice_intake.sniff_audio_mime('note.txt', ''), '')


class Transcribe(unittest.TestCase):
    def test_non_audio_provider_fails_closed(self):
        with self.assertRaises(ProviderError) as ctx:
            voice_intake.transcribe_audio(_client('claude'), B64, 'a.webm', 'audio/webm')
        self.assertIn('OpenAI', str(ctx.exception))

    def test_rejects_non_audio_type(self):
        with self.assertRaises(ValueError):
            voice_intake.transcribe_audio(_client(), B64, 'a.txt', 'text/plain')

    def test_transcript_roundtrip(self):
        out = voice_intake.transcribe_audio(_client(), B64, 'a.webm', 'audio/webm',
                                            opener=_ok_opener({'text': ' counted two hundred dollars '}))
        self.assertEqual(out['transcript'], 'counted two hundred dollars')
        self.assertEqual(out['mime'], 'audio/webm')

    def test_unreadable_response_fails_closed(self):
        with self.assertRaises(ProviderError):
            voice_intake.transcribe_audio(_client(), B64, 'a.webm', 'audio/webm',
                                          opener=_ok_opener({'unexpected': True}))

    def test_auth_error_is_plain(self):
        import urllib.error

        def deny(req, timeout=30):
            raise urllib.error.HTTPError(req.full_url, 401, 'no', {}, None)

        with self.assertRaises(ProviderError) as ctx:
            voice_intake.transcribe_audio(_client(), B64, 'a.webm', 'audio/webm', opener=deny)
        self.assertIn('rejected the key', str(ctx.exception))

    def test_multipart_body_shape(self):
        body, ctype = voice_intake._multipart_body([('model', 'whisper-1')], 'file', 'r.webm', 'audio/webm', b'abc')
        self.assertIn('multipart/form-data; boundary=', ctype)
        self.assertIn(b'name="model"', body)
        self.assertIn(b'filename="r.webm"', body)
        self.assertTrue(body.rstrip().endswith(b'--'))


if __name__ == '__main__':
    unittest.main()
