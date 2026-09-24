"""Jev System One client - Choice, Score and Noul primitives with probabilities.

Mock-first by design: MockJevClient returns faithful response shapes with zero
spend so the app, CI and the eval harness all run without a key. HttpJevClient
speaks to the documented POST /v1/systemone shape (model jev-1.13.0) and is only
ever constructed with an owner's own key (BYOK) - never a shared Hearthplug key.

Research basis (docs.typesafe.ai): 64k context (32k state + question), Choice up
to 255 options, Score 2-10 levels, Noul yes/no, response carries per-option
probabilities plus a confidence value; retry on 429/529 with backoff.
English-primary: non-English input is routed to owner confirmation upstream.
"""
import json, time, random, urllib.request, urllib.error
from dataclasses import dataclass, field

MODEL = 'jev-1.13.0'
ENDPOINT = 'https://api.typesafe.ai/v1/systemone'
MAX_CHOICE_OPTIONS = 255
MIN_SCORE_LEVELS, MAX_SCORE_LEVELS = 2, 10
CONTEXT_LIMIT = 64000


class JevError(Exception): pass
class JevUnavailable(JevError): pass
class JevConfigError(JevError): pass


@dataclass
class ChoiceResult:
    options: list
    probabilities: dict
    pick: str
    confidence: float


@dataclass
class ScoreResult:
    levels: int
    probabilities: dict
    pick: int
    confidence: float


@dataclass
class NoulResult:
    answer: bool
    probability_yes: float
    confidence: float


def _validate_choice(options):
    opts = list(options)
    if not 1 <= len(opts) <= MAX_CHOICE_OPTIONS:
        raise JevConfigError(f'Choice needs 1-{MAX_CHOICE_OPTIONS} options, got {len(opts)}')
    if len(set(opts)) != len(opts):
        raise JevConfigError('Choice options must be unique')
    return opts


def _validate_levels(levels):
    if not MIN_SCORE_LEVELS <= int(levels) <= MAX_SCORE_LEVELS:
        raise JevConfigError(f'Score needs {MIN_SCORE_LEVELS}-{MAX_SCORE_LEVELS} levels, got {levels}')
    return int(levels)


def _confidence(probs):
    """Confidence = margin between top-2 probabilities (0..1), Jev-style."""
    if len(probs) < 2:
        return 1.0
    top2 = sorted(probs, reverse=True)[:2]
    return round(max(0.0, min(1.0, top2[0] - top2[1] + 0.5 * top2[0])), 4)


class HttpJevClient:
    """BYOK HTTP client for the documented System One API. Unused without a key."""
    def __init__(self, api_key, endpoint=ENDPOINT, model=MODEL, timeout=30, max_retries=4):
        if not api_key:
            raise JevConfigError('Jev requires the owner\'s own API key (BYOK)')
        self.api_key, self.endpoint, self.model = api_key, endpoint, model
        self.timeout, self.max_retries = timeout, max_retries
        self.label = 'jev'

    def _call(self, primitive, question, payload):
        body = {'model': self.model, 'primitive': primitive, 'question': question, **payload}
        if len(json.dumps(body)) > CONTEXT_LIMIT * 4:
            raise JevConfigError('question + state exceeds the 64k context window')
        data = json.dumps(body).encode()
        for attempt in range(self.max_retries):
            req = urllib.request.Request(self.endpoint, data=data, headers={
                'Authorization': f'Bearer {self.api_key}', 'Content-Type': 'application/json'})
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    return json.loads(r.read().decode())
            except urllib.error.HTTPError as e:
                if e.code in (429, 529) and attempt < self.max_retries - 1:
                    time.sleep(min(2 ** attempt, 8)); continue
                raise JevUnavailable(f'Jev HTTP {e.code}') from e
            except (urllib.error.URLError, TimeoutError) as e:
                if attempt < self.max_retries - 1:
                    time.sleep(min(2 ** attempt, 8)); continue
                raise JevUnavailable(f'Jev unreachable: {e}') from e
        raise JevUnavailable('Jev retries exhausted')

    def choice(self, question, options, context=None, evidence=None):
        opts = _validate_choice(options)
        r = self._call('choice', question, {'options': opts, 'state': context or ''})
        probs = {o: float(p) for o, p in zip(r['options'], r['probabilities'])}
        return ChoiceResult(opts, probs, r['options'][0], _confidence(list(probs.values())))

    def score(self, question, levels, context=None, evidence=None):
        lv = _validate_levels(levels)
        r = self._call('score', question, {'levels': lv, 'state': context or ''})
        probs = {i + 1: float(p) for i, p in enumerate(r['probabilities'])}
        return ScoreResult(lv, probs, max(probs, key=probs.get), _confidence(list(probs.values())))

    def noul(self, question, context=None, evidence=None):
        r = self._call('noul', question, {'state': context or ''})
        p = float(r['probability_yes'])
        return NoulResult(p >= 0.5, round(p, 4), _confidence([p, 1 - p]))


class MockJevClient:
    """Faithful zero-spend stand-in. Deterministic keyword-evidence scoring with
    Jev-shaped outputs: per-option probabilities that sum to 1 and a margin-based
    confidence. Evidence phrases are supplied by the caller's question spec; the
    mock never invents answers, it only weighs the evidence it is given."""
    def __init__(self, seed=13):
        self.rng = random.Random(seed)
        self.label = 'mock'

    def _weigh(self, question, options, evidence):
        q = question.lower()
        raw = []
        for o in options:
            hits = sum(1 for ph in evidence.get(o, ()) if ph in q)
            raw.append(1.0 + 3.0 * hits + self.rng.uniform(0, 0.15))
        total = sum(raw)
        return {o: round(w / total, 4) for o, w in zip(options, raw)}

    def choice(self, question, options, context=None, evidence=None):
        opts = _validate_choice(options)
        probs = self._weigh(question + ' ' + (context or ''), opts, evidence or {})
        return ChoiceResult(opts, probs, max(probs, key=probs.get), _confidence(list(probs.values())))

    def score(self, question, levels, context=None, evidence=None):
        lv = _validate_levels(levels)
        opts = list(range(1, lv + 1))
        probs = self._weigh(question + ' ' + (context or ''), opts, evidence or {})
        return ScoreResult(lv, probs, max(probs, key=probs.get), _confidence(list(probs.values())))

    def noul(self, question, context=None, evidence_yes=()):
        q = (question + ' ' + (context or '')).lower()
        hits = sum(1 for ph in evidence_yes if ph in q)
        p = min(0.97, 0.35 + 0.25 * hits + self.rng.uniform(0, 0.05))
        return NoulResult(p >= 0.5, round(p, 4), _confidence([p, 1 - p]))


def default_client(api_key=None):
    """App factory: real client only when an owner key exists, else the mock."""
    return HttpJevClient(api_key) if api_key else MockJevClient()
