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


class VoiceStatusAndCloseFields(unittest.TestCase):
    class _Prefs:
        def __init__(self, provider, has_key):
            self.p, self.k = provider, has_key

        def get(self, wid):
            return {'provider': self.p, 'has_key': self.k, 'key_brand': self.p.title()}

    def test_status(self):
        ok = voice_intake.voice_status(self._Prefs('openai', True), 'w')
        self.assertTrue(ok['available'])
        no_key = voice_intake.voice_status(self._Prefs('openai', False), 'w')
        self.assertFalse(no_key['available']); self.assertIn('OpenAI key', no_key['reason'])
        claude = voice_intake.voice_status(self._Prefs('claude', True), 'w')
        self.assertFalse(claude['available']); self.assertIn('cannot transcribe', claude['reason'])
        standard = voice_intake.voice_status(self._Prefs('standard', False), 'w')
        self.assertFalse(standard['available'])

    def test_close_fields(self):
        out = voice_intake.close_fields({'fields': [
            {'name': 'counted cash', 'value': '157', 'confidence': 0.9},
            {'name': 'note', 'value': 'kept 50 for float', 'confidence': 0.8}], 'summary': 'x'})
        self.assertEqual(out['counted_cash_minor'], 15700)
        self.assertEqual(out['note'], 'kept 50 for float')
        self.assertEqual(out['missing'], [])
        miss = voice_intake.close_fields({'fields': [{'name': 'note', 'value': 'hi'}], 'summary': 'x'})
        self.assertIsNone(miss['counted_cash_minor'])
        self.assertEqual(miss['missing'], ['counted_cash'])


class RecordEntry(unittest.TestCase):
    def _store(self):
        import tempfile
        from store import Store
        from accounting import Accounting
        s = Store(tempfile.mktemp(suffix='.db'))
        wid, _ = s.create_workspace('Voice Shop')
        b = Accounting(s)
        b.setup(wid, 'owner', 'USD')
        b.add_period(wid, 'owner', 'FY26', '2026-01-01', '2026-12-31')
        return s, b, wid

    def test_credit_then_payment_then_sale(self):
        s, b, wid = self._store()
        r = voice_intake.record_entry(s, b, wid, 'owner', {'kind': 'credit', 'party': 'Ravi', 'detail': 'rice and oil', 'amount_minor': 50000})
        self.assertEqual(r['kind'], 'credit')
        open_docs = s._db.execute("SELECT balance_minor FROM documents WHERE workspace_id=? AND kind='sales_invoice'", (wid,)).fetchall()
        self.assertEqual(sum(int(d['balance_minor']) for d in open_docs), 50000)
        r2 = voice_intake.record_entry(s, b, wid, 'owner', {'kind': 'payment', 'party': 'ravi', 'amount_minor': 20000})
        self.assertEqual(r2['remaining_minor'], 30000)
        r3 = voice_intake.record_entry(s, b, wid, 'owner', {'kind': 'sale', 'detail': 'bread', 'amount_minor': 700})
        doc = s._db.execute('SELECT balance_minor,total_minor FROM documents WHERE id=?', (r3['document_id'],)).fetchone()
        self.assertEqual(int(doc['balance_minor']), 0)

    def test_fail_closed(self):
        s, b, wid = self._store()
        with self.assertRaises(ValueError):
            voice_intake.record_entry(s, b, wid, 'owner', {'kind': 'credit', 'detail': 'x', 'amount_minor': 100})
        with self.assertRaises(ValueError):
            voice_intake.record_entry(s, b, wid, 'owner', {'kind': 'credit', 'party': 'Ravi', 'amount_minor': 0})
        with self.assertRaises(ValueError):
            voice_intake.record_entry(s, b, wid, 'owner', {'kind': 'payment', 'party': 'Nobody', 'amount_minor': 100})
        voice_intake.record_entry(s, b, wid, 'owner', {'kind': 'credit', 'party': 'Ravi', 'amount_minor': 1000})
        with self.assertRaises(ValueError):
            voice_intake.record_entry(s, b, wid, 'owner', {'kind': 'payment', 'party': 'Ravi', 'amount_minor': 2000})
        docs = s._db.execute("SELECT COUNT(*) n FROM documents WHERE workspace_id=?", (wid,)).fetchone()['n']
        self.assertEqual(docs, 1)


if __name__ == '__main__':
    unittest.main()
