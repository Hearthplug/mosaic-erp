"""Voice intake: turn a short recording into text the owner reviews.

Deterministic parts live here (decode, sniff, size limits, multipart body,
response cleaning). The recording itself is transcribed with the owner's own
OpenAI key (Whisper) - the same BYOK pattern as photo reading, and the same
fail-closed rule: providers without audio transcription raise ProviderError
with a plain next step, and nothing is drafted or applied until the owner
reviews the transcript.
"""
import base64
import json
import re
import urllib.error
import urllib.request
import uuid

import dayclose
from byok_clients import ProviderError

MAX_AUDIO_BYTES = 10 * 1024 * 1024  # ~2-4 minutes of compressed voice
AUDIO_TYPES = {'audio/webm', 'audio/ogg', 'audio/mp4', 'audio/mpeg', 'audio/wav', 'audio/x-m4a'}
AUDIO_PROVIDERS = ('openai',)  # Claude chat has no audio transcription endpoint

_EXT = {'audio/webm': 'webm', 'audio/ogg': 'ogg', 'audio/mp4': 'm4a',
        'audio/mpeg': 'mp3', 'audio/wav': 'wav', 'audio/x-m4a': 'm4a'}

WHISPER_ENDPOINT = 'https://api.openai.com/v1/audio/transcriptions'
WHISPER_MODEL = 'whisper-1'


def decode_audio(data_b64):
    try:
        raw = base64.b64decode(data_b64 or '', validate=True)
    except Exception:
        raise ValueError('The recording could not be read. Try recording it again.')
    if not raw:
        raise ValueError('That recording is empty.')
    if len(raw) > MAX_AUDIO_BYTES:
        raise ValueError('Recordings up to about two minutes are supported. Keep it short and try again.')
    return raw


def sniff_audio_mime(name, declared):
    """Trust a known audio content-type; fall back to the file extension."""
    if (declared or '') in AUDIO_TYPES:
        return declared
    low = (name or '').lower()
    for ext, mime in (('.webm', 'audio/webm'), ('.ogg', 'audio/ogg'), ('.m4a', 'audio/x-m4a'),
                      ('.mp4', 'audio/mp4'), ('.mp3', 'audio/mpeg'), ('.wav', 'audio/wav')):
        if low.endswith(ext):
            return mime
    return ''


def _multipart_body(fields, file_field, filename, mime, raw):
    boundary = '----mosaic' + uuid.uuid4().hex
    parts = []
    for key, value in fields:
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode())
    parts.append((f'--{boundary}\r\nContent-Disposition: form-data; name="{file_field}"; '
                  f'filename="{filename}"\r\nContent-Type: {mime}\r\n\r\n').encode() + raw + b'\r\n')
    parts.append(f'--{boundary}--\r\n'.encode())
    return b''.join(parts), f'multipart/form-data; boundary={boundary}'


def voice_status(aiprefs, wid):
    """Can this workspace use the mic? Plain reason when not (drives a disabled control, never a fake one)."""
    prefs = aiprefs.get(wid)
    provider = prefs.get('provider', 'standard')
    if provider in AUDIO_PROVIDERS and prefs.get('has_key'):
        return {'available': True, 'reason': ''}
    if provider == 'standard' or not prefs.get('has_key'):
        return {'available': False,
                'reason': 'Voice entry needs your own OpenAI key - add it in Assistant settings, or type instead.'}
    return {'available': False,
            'reason': f"Voice entry needs an OpenAI key - {prefs.get('key_brand') or provider} keys cannot transcribe recordings. Switch in Assistant settings, or type instead."}


CASH_FIELD_NAMES = ('counted cash', 'cash counted', 'cash in drawer', 'cash in the drawer', 'cash')
NOTE_FIELD_NAMES = ('note', 'notes')


def close_fields(extraction):
    """Map a parsed spoken close onto the /close form. Missing cash is reported, never guessed."""
    from build_bills import amount_minor
    counted = None
    note = ''
    for f in extraction.get('fields', []):
        name = str(f.get('name', '')).strip().lower()
        if name in CASH_FIELD_NAMES:
            counted = amount_minor(f.get('value'))
        elif name in NOTE_FIELD_NAMES:
            note = str(f.get('value', '')).strip()[:300]
    if not note and extraction.get('summary'):
        note = ''
    missing = [] if counted is not None else ['counted_cash']
    return {'counted_cash_minor': counted, 'note': note, 'missing': missing}


def transcribe_audio(client, audio_b64, name='', mime='', hint='', opener=None):
    """Transcribe a recording with the owner's own key. Fail-closed."""
    if client.provider not in AUDIO_PROVIDERS:
        raise ProviderError(f"{client.spec['brand']} cannot transcribe recordings. "
                            "Switch the key in Assistant settings to OpenAI, or type what you said.")
    raw = decode_audio(audio_b64)
    media = sniff_audio_mime(name, mime)
    if not media:
        raise ValueError('That does not look like a voice recording. Use a WebM, OGG, M4A, MP3, or WAV file.')
    fields = [('model', WHISPER_MODEL), ('response_format', 'json')]
    if hint:
        fields.append(('prompt', hint[:200]))
    body, content_type = _multipart_body(fields, 'file', 'recording.' + _EXT[media], media, raw)
    open_fn = opener or client._opener
    req = urllib.request.Request(WHISPER_ENDPOINT, data=body, headers={
        'Authorization': f'Bearer {client.api_key}', 'Content-Type': content_type})
    try:
        with open_fn(req, timeout=client.timeout) as r:
            payload = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise ProviderError(f"{client.spec['brand']} rejected the key. Check it and paste it again.") from e
        raise ProviderError(f"{client.spec['brand']} returned HTTP {e.code}. Try again, or type what you said.") from e
    except (urllib.error.URLError, TimeoutError, ConnectionError, json.JSONDecodeError) as e:
        raise ProviderError(f"{client.spec['brand']} could not be reached. Try again, or type what you said.") from e
    text = payload.get('text')
    if not isinstance(text, str):
        raise ProviderError(f"{client.spec['brand']} returned an unreadable transcript. Try again, or type what you said.")
    return {'transcript': text.strip()[:2000], 'mime': media, 'bytes': len(raw)}


_ENTRY_KINDS = ('credit', 'payment', 'sale')


def record_entry(store, books, wid, actor, payload):
    """Record one owner-reviewed spoken entry into the books. Re-validates
    everything here; never invents a name or an amount (fail closed)."""
    kind = str(payload.get('kind') or '')
    if kind not in _ENTRY_KINDS:
        raise ValueError('Pick what this entry is: credit, payment or sale.')
    detail = str(payload.get('detail') or '').strip()[:160]
    try:
        amount = int(payload.get('amount_minor'))
    except (TypeError, ValueError):
        raise ValueError('Type the amount as a number.')
    if amount <= 0:
        raise ValueError('The amount must be more than zero.')
    day = str(payload.get('day') or '').strip()
    if not re.match(r'^\d{4}-\d{2}-\d{2}$', day):
        day = dayclose.local_today(store, wid)
    party = str(payload.get('party') or '').strip()[:160]
    if kind in ('credit', 'payment') and not party:
        raise ValueError('Type the name of the person this is for.')
    cash = store._db.execute("SELECT id FROM accounts WHERE workspace_id=? AND system_key='cash'", (wid,)).fetchone()
    cash_id = cash['id'] if cash else None
    if kind == 'payment':
        row = store._db.execute("SELECT id FROM parties WHERE workspace_id=? AND kind IN ('customer','both') AND lower(name)=lower(?)", (wid, party)).fetchone()
        if not row:
            raise ValueError('No credit book entry for ' + party + ' yet - record what they took first.')
        pid = row['id']
        open_docs = store._db.execute(
            "SELECT id,balance_minor,number FROM documents WHERE workspace_id=? AND party_id=? "
            "AND kind='sales_invoice' AND status='posted' AND balance_minor>0 ORDER BY issue_date,created_at", (wid, pid)).fetchall()
        total_open = sum(int(d['balance_minor']) for d in open_docs)
        if not open_docs:
            raise ValueError(party + ' has nothing outstanding to pay against.')
        if amount > total_open:
            raise ValueError(party + ' owes less than this payment - type the exact amount they paid.')
        remaining = amount
        for d in open_docs:
            pay = min(remaining, int(d['balance_minor']))
            books.record_payment(wid, actor, d['id'], pay, day, cash_id)
            remaining -= pay
            if not remaining:
                break
        store._audit(wid, actor, 'voice_entry.payment', {'party': party, 'amount_minor': amount, 'day': day})
        return {'kind': 'payment', 'party': party, 'amount_minor': amount, 'day': day, 'remaining_minor': total_open - amount, 'currency': books.status(wid)['base_currency']}
    pid = None
    if party:
        row = store._db.execute("SELECT id FROM parties WHERE workspace_id=? AND kind IN ('customer','both') AND active=1 AND lower(name)=lower(?)", (wid, party)).fetchone()
        pid = row['id'] if row else books.create_party(wid, actor, 'customer', party)['id']
    desc = detail or ('Credit sale (spoken entry)' if kind == 'credit' else 'Sale (spoken entry)')
    doc = books.create_document(wid, actor, 'sales_invoice', day,
                                [{'description': desc, 'quantity': '1', 'unit_price_minor': amount}],
                                party_id=pid, memo='Spoken entry from the Build screen')
    books.approve_document(wid, actor, doc['id'])
    books.post_document(wid, actor, doc['id'])
    if kind == 'sale':
        books.record_payment(wid, actor, doc['id'], amount, day, cash_id)
    store._audit(wid, actor, 'voice_entry.' + kind, {'party': party, 'amount_minor': amount, 'day': day, 'document_id': doc['id']})
    return {'kind': kind, 'party': party, 'amount_minor': amount, 'day': day, 'document_id': doc['id'], 'number': doc['number'], 'currency': books.status(wid)['base_currency']}
