"""Dodo test-mode webhook adapter. No checkout, prices, or live entitlements."""
import base64
import binascii
import hashlib
import hmac
import json
import time
from datetime import datetime, timezone
from store import Conflict, utcnow

# Dodo follows Standard Webhooks: signed message-id.timestamp.raw-body.
STATES = {'pending':'trialing', 'active':'active', 'on_hold':'past_due',
          'past_due':'past_due', 'paused':'paused', 'cancelled':'canceled',
          'failed':'canceled', 'expired':'expired'}
EVENTS = frozenset(('subscription.active', 'subscription.updated',
    'subscription.on_hold', 'subscription.paused', 'subscription.unpaused',
    'subscription.renewed', 'subscription.plan_changed',
    'subscription.update_payment_method', 'subscription.cancelled',
    'subscription.failed', 'subscription.expired'))

def _field(value):
    return isinstance(value, str) and bool(value.strip()) and len(value) <= 256

def verify_dodo_signature(body, message_id, timestamp, signature, secret, now=None):
    """Verify exact raw bytes, fresh Standard Webhooks headers and whsec_ key."""
    if not isinstance(body, bytes) or not all(map(_field, (message_id, timestamp, signature, secret))):
        return False
    if not timestamp.isdecimal() or not secret.startswith('whsec_'):
        return False
    current = int(time.time() if now is None else now)
    if abs(current-int(timestamp)) > 300:
        return False
    try:
        key = base64.b64decode(secret[6:], validate=True)
    except (ValueError, binascii.Error):
        return False
    if len(key) < 24:
        return False
    signed = message_id.encode() + b'.' + timestamp.encode() + b'.' + body
    expected = hmac.new(key, signed, hashlib.sha256).digest()
    for token in signature.split(' '):
        if not token.startswith('v1,'):
            continue
        try:
            received = base64.b64decode(token[3:], validate=True)
        except (ValueError, binascii.Error):
            continue
        if hmac.compare_digest(expected, received):
            return True
    return False

def bind_dodo_test_subscription(store, workspace_id, subscription_id, product_id, nonce):
    """Bind only a signed Dodo TEST webhook to a server-recorded checkout intent.

    The random nonce was sent to Dodo at test checkout creation. Never bind based
    on an unrecognized subscription's workspace hint alone.
    """
    if not all(map(_field,(workspace_id,subscription_id,product_id,nonce))) or not workspace_id.startswith('wsp_'):
        raise ValueError('Invalid subscription binding')
    with store.tx():
        intent=store._db.execute('SELECT product_id,subscription_id FROM dodo_test_checkout_intents WHERE workspace_id=? AND nonce=?',
                                 (workspace_id,nonce)).fetchone()
        if not intent or intent['product_id'] != product_id or (intent['subscription_id'] and intent['subscription_id'] != subscription_id):
            raise ValueError('No matching test checkout intent')
        if not intent['subscription_id']:
            store._db.execute('UPDATE dodo_test_checkout_intents SET subscription_id=? WHERE workspace_id=? AND nonce=? AND subscription_id IS NULL',(subscription_id,workspace_id,nonce))
        prior=store._db.execute('SELECT workspace_id,plan_ref FROM billing_subscriptions WHERE workspace_id=? AND provider=? AND external_id=?',
                                (workspace_id,'dodo_test',subscription_id)).fetchone()
        if prior:
            if prior['plan_ref'] != product_id:raise Conflict('Subscription product changed')
            return
        store._db.execute('INSERT INTO billing_subscriptions(workspace_id,provider,external_id,plan_ref,status,period_end,last_event_at,updated_at) VALUES(?,?,?,?,?,?,?,?)',
                          (workspace_id,'dodo_test',subscription_id,product_id,'trialing',None,'',utcnow()))

def apply_dodo_test_webhook(store, workspace_id, body, message_id):
    """Apply signed, recognized event to a previously bound subscription only."""
    if not _field(message_id) or not _field(workspace_id) or not workspace_id.startswith('wsp_'):
        raise ValueError('Invalid binding context')
    try: event=json.loads(body)
    except (ValueError, TypeError, UnicodeError):raise ValueError('Invalid webhook JSON')
    if not isinstance(event,dict):raise ValueError('Invalid webhook payload')
    kind=event.get('type')
    if not isinstance(kind,str):raise ValueError('Invalid event type')
    if kind not in EVENTS:return {'accepted':True,'ignored':True}
    data=event.get('data')
    if not isinstance(data,dict):raise ValueError('Invalid subscription data')
    sid=data.get('subscription_id'); product=data.get('product_id'); status=data.get('status')
    metadata=data.get('metadata')
    if not isinstance(metadata,dict) or metadata.get('mosaic_workspace_id') != workspace_id or not _field(metadata.get('mosaic_checkout_nonce')):
        raise ValueError('Missing or mismatched workspace hint')
    at=event.get('timestamp')
    if not all(map(_field,(sid,product,at))) or not isinstance(status,str) or status not in STATES:
        raise ValueError('Invalid subscription fields')
    try:
        moment=datetime.fromisoformat(at.replace('Z','+00:00'))
        if moment.tzinfo is None:raise ValueError()
    except ValueError:raise ValueError('Invalid event timestamp')
    if abs((datetime.now(timezone.utc)-moment).total_seconds()) > 86400*30:
        raise ValueError('Event outside test window')
    canonical=moment.astimezone(timezone.utc).isoformat()
    period=data.get('next_billing_date')
    if period is not None and (not isinstance(period,str) or len(period)>64):
        raise ValueError('Invalid billing date')
    with store.tx():
        bind_dodo_test_subscription(store,workspace_id,sid,product,metadata['mosaic_checkout_nonce'])
        # The caller obtains workspace_id from a trusted, server-side Dodo TEST
        # checkout binding. No tenant identity is accepted from event metadata.
        binding=store._db.execute('SELECT workspace_id,plan_ref,last_event_at FROM billing_subscriptions WHERE workspace_id=? AND provider=? AND external_id=?',
                                  (workspace_id,'dodo_test',sid)).fetchone()
        if not binding:raise ValueError('Unbound subscription')
        wid=workspace_id
        # Product changes need a separately verified server-side binding update.
        if product != binding['plan_ref']:raise ValueError('Unknown product')
        if store._db.execute('SELECT event_id FROM billing_events WHERE workspace_id=? AND provider=? AND event_id=?',
                             (wid,'dodo_test',message_id)).fetchone():
            return {'accepted':True,'duplicate':True,'applied':False}
        store._db.execute('INSERT INTO billing_events(workspace_id,provider,event_id,subscription_id,received_at) VALUES(?,?,?,?,?)',
                          (wid,'dodo_test',message_id,sid,utcnow()))
        if binding['last_event_at'] >= canonical:
            return {'accepted':True,'duplicate':False,'applied':False}
        store._db.execute('UPDATE billing_subscriptions SET status=?,period_end=?,last_event_at=?,updated_at=? WHERE workspace_id=? AND provider=? AND external_id=?',
                          (STATES[status],period,canonical,utcnow(),wid,'dodo_test',sid))
    return {'accepted':True,'duplicate':False,'applied':True}
