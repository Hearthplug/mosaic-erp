"""Local assistant Preview: confirmation-gated typed-intent actions.

The local model only proposes a typed intent against the frozen v3 contract.
Mosaic validates every output fail-closed, renders the exact ERP action as an
immutable draft, and executes only after explicit shop-owner confirmation.
"Approve once" authorizes exactly one rendered payload, single-use, bound to
its hash; changed parameters are a new draft and need a new approval.
High-risk, unsupported, invalid, or fail-closed outputs can never use it.
"""
from __future__ import annotations
import hashlib, importlib.util, ipaddress, json, os, secrets, socket, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from store import Store, canon, utcnow, Conflict, NotFound

ROOT = Path(__file__).parent
CONTRACT_ROOT = ROOT / 'local_assistant_finetune' / 'v3'
DRAFT_TTL_MINUTES = 15
SYSTEM_PROMPT = 'Classify with one allowed Mosaic label, then extract only schema-approved slots. Never execute.'
UNAVAILABLE = ('The private local assistant is a Preview feature and is not active on this installation yet. '
               'Built-in chat and every normal screen keep working.')
IM_START = chr(60) + '|im_start|>'
IM_END = chr(60) + '|im_end|>'


def _load_contract():
    spec = importlib.util.spec_from_file_location('mosaic_frozen_contract_runtime', CONTRACT_ROOT / 'runtime.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    contract = module.load_contract(CONTRACT_ROOT)
    grammar = (CONTRACT_ROOT / 'intent_label.gbnf').read_text().strip()
    return module, contract, grammar


_RUNTIME, CONTRACT, LABEL_GRAMMAR = _load_contract()
LABELS = CONTRACT['labels']


class ModelError(Exception):
    """The local model endpoint did not answer safely. Always fails closed."""


def _chat_prompt(message):
    return (IM_START + 'system\n' + SYSTEM_PROMPT + IM_END + '\n'
            + IM_START + 'user\n' + message + IM_END + '\n'
            + IM_START + 'assistant\n')


def _local_base_url():
    raw = os.environ.get('MOSAIC_ASSISTANT_LOCAL_URL', '').strip() or 'http://127.0.0.1:18080'
    p = urllib.parse.urlparse(raw)
    if p.scheme not in ('http', 'https') or not p.hostname or p.username or p.password:
        raise ModelError('local assistant address must be a plain http(s) URL without credentials')
    try:
        infos = socket.getaddrinfo(p.hostname, p.port or (443 if p.scheme == 'https' else 80), type=socket.SOCK_STREAM)
    except socket.gaierror:
        raise ModelError('local assistant address did not resolve')
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_global:
            raise ModelError('local assistant address must stay on this machine or private network')
    return raw.rstrip('/')


class LocalModelClient:
    """Constrained two-stage calls to the companion llama.cpp server."""

    def __init__(self, base=None, timeout=20):
        self.base = base if base is not None else _local_base_url()
        self.timeout = timeout

    def _complete(self, body):
        data = canon(body).encode()
        req = urllib.request.Request(self.base + '/completion', data=data,
                                     headers={'Content-Type': 'application/json'}, method='POST')
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as res:
                raw = res.read(65537)
        except Exception as exc:
            raise ModelError('local assistant endpoint failed: ' + type(exc).__name__)
        if len(raw) > 65536:
            raise ModelError('local assistant response too large')
        try:
            out = json.loads(raw)
            content = out['content']
        except (ValueError, KeyError, TypeError):
            raise ModelError('local assistant response was not valid')
        if not isinstance(content, str):
            raise ModelError('local assistant response was not valid')
        return content

    def classify(self, message):
        body = {'prompt': _chat_prompt(message), 'grammar': LABEL_GRAMMAR, 'temperature': 0,
                'max_tokens': 24, 'stop': ['\n', IM_END], 'cache_prompt': True}
        label = self._complete(body).strip()
        if label not in LABELS:
            raise ModelError('local assistant returned an unknown label')
        return label

    def fill_slots(self, message, label):
        schema = CONTRACT['schemas'][LABELS[label]]
        body = {'prompt': _chat_prompt(message) + label + '\n', 'json_schema': schema, 'temperature': 0,
                'max_tokens': 200, 'stop': [IM_END], 'cache_prompt': True}
        raw = self._complete(body).strip()
        try:
            slots = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            raise ModelError('local assistant returned invalid slots')
        if not isinstance(slots, dict):
            raise ModelError('local assistant returned invalid slots')
        return slots


def availability():
    """Verified native amd64+arm64 evidence, or None when the Preview stays off."""
    path = os.environ.get('MOSAIC_ASSISTANT_LOCAL_AVAILABILITY_FILE', '').strip()
    if not path:
        return None
    try:
        doc = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(doc, dict) or doc.get('schema') != 'mosaic-local-availability-v1' or doc.get('available') is not True:
        return None
    verdicts = doc.get('verdicts')
    if not isinstance(verdicts, list) or {v.get('architecture') for v in verdicts if isinstance(v, dict)} != {'amd64', 'arm64'}:
        return None
    if not all(isinstance(v, dict) and v.get('passed') is True for v in verdicts):
        return None
    return doc


def _payload_hash(payload):
    return hashlib.sha256(canon(payload).encode()).hexdigest()


def _build_product_create(preview, wid, slots):
    sku = 'SKU-' + secrets.token_hex(4).upper()
    params = {'sku': sku, 'name': slots['name'], 'selling_price_minor': 0, 'cost_minor': 0, 'unit': 'each'}
    rendered = ("Create product '" + params['name'] + "' with SKU " + sku +
                '. Price and cost are not set yet (0); edit the product afterwards to set them.')
    return {'op': 'retail.product.create', 'params': params}, rendered


def _build_stock_status(preview, wid, slots):
    ref = slots['product_ref']
    row = preview.s._db.execute(
        'SELECT id, name, sku FROM retail_products WHERE workspace_id=? AND (sku=? OR id=?)', (wid, ref, ref)).fetchone()
    if not row:
        return None, None
    params = {'product_id': row['id'], 'product_ref': ref, 'product_name': row['name']}
    rendered = "Check current stock for '" + row['name'] + "' (" + ref + ') across every location. This only reads data.'
    return {'op': 'retail.stock.status', 'params': params}, rendered


def _build_workspace_invite(preview, wid, slots):
    team = slots['role']
    operational = 'Cashier · sell & return' if team == 'cashier' else 'Manager · approve & transfer'
    params = {'team_role': team, 'operational_role': operational, 'expires_hours': 72}
    rendered = ('Create a ' + team + ' invitation link (valid 72 hours). The person joins only after accepting; '
                'their operational permissions apply when they accept.')
    return {'op': 'workspace.invite', 'params': params}, rendered


def _exec_product_create(preview, wid, actor, params):
    result = preview.retail.product(wid, actor, params['sku'], params['name'],
                                    params['selling_price_minor'], params['cost_minor'], unit=params['unit'])
    return {'product_id': result['id'], 'sku': result['sku'], 'name': result['name']}, 'Product created.'


def _exec_stock_status(preview, wid, actor, params):
    rows = preview.s._db.execute(
        "SELECT l.name, COALESCE(SUM(CAST(sl.quantity_delta AS REAL)),0) q FROM stock_ledger sl "
        "JOIN locations l ON l.id=sl.location_id AND l.workspace_id=sl.workspace_id "
        "WHERE sl.workspace_id=? AND sl.product_id=? GROUP BY sl.location_id ORDER BY l.name",
        (wid, params['product_id'])).fetchall()
    levels = [{'location': r['name'], 'quantity': r['q']} for r in rows]
    total = sum(r['q'] for r in rows)
    text = 'Total stock: ' + ('%g' % total) + '. ' + ('; '.join(x['location'] + ': ' + ('%g' % x['quantity']) for x in levels) if levels else 'No stock movements yet.')
    return {'levels': levels, 'total': total}, text


def _exec_workspace_invite(preview, wid, actor, params):
    result = preview.s.create_invitation(wid, '', 'viewer', params['operational_role'], actor, ttl_hours=params['expires_hours'])
    url = '/invite?token=' + result.pop('invite_token')
    return {'invitation_id': result['invitation_id'], 'expires_at': result['expires_at']}, 'Invitation created. Share this link: ' + url


BINDINGS = {
    'retail.product.create': {'risk': 'standard', 'role': 'editor', 'build': _build_product_create, 'execute': _exec_product_create},
    'retail.stock.status': {'risk': 'standard', 'role': 'viewer', 'build': _build_stock_status, 'execute': _exec_stock_status},
    'workspace.invite': {'risk': 'standard', 'role': 'owner', 'build': _build_workspace_invite, 'execute': _exec_workspace_invite},
}

# Understood by the model but not executable in the Preview: explained, never drafted.
EXPLAIN_ONLY = {
    'retail.purchase.create', 'retail.sale.create', 'accounting.party.create', 'accounting.bank.import',
    'accounting.document.create', 'accounting.journal.reverse', 'accounting.period.create', 'migration.stage',
    'workspace.config.preview', 'accounting.setup.preview', 'artifact.draft', 'assistant.configure', 'assistant.cancel',
}
GUIDANCE_KINDS = {'guidance', 'guidance.docker', 'guidance.kubernetes'}


class AssistantPreview:
    """Preview runtime: draft -> explicit confirmation or Approve once -> execute once."""

    def __init__(self, store, retail, setup, client=None):
        self.s = store
        self.retail = retail
        self.setup = setup
        self.client = client

    def ready(self, wid):
        try:
            settings = self.setup.get(wid)
        except Exception:
            return False
        return settings.get('mode') == 'local' and settings.get('status') == 'ready' and availability() is not None

    def _infer(self, message):
        client = self.client or LocalModelClient()
        label = client.classify(message)
        slots = client.fill_slots(message, label)
        rendered = _RUNTIME.render_typed_intent(label, slots, 1.0, CONTRACT)
        return rendered['kind'], rendered['slots']

    def chat(self, wid, actor, role, message):
        text = ' '.join((message or '').strip().split())
        if not self.ready(wid):
            return {'reply': UNAVAILABLE, 'preview_available': False}
        if not text:
            return {'reply': 'Local assistant Preview is active. Describe what you want in everyday words; '
                             'every action still needs your explicit confirmation before anything changes.',
                    'preview_available': True}
        try:
            kind, slots = self._infer(text)
        except ModelError as exc:
            with self.s.tx():
                self.s._audit(wid, actor, 'assistant.preview.model_error', {'reason': str(exc)[:120]})
            return {'reply': 'The local assistant did not produce a safe answer, so nothing was drafted. '
                             'Try rephrasing, or use the normal screens.', 'preview_available': True}
        if kind == 'clarify':
            return {'reply': 'I am not sure what you mean. Can you rephrase or add the missing detail?',
                    'preview_available': True, 'kind': kind}
        if kind == 'reject':
            return {'reply': 'I cannot help with that request. Destructive, bulk, or unsafe changes are never '
                             'performed by the assistant.', 'preview_available': True, 'kind': kind}
        if kind in GUIDANCE_KINDS:
            topic = slots.get('topic', '')
            return {'reply': 'Guidance: ' + (topic or 'general') + '. Step-by-step help lives in the deployment '
                             'guides (docs/DEPLOYMENT.md). The Preview does not change anything for guidance requests.',
                    'preview_available': True, 'kind': kind}
        if kind in EXPLAIN_ONLY:
            return {'reply': 'I understood the action you want, but the Preview cannot execute this type of change '
                             'yet. Nothing was drafted or changed; please use the normal screen for it.',
                    'preview_available': True, 'kind': kind}
        spec = BINDINGS.get(kind)
        if not spec:
            return {'reply': 'That request is not supported by the Preview, so nothing was drafted.',
                    'preview_available': True, 'kind': 'clarify'}
        if not Store.role_ok(role, spec['role']):
            return {'reply': 'This action needs the ' + spec['role'] + ' role; your key does not allow it. '
                             'Nothing was drafted.', 'preview_available': True, 'kind': kind}
        payload, rendered = spec['build'](self, wid, slots)
        if payload is None:
            return {'reply': 'I could not find that record in this workspace. Check the reference and try again.',
                    'preview_available': True, 'kind': 'clarify'}
        draft_id = 'adr_' + secrets.token_hex(8)
        expires = (datetime.now(timezone.utc) + timedelta(minutes=DRAFT_TTL_MINUTES)).isoformat()
        with self.s.tx():
            self.s._db.execute(
                'INSERT INTO assistant_action_drafts(id,workspace_id,kind,payload_json,payload_hash,rendered_text,'
                'risk,approval_mode,status,created_by,created_at,expires_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                (draft_id, wid, kind, canon(payload), _payload_hash(payload), rendered, spec['risk'],
                 'confirm', 'pending', actor, utcnow(), expires))
            self.s._audit(wid, actor, 'assistant.preview.draft',
                          {'draft_id': draft_id, 'kind': kind, 'payload_hash': _payload_hash(payload), 'risk': spec['risk']})
        return {'reply': rendered + ' Confirm to run it once, approve once to authorize this exact action, '
                        'or cancel to discard it. It expires in ' + str(DRAFT_TTL_MINUTES) + ' minutes.',
                'preview_available': True, 'kind': kind,
                'draft': {'id': draft_id, 'kind': kind, 'rendered': rendered, 'risk': spec['risk'],
                          'expires_at': expires, 'approve_once_allowed': spec['risk'] == 'standard',
                          'payload': payload}}

    def _load_pending(self, wid, draft_id):
        row = self.s._db.execute('SELECT * FROM assistant_action_drafts WHERE id=? AND workspace_id=?',
                                 (draft_id, wid)).fetchone()
        if not row:
            raise NotFound('assistant draft not found')
        row = dict(row)
        if row['status'] == 'pending' and datetime.fromisoformat(row['expires_at']) <= datetime.now(timezone.utc):
            with self.s.tx():
                self.s._db.execute("UPDATE assistant_action_drafts SET status='expired',resolved_at=? WHERE id=? AND status='pending'",
                                   (utcnow(), draft_id))
            row['status'] = 'expired'
        return row

    def confirm(self, wid, actor, role, draft_id, approve_once=False):
        row = self._load_pending(wid, draft_id)
        if row['status'] != 'pending':
            raise Conflict('this draft was already ' + row['status'] + '; approvals are single-use')
        spec = BINDINGS.get(row['kind'])
        if not spec:
            raise Conflict('this action type is not executable in the Preview')
        if not Store.role_ok(role, spec['role']):
            raise ValueError('this action needs the ' + spec['role'] + ' role')
        if approve_once and row['risk'] != 'standard':
            raise Conflict('Approve once is only available for standard actions; high-risk actions are never auto-approved')
        payload = json.loads(row['payload_json'])
        if _payload_hash(payload) != row['payload_hash']:
            with self.s.tx():
                self.s._audit(wid, actor, 'assistant.preview.payload_mismatch', {'draft_id': draft_id})
            raise Conflict('the rendered action changed; a new approval is required')
        mode = 'approve_once' if approve_once else 'confirm'
        with self.s.tx():
            claimed = self.s._db.execute(
                "UPDATE assistant_action_drafts SET status='executed',approval_mode=?,resolved_by=?,resolved_at=? "
                "WHERE id=? AND workspace_id=? AND status='pending'",
                (mode, actor, utcnow(), draft_id, wid)).rowcount
            if claimed != 1:
                raise Conflict('this draft was already resolved; approvals are single-use')
            result, text = spec['execute'](self, wid, actor, payload['params'])
            stored = dict(result)
            stored.pop('invite_token', None)
            self.s._db.execute('UPDATE assistant_action_drafts SET result_json=? WHERE id=?', (canon(stored), draft_id))
            self.s._audit(wid, actor, 'assistant.preview.execute',
                          {'draft_id': draft_id, 'kind': row['kind'], 'payload_hash': row['payload_hash'],
                           'approval_mode': mode})
        return {'status': 'executed', 'draft_id': draft_id, 'approval_mode': mode, 'result': result, 'reply': text}

    def cancel(self, wid, actor, draft_id):
        row = self._load_pending(wid, draft_id)
        if row['status'] != 'pending':
            raise Conflict('this draft was already ' + row['status'])
        with self.s.tx():
            self.s._db.execute(
                "UPDATE assistant_action_drafts SET status='cancelled',resolved_by=?,resolved_at=? WHERE id=? AND status='pending'",
                (actor, utcnow(), draft_id))
            self.s._audit(wid, actor, 'assistant.preview.cancel',
                          {'draft_id': draft_id, 'kind': row['kind'], 'payload_hash': row['payload_hash']})
        return {'status': 'cancelled', 'draft_id': draft_id, 'reply': 'Draft discarded. Nothing was changed.'}
