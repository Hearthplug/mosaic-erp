"""BYOK chat providers for answer shaping: OpenAI, Claude and DeepSeek.

Same client.choice() interface as the Jev client, mapped onto the providers'
chat APIs. The model is asked for STRICT JSON - a pick plus a 0..1 score for
every offered option - the scores are normalised into probabilities, and the
confidence uses the same margin function as the other clients, so the mapper
and reconfiguration behave identically no matter which provider shapes them.

Fail-closed: anything that is not a clean schema-valid answer (prose, markdown,
an unknown pick with unusable scores, missing scores, transport errors after
retries) raises ProviderError and nothing is mapped. The owner can switch back
to Standard at any time.

Only ever constructed with the owner's own key (BYOK) - never a shared
Hearthplug key. Tests stub the HTTP layer; the app and CI make no paid calls.
"""
import json, time, urllib.request, urllib.error
from jev_client import ChoiceResult, _validate_choice, _confidence


class ProviderError(ValueError):
    """Clean owner-facing failure (HTTP 400 via the app's ValueError path)."""


PROVIDER_SPECS = {
    'openai': {'brand': 'OpenAI', 'endpoint': 'https://api.openai.com/v1/chat/completions',
               'model': 'gpt-4o-mini', 'style': 'openai'},
    'claude': {'brand': 'Claude', 'endpoint': 'https://api.anthropic.com/v1/messages',
               'model': 'claude-haiku-4-5', 'style': 'anthropic'},
    'deepseek': {'brand': 'DeepSeek', 'endpoint': 'https://api.deepseek.com/chat/completions',
                 'model': 'deepseek-chat', 'style': 'openai'},
}

_SYSTEM = ("You map a business owner's plain-English answer to exactly one option from a fixed list. "
           'Reply with ONLY a JSON object: {"pick": "<exact option text>", '
           '"scores": {"<exact option text>": <number between 0 and 1>, ...}}. '
           'Include every listed option in scores. No prose, no markdown fences.')


def _user_prompt(question, options, context):
    lines = ['Question: ' + (question or '')]
    if context:
        lines.append('Context: ' + context)
    lines.append('Options:')
    lines.extend('- ' + o for o in options)
    return '\n'.join(lines)


def _strict_json(raw):
    """Parse the model reply as one JSON object. A single surrounding markdown
    fence is tolerated; anything else fails closed."""
    text = (raw or '').strip()
    if text.startswith('```'):
        parts = text.split('```')
        if len(parts) >= 3:
            text = parts[1]
            if text.startswith('json'):
                text = text[4:]
            text = text.strip()
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        raise ProviderError('The provider did not return a clean structured answer. Try again, or switch to Standard.')
    if not isinstance(data, dict):
        raise ProviderError('The provider returned an unexpected answer shape. Try again, or switch to Standard.')
    return data


def _scores_to_probs(data, options):
    scores = data.get('scores')
    if not isinstance(scores, dict):
        raise ProviderError('The provider answer was missing per-option scores. Try again, or switch to Standard.')
    vals = []
    for o in options:
        v = scores.get(o, 0)
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            raise ProviderError('The provider returned a non-numeric score. Try again, or switch to Standard.')
        vals.append(max(0.0, min(1.0, float(v))))
    total = sum(vals)
    if total <= 0:
        raise ProviderError('The provider could not weigh any option. Try again, or switch to Standard.')
    return {o: round(v / total, 4) for o, v in zip(options, vals)}


class ChatProviderClient:
    """One BYOK chat provider behind the shared choice() interface."""
    def __init__(self, provider, api_key, timeout=30, max_retries=3, opener=None):
        if provider not in PROVIDER_SPECS:
            raise ProviderError(f'unknown provider: {provider}')
        spec = PROVIDER_SPECS[provider]
        if not api_key:
            raise ProviderError(f"{spec['brand']} needs the owner's own API key (BYOK)")
        self.provider, self.spec, self.api_key = provider, spec, api_key
        self.label = provider
        self.timeout, self.max_retries = timeout, max_retries
        self._opener = opener or urllib.request.urlopen

    def _request(self, body):
        data = json.dumps(body).encode()
        headers = {'Content-Type': 'application/json'}
        if self.spec['style'] == 'openai':
            headers['Authorization'] = f'Bearer {self.api_key}'
        else:
            headers['x-api-key'] = self.api_key
            headers['anthropic-version'] = '2023-06-01'
        for attempt in range(self.max_retries):
            req = urllib.request.Request(self.spec['endpoint'], data=data, headers=headers)
            try:
                with self._opener(req, timeout=self.timeout) as r:
                    return json.loads(r.read().decode())
            except urllib.error.HTTPError as e:
                if e.code in (401, 403):
                    raise ProviderError(f"{self.spec['brand']} rejected the key. Check it and paste it again.") from e
                if (e.code == 429 or 500 <= e.code < 600) and attempt < self.max_retries - 1:
                    time.sleep(min(2 ** attempt, 8)); continue
                raise ProviderError(f"{self.spec['brand']} returned HTTP {e.code}. Try again, or switch to Standard.") from e
            except (urllib.error.URLError, TimeoutError, ConnectionError, json.JSONDecodeError) as e:
                if attempt < self.max_retries - 1:
                    time.sleep(min(2 ** attempt, 8)); continue
                raise ProviderError(f"{self.spec['brand']} could not be reached. Try again, or switch to Standard.") from e
        raise ProviderError(f"{self.spec['brand']} did not answer. Try again, or switch to Standard.")

    def _chat(self, question, options, context):
        if self.spec['style'] == 'openai':
            body = {'model': self.spec['model'], 'temperature': 0,
                    'response_format': {'type': 'json_object'},
                    'messages': [{'role': 'system', 'content': _SYSTEM},
                                 {'role': 'user', 'content': _user_prompt(question, options, context)}]}
            payload = self._request(body)
            try:
                return payload['choices'][0]['message']['content']
            except (KeyError, IndexError, TypeError):
                raise ProviderError(f"{self.spec['brand']} returned an unexpected response. Try again, or switch to Standard.")
        body = {'model': self.spec['model'], 'max_tokens': 1024, 'temperature': 0,
                'system': _SYSTEM,
                'messages': [{'role': 'user', 'content': _user_prompt(question, options, context)}]}
        payload = self._request(body)
        try:
            return next(b['text'] for b in payload['content'] if b.get('type') == 'text')
        except (KeyError, IndexError, TypeError, StopIteration):
            raise ProviderError(f"{self.spec['brand']} returned an unexpected response. Try again, or switch to Standard.")

    def choice(self, question, options, context=None, evidence=None):
        opts = _validate_choice(options)
        data = _strict_json(self._chat(question, opts, context))
        probs = _scores_to_probs(data, opts)
        pick = data.get('pick')
        if pick not in opts:
            pick = max(probs, key=probs.get)
        return ChoiceResult(opts, probs, pick, _confidence(list(probs.values())))


def provider_client(provider, api_key, **kw):
    """Factory used by ai_prefs: the owner's own key selects the provider."""
    return ChatProviderClient(provider, api_key, **kw)


VISION_PROVIDERS = ('openai', 'claude')

_EXTRACT_SYSTEM = ("You read a photo of a business document, screen, or notebook page for a small business owner. "
    "Reply with ONLY a JSON object: "
    '{"document_type": "<short plain name>", '
    '"fields": [{"name": "<field>", "value": "<what is written>", "confidence": <0..1>}], '
    '"summary": "<one plain sentence about what this document shows>"}. '
    "Copy values exactly as written, including currency symbols and non-Latin scripts. "
    "Use a confidence below 0.6 for anything you are unsure about. No prose, no markdown fences.")


def _extract_chat_body(client, image_b64, media_type):
    if client.spec['style'] == 'openai':
        return {'model': client.spec['model'], 'temperature': 0,
                'response_format': {'type': 'json_object'},
                'messages': [{'role': 'system', 'content': _EXTRACT_SYSTEM},
                             {'role': 'user', 'content': [
                                 {'type': 'text', 'text': 'Read this document.'},
                                 {'type': 'image_url', 'image_url': {'url': f'data:{media_type};base64,{image_b64}'}}]}]}, 'openai'
    return {'model': client.spec['model'], 'max_tokens': 2048, 'temperature': 0,
            'system': _EXTRACT_SYSTEM,
            'messages': [{'role': 'user', 'content': [
                {'type': 'image', 'source': {'type': 'base64', 'media_type': media_type, 'data': image_b64}},
                {'type': 'text', 'text': 'Read this document.'}]}]}, 'anthropic'


def _extract_image(self, image_b64, media_type):
    """Read a document photo with the owner's own vision-capable key.
    Fail-closed: non-vision providers and unreadable answers raise ProviderError."""
    if self.provider not in VISION_PROVIDERS:
        raise ProviderError(f"{self.spec['brand']} cannot read photos. Switch the key in Assistant settings to OpenAI or Claude, or type what the document shows.")
    body, style = _extract_chat_body(self, image_b64, media_type)
    payload = self._request(body)
    if style == 'openai':
        try:
            raw = payload['choices'][0]['message']['content']
        except (KeyError, IndexError, TypeError):
            raise ProviderError(f"{self.spec['brand']} returned an unexpected response. Try again, or switch to Standard.")
    else:
        try:
            raw = next(b['text'] for b in payload['content'] if b.get('type') == 'text')
        except (KeyError, IndexError, TypeError, StopIteration):
            raise ProviderError(f"{self.spec['brand']} returned an unexpected response. Try again, or switch to Standard.")
    data = _strict_json(raw)
    fields = data.get('fields')
    if not isinstance(fields, list) or not all(isinstance(f, dict) and isinstance(f.get('name'), str) for f in fields):
        raise ProviderError(f"{self.spec['brand']} returned an unreadable extraction. Try again, or type the fields.")
    cleaned = []
    for f in fields[:40]:
        try:
            conf = float(f.get('confidence', 0))
        except (TypeError, ValueError):
            conf = 0.0
        cleaned.append({'name': f['name'][:80], 'value': str(f.get('value', ''))[:500], 'confidence': min(max(conf, 0.0), 1.0)})
    return {'document_type': str(data.get('document_type', 'document'))[:80],
            'summary': str(data.get('summary', ''))[:300], 'fields': cleaned}


ChatProviderClient.extract_image = _extract_image
