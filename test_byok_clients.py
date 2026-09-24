"""BYOK chat provider clients: request shapes, strict-JSON mapping, fail-closed
behaviour and retries - all against a stubbed HTTP opener, zero paid calls."""
import json, unittest, urllib.error
from byok_clients import ChatProviderClient, ProviderError, PROVIDER_SPECS
from jev_client import JevConfigError
from jev_mapper import map_text_field

OPTIONS = ['Walk-in checkout, pays on the spot', 'Order first, pay on delivery', 'Account sale, pays later']


def http_error(code):
    return urllib.error.HTTPError('https://x', code, 'err', {}, None)


class FakeResp:
    def __init__(self, payload): self.payload = payload
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def read(self): return json.dumps(self.payload).encode()


class Stub:
    """Records requests, replays queued outcomes (payloads or exceptions)."""
    def __init__(self, outcomes): self.outcomes = list(outcomes); self.calls = []
    def __call__(self, req, timeout=None):
        body = json.loads(req.data.decode())
        self.calls.append({'url': req.full_url, 'headers': dict(req.header_items()), 'body': body, 'timeout': timeout})
        out = self.outcomes.pop(0)
        if isinstance(out, Exception): raise out
        return FakeResp(out)


def openai_payload(answer):
    return {'choices': [{'message': {'content': answer}}]}


def claude_payload(answer):
    return {'content': [{'type': 'text', 'text': answer}]}


GOOD = json.dumps({'pick': OPTIONS[0], 'scores': {OPTIONS[0]: 0.9, OPTIONS[1]: 0.2, OPTIONS[2]: 0.05}})


class RequestShapes(unittest.TestCase):
    def test_openai_request_shape_and_mapping(self):
        st = Stub([openai_payload(GOOD)])
        c = ChatProviderClient('openai', 'sk-owner-key', opener=st)
        r = c.choice('customers walk in and pay at the till', OPTIONS)
        call = st.calls[0]
        self.assertEqual(call['url'], PROVIDER_SPECS['openai']['endpoint'])
        self.assertEqual(call['headers']['Authorization'], 'Bearer sk-owner-key')
        self.assertEqual(call['body']['model'], 'gpt-4o-mini')
        self.assertEqual(call['body']['response_format'], {'type': 'json_object'})
        self.assertEqual(call['body']['temperature'], 0)
        self.assertEqual(r.pick, OPTIONS[0])
        self.assertAlmostEqual(sum(r.probabilities.values()), 1.0, places=3)
        self.assertGreater(r.probabilities[OPTIONS[0]], r.probabilities[OPTIONS[1]])
        self.assertGreater(r.confidence, 0.5)
        self.assertEqual(c.label, 'openai')

    def test_deepseek_uses_openai_style_on_deepseek_endpoint(self):
        st = Stub([openai_payload(GOOD)])
        c = ChatProviderClient('deepseek', 'sk-ds', opener=st)
        c.choice('q', OPTIONS)
        self.assertEqual(st.calls[0]['url'], 'https://api.deepseek.com/chat/completions')
        self.assertEqual(st.calls[0]['body']['model'], 'deepseek-chat')

    def test_claude_request_shape(self):
        st = Stub([claude_payload(GOOD)])
        c = ChatProviderClient('claude', 'sk-ant-owner', opener=st)
        r = c.choice('q', OPTIONS)
        call = st.calls[0]
        self.assertEqual(call['url'], PROVIDER_SPECS['claude']['endpoint'])
        headers = {k.lower(): v for k, v in call['headers'].items()}
        self.assertEqual(headers['x-api-key'], 'sk-ant-owner')
        self.assertEqual(headers['anthropic-version'], '2023-06-01')
        self.assertEqual(call['body']['model'], 'claude-haiku-4-5')
        self.assertIn('system', call['body'])
        self.assertEqual(r.pick, OPTIONS[0])

    def test_requires_owner_key(self):
        for pid in PROVIDER_SPECS:
            with self.assertRaises(ProviderError):
                ChatProviderClient(pid, '')


class FailClosed(unittest.TestCase):
    def test_prose_answer_fails_closed(self):
        c = ChatProviderClient('openai', 'k', opener=Stub([openai_payload('I think walk-in checkout fits best.')]))
        with self.assertRaises(ProviderError): c.choice('q', OPTIONS)

    def test_fenced_json_is_tolerated(self):
        c = ChatProviderClient('openai', 'k', opener=Stub([openai_payload('```json\n' + GOOD + '\n```')]))
        self.assertEqual(c.choice('q', OPTIONS).pick, OPTIONS[0])

    def test_missing_scores_fail_closed(self):
        bad = json.dumps({'pick': OPTIONS[0]})
        c = ChatProviderClient('openai', 'k', opener=Stub([openai_payload(bad)]))
        with self.assertRaises(ProviderError): c.choice('q', OPTIONS)

    def test_non_numeric_score_fails_closed(self):
        bad = json.dumps({'pick': OPTIONS[0], 'scores': {OPTIONS[0]: 'high'}})
        c = ChatProviderClient('openai', 'k', opener=Stub([openai_payload(bad)]))
        with self.assertRaises(ProviderError): c.choice('q', OPTIONS)

    def test_all_zero_scores_fail_closed(self):
        bad = json.dumps({'pick': OPTIONS[0], 'scores': {o: 0 for o in OPTIONS}})
        c = ChatProviderClient('openai', 'k', opener=Stub([openai_payload(bad)]))
        with self.assertRaises(ProviderError): c.choice('q', OPTIONS)

    def test_unknown_pick_falls_back_to_top_score(self):
        bad = json.dumps({'pick': 'Something invented', 'scores': {OPTIONS[1]: 0.8, OPTIONS[0]: 0.2, OPTIONS[2]: 0.1}})
        c = ChatProviderClient('openai', 'k', opener=Stub([openai_payload(bad)]))
        self.assertEqual(c.choice('q', OPTIONS).pick, OPTIONS[1])

    def test_option_validation_still_applies(self):
        c = ChatProviderClient('openai', 'k', opener=Stub([]))
        with self.assertRaises(JevConfigError):
            c.choice('q', ['a', 'a'])

    def test_rejected_key_fails_fast_without_retry(self):
        st = Stub([http_error(401)])
        c = ChatProviderClient('openai', 'bad-key', opener=st)
        with self.assertRaises(ProviderError): c.choice('q', OPTIONS)
        self.assertEqual(len(st.calls), 1)

    def test_429_retried_then_success(self):
        st = Stub([http_error(429), http_error(500), openai_payload(GOOD)])
        c = ChatProviderClient('openai', 'k', opener=st, max_retries=3)
        import time; orig = time.sleep; time.sleep = lambda s: None
        try:
            r = c.choice('q', OPTIONS)
        finally:
            time.sleep = orig
        self.assertEqual(len(st.calls), 3)
        self.assertEqual(r.pick, OPTIONS[0])

    def test_persistent_failure_raises_provider_error(self):
        st = Stub([http_error(500), http_error(500), http_error(500)])
        c = ChatProviderClient('openai', 'k', opener=st, max_retries=3)
        import time; orig = time.sleep; time.sleep = lambda s: None
        try:
            with self.assertRaises(ProviderError): c.choice('q', OPTIONS)
        finally:
            time.sleep = orig
        self.assertEqual(len(st.calls), 3)


class MapperIntegration(unittest.TestCase):
    def test_mapper_uses_byok_client_like_any_client(self):
        c = ChatProviderClient('openai', 'k', opener=Stub([openai_payload(GOOD)]))
        spec_options = ['Walk-in checkout, pays on the spot', 'Order first, pay on delivery', 'Account sale, pays later', 'A mix of these']
        # mapper calls with its own option list; stub scores for those
        answer = json.dumps({'pick': spec_options[0], 'scores': {spec_options[0]: 0.9, spec_options[1]: 0.1, spec_options[2]: 0.05, spec_options[3]: 0.05}})
        c2 = ChatProviderClient('openai', 'k', opener=Stub([openai_payload(answer)]))
        r = map_text_field('selling', 'Customer walks in, cashier scans, pays cash', c2)
        self.assertEqual(r['proposed'], spec_options[0])
        self.assertIn(r['status'], ('auto_accept', 'confirm'))
        self.assertIn('probabilities', r)


if __name__ == '__main__':
    unittest.main()
