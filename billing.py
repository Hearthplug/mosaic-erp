"""Provider-neutral sandbox event processing; live adapters must validate native signatures."""
import hashlib
import hmac
import json
import time
from datetime import datetime, timezone
from store import Conflict, utcnow

STATES = frozenset(('trialing', 'active', 'past_due', 'paused', 'canceled', 'expired'))

def verify_test_signature(body: bytes, timestamp: str, signature: str, secret: str, now=None):
    """HMAC over exact wire bytes, with short replay window, for test harness only."""
    if not secret or not timestamp or not signature or not timestamp.isdecimal():
        return False
    current = int(time.time() if now is None else now)
    if abs(current - int(timestamp)) > 300:
        return False
    expected = hmac.new(secret.encode(), timestamp.encode()+b'.'+body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)

def apply_test_event(store, event):
    """Store only an authenticated, validated sandbox status; never enable live access."""
    if not isinstance(event, dict): raise ValueError('Invalid billing event')
    required=('id','workspace_id','subscription_id','plan_ref','status','event_at')
    if any(not isinstance(event.get(k),str) or not event[k].strip() or len(event[k])>256 for k in required):
        raise ValueError('Invalid billing event fields')
    if event['status'] not in STATES or not event['workspace_id'].startswith('wsp_'):
        raise ValueError('Invalid billing state or workspace')
    try:
        occurred=datetime.fromisoformat(event['event_at'].replace('Z','+00:00'))
        if occurred.tzinfo is None:raise ValueError()
    except ValueError:raise ValueError('Invalid event timestamp')
    if abs((datetime.now(timezone.utc)-occurred).total_seconds())>86400*30:
        raise ValueError('Event timestamp outside sandbox window')
    at=occurred.astimezone(timezone.utc).isoformat()
    period=event.get('period_end')
    if period is not None and (not isinstance(period,str) or len(period)>64):raise ValueError('Invalid period end')
    wid=event['workspace_id']; sid=event['subscription_id']; provider='test'
    with store.tx():
        if not store._db.execute('SELECT id FROM workspaces WHERE id=?',(wid,)).fetchone():
            raise ValueError('Unknown workspace')
        prior=store._db.execute('SELECT workspace_id,last_event_at FROM billing_subscriptions WHERE workspace_id=? AND provider=? AND external_id=?',(wid,provider,sid)).fetchone()
        duplicate=store._db.execute('SELECT workspace_id FROM billing_events WHERE workspace_id=? AND provider=? AND event_id=?',(wid,provider,event['id'])).fetchone()
        if duplicate:
            return {'accepted':True,'duplicate':True,'applied':False}
        store._db.execute('INSERT INTO billing_events(workspace_id,provider,event_id,subscription_id,received_at) VALUES(?,?,?,?,?)',(wid,provider,event['id'],sid,utcnow()))
        if prior and prior['last_event_at']>=at:return {'accepted':True,'duplicate':False,'applied':False}
        if prior:
            store._db.execute('UPDATE billing_subscriptions SET plan_ref=?,status=?,period_end=?,last_event_at=?,updated_at=? WHERE provider=? AND external_id=? AND workspace_id=?',(event['plan_ref'],event['status'],period,at,utcnow(),provider,sid,wid))
        else:
            store._db.execute('INSERT INTO billing_subscriptions(workspace_id,provider,external_id,plan_ref,status,period_end,last_event_at,updated_at) VALUES(?,?,?,?,?,?,?,?)',(wid,provider,sid,event['plan_ref'],event['status'],period,at,utcnow()))
    return {'accepted':True,'duplicate':False,'applied':True}

def list_test_subscriptions(store, wid):
    rows=store._db.execute('SELECT external_id,plan_ref,status,period_end,last_event_at FROM billing_subscriptions WHERE workspace_id=? AND provider=? ORDER BY updated_at DESC',(wid,'test')).fetchall()
    return {'mode':'test','entitlements':'none','subscriptions':[dict(r) for r in rows]}
