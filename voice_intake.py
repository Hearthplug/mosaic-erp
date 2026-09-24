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
import urllib.error
import urllib.request
import uuid

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
